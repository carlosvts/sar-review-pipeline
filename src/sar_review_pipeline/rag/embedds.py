"""
    Etapa 05 de uma rodada: indexa os chunks (seção + texto) e, para cada artigo incluído no cluster,
    busca os trechos mais próximos de cada QP. A busca não decide nada: grava um arquivo de revisão
    por artigo (r<N>/fulltext/rag_review/W….md) com os trechos literais, a seção e a página, e a
    leitura humana diz, por QP, se o artigo responde. Responde a alguma QP: include; a nenhuma: exclude
    (colunas qp1..qp5 e decision do r<N>/fulltext/decisions.csv).
"""
import json
import sys
from pathlib import Path

import chromadb
import torch
from sentence_transformers import SentenceTransformer

from sar_review_pipeline.rounds import CHROMA, Round, pop_round
from sar_review_pipeline.work import Work

QUESTIONS = Path(__file__).resolve().parent / "questions.json"
TOP_K = 3          # trechos por QP guardados em rag_evidence.jsonl
REVIEW_K = 1       # trechos por QP no arquivo de revisão (20/11/2026: o usuário pediu menos texto)
REVIEW_QPS = ("QP1", "QP2", "QP3", "QP4")  # só as QPs que incluem (IC2/IC3); QP5 fica só no rag_evidence.jsonl
PER_SUBQUERY = 3   # vizinhos buscados por sub-query, antes de juntar
WITH_SECTION = True  # variante B (seção + texto), escolhida em 19/11/2026


def load_questions(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        questions = json.load(f)
        return questions


def load_clusters(path: Path):
    clusters = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            jsoned_line = json.loads(line)
            clusters.append(jsoned_line)
        return clusters


def sanitize_subqueries(questions):
    """
        sanitiza as subqueries de cada QP para o modelo
        retorna dict[QPX, [lista de subqueries]]
    """
    sanitized_qps = {}
    for question in questions:
        sanitized_qps[question["id"]] = question["sub_queries"]
    return sanitized_qps


class Embedder:
    """
        Transforma textos em vetores com o Qwen3-Embedding.
        Documentos (chunks) vao sem instrucao; as queries levam a instrucao da sua QP.
    """
    MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
    BATCH_SIZE = 12

    INSTRUCTIONS = {
        "QP1": "Instruct: Given a question about the physical and visual design of social robots, retrieve passages from research papers that describe the robot's appearance, shape, size, materials, color or face.\nQuery: ",
        "QP2": "Instruct: Given a question about how social robots communicate, retrieve passages from research papers that describe the robot's speech, voice, gestures, movement, touch, light or sound and the strategy behind them.\nQuery: ",
        "QP3": "Instruct: Given a question about emotion, expressiveness or personality in social robots, retrieve passages from research papers that describe how the robot displays, models or conveys them to users.\nQuery: ",
        "QP4": "Instruct: Given a question about evaluating human-robot interaction, retrieve passages from research papers that describe the evaluation method and the instruments used, such as questionnaires, scales, interviews or behavioral measures.\nQuery: ",
        "QP5": "Instruct: Given a question about limitations of social robot interaction design, retrieve passages from research papers where the authors state limitations, open questions, unresolved challenges or future work.\nQuery: ",
    }

    def __init__(self, batch_size: int = BATCH_SIZE):
        self.batch_size = batch_size
        # boilerplate work from: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
        # Load the model
        self.model = SentenceTransformer(
            self.MODEL_NAME,
            # sdpa = scaled dot product attention
            model_kwargs={"attn_implementation": "sdpa", "device_map": "auto", "dtype": torch.float16},
            processor_kwargs={"padding_side": "left"},
        )

    @staticmethod
    def chunk_texts(chunks: list[dict], with_section: bool = False) -> list[str]:
        """
            A: so o texto do chunk
            B (with_section=True): secao + texto (se a secao estiver vazia, usa so o texto)
            a linha i dos vetores e sempre o chunk i dessa lista
        """
        if with_section:
            return [f"{c['section']}\n{c['text']}" if c["section"] else c["text"] for c in chunks]
        return [c["text"] for c in chunks]

    def encode_documents(self, texts: list[str]):
        """
            documentos NAO levam prompt
            retorna array (n_chunks, 1024), normalizado
        """
        return self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
        )

    def encode_queries(self, sn_subqueries: dict[str, list[str]]):
        """
            uma chamada por QP, cada uma com a sua instrucao
            retorna dict[QPX, array (n_subqueries, 1024)]
        """
        query_vectors = {}
        for qp_id, subqueries in sn_subqueries.items():
            query_vectors[qp_id] = self.model.encode(
                subqueries,
                prompt=self.INSTRUCTIONS[qp_id],      # no lugar de prompt_name="query"
                normalize_embeddings=True,
            )
        return query_vectors


class ChromaStore:
    """
        Guarda os vetores dos chunks no ChromaDB (cosseno) e busca dentro de um paper.
        O Chroma devolve distancia = 1 - cosseno.
    """
    ADD_BATCH = 500

    def __init__(self, path: Path, name: str = "hri-articles", reset: bool = False):
        self.client = chromadb.PersistentClient(path=str(path))
        self.name = name
        if reset:
            # o add ignora ids que ja existem, entao para refazer os vetores a colecao precisa ser apagada
            try:
                self.client.delete_collection(name)
            except Exception:
                pass  # caso ainda nao existia
        self.collection = self.client.get_or_create_collection(
            name=name,
            configuration={"hnsw": {"space": "cosine"}},
        )

    @staticmethod
    def build_metadata(c: dict) -> dict:
        meta = {
            "key": c["key"],
            "section": c["section"],
            "page_start": c["page_start"],
            "page_end": c["page_end"],
            "para_start": c["para_start"],
            "para_end": c["para_end"],
        }
        # chunks de XML tem pagina None; o Chroma nao garante aceitar None
        return {k: v for k, v in meta.items() if v is not None}

    def add_chunks(self, chunks: list[dict], vectors):
        """
            ids = chunk_id, documents = texto ORIGINAL (para conferir a evidencia)
            vectors: array (n_chunks, 1024) na mesma ordem de chunks
        """
        assert len(chunks) == len(vectors), "chunks e vetores precisam ter o mesmo tamanho"
        for i in range(0, len(chunks), self.ADD_BATCH):
            batch = chunks[i:i + self.ADD_BATCH]
            self.collection.add(
                ids=[c["chunk_id"] for c in batch],
                embeddings=vectors[i:i + self.ADD_BATCH],
                documents=[c["text"] for c in batch],
                metadatas=[self.build_metadata(c) for c in batch],
            )
        print(f"{self.name}: {self.collection.count()} chunks (esperado {len(chunks)})")

    def search_paper(self, key: str, vectors, k: int = 3):
        """
            vectors: array (n_subqueries, 1024) de uma QP
            retorna o resultado do Chroma (listas aninhadas: [i] = sub_query i)
        """
        return self.collection.query(
            query_embeddings=vectors,
            n_results=k,
            where={"key": key},
        )

    @staticmethod
    def print_results(subqueries: list[str], res: dict):
        for i, subquery in enumerate(subqueries):
            print(subquery)
            for cid, dist, doc in zip(res["ids"][i], res["distances"][i], res["documents"][i]):
                print(f"cos={1 - dist:.3f}  {cid}  {doc[:150]}")


def best_chunks(store: "ChromaStore", key: str, vectors, k: int = TOP_K) -> list[dict]:
    """Junta as sub-queries de uma QP: para cada chunk, o maior cosseno; devolve os k melhores."""
    res = store.search_paper(key, vectors, k=PER_SUBQUERY)
    best: dict[str, dict] = {}
    for i in range(len(vectors)):
        for cid, dist, doc, meta in zip(res["ids"][i], res["distances"][i], res["documents"][i], res["metadatas"][i]):
            cos = 1 - dist
            if cid not in best or cos > best[cid]["cos"]:
                best[cid] = {"chunk_id": cid, "cos": round(cos, 3), "section": meta.get("section", ""),
                             "page_start": meta.get("page_start"), "page_end": meta.get("page_end"), "text": doc}
    return sorted(best.values(), key=lambda c: -c["cos"])[:k]


def pages(c: dict) -> str:
    if c["page_start"] is None:
        return "XML, sem página"
    if c["page_end"] in (None, c["page_start"]):
        return f"p. {c['page_start']}"
    return f"p. {c['page_start']}-{c['page_end']}"


def review_markdown(work: Work, questions: list[dict], evidence: dict[str, list[dict]]) -> str:
    lines = [f"# {work.title}", "", f"{work.id} · doi {work.doi or '-'} · {work.publication_year or ''} · {work.direction}", ""]
    for q in questions:
        if q["id"] not in REVIEW_QPS:
            continue
        lines += [f"## {q['id']}: {q['question']}", ""]
        for c in evidence[q["id"]][:REVIEW_K]:
            lines += [f"*{c['section'] or '(sem seção)'} · {pages(c)} · cos {c['cos']}*", "", c["text"], ""]
        lines += [f"- [ ] responde à {q['id']}", ""]
    lines += [
        "## Decisão", "",
        "- [ ] include (marque acima as QPs que o artigo responde)",
        "- [ ] seed_only: revisão ou estudo secundário (EC4)",
        "- [ ] exclude, código: EC",
        "",
        "Motivo: ",
        "",
    ]
    return "\n".join(lines)


def has_marks(path: Path) -> bool:
    """Arquivo de revisão com alguma caixa marcada: a leitura começou e ele não é reescrito."""
    return path.exists() and "- [x]" in path.read_text(encoding="utf-8").lower()


def write_reviews(rnd: Round, questions: list[dict]) -> int:
    """Arquivos de revisão por artigo e o index.md, a partir do rag_evidence.jsonl (sem refazer embeddings)."""
    works = {w.rsplit("/", 1)[-1]: v for w, v in Work.load_jsonl(str(rnd.included)).items()}
    rnd.rag_review_dir.mkdir(parents=True, exist_ok=True)
    keys = []
    with open(rnd.fulltext_dir / "rag_evidence.jsonl", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            keys.append(e["key"])
            path = rnd.rag_review_dir / f"{e['key']}.md"
            if has_marks(path):
                continue  # nunca apaga uma marcação
            path.write_text(review_markdown(works[e["key"]], questions, e["evidence"]), encoding="utf-8")
    index = [f"# Revisão do texto completo, {rnd.name}", "",
             "Inclui se responder a pelo menos uma de QP1 a QP4 (IC2/IC3). Revisões e estudos secundários: seed_only (EC4).",
             "Em cada arquivo, marque [x] nas QPs que o artigo responde e, se for o caso, seed_only ou exclude com o código EC.",
             "Só QPs marcadas = include. Depois:  uv run step04-fulltext collect --round N",
             "Demais critérios em docs/criterios-elegibilidade.md.", ""]
    for q in questions:
        if q["id"] in REVIEW_QPS:
            index += [f"- **{q['id']}**: {q['description']}"]
    index += ["", "## Artigos", ""] + [f"- [{works[k].title}]({k}.md)" for k in keys]
    (rnd.rag_review_dir / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return len(keys)


def main():
    # uv run --frozen --extra rag step05-embed --round N
    #   indexa r<N>/fulltext/chunks.jsonl (coleção round-N em data/rounds/chroma) e grava a revisão por artigo
    #   --review-only: só regera os arquivos de revisão a partir do rag_evidence.jsonl
    rnd, args = pop_round(sys.argv[1:])
    if "--review-only" in args:
        n = write_reviews(rnd, load_questions(QUESTIONS))
        print(f"{n} arquivos de revisão regerados -> {rnd.rag_review_dir.resolve()}")
        return
    if not rnd.chunks.exists():
        sys.exit(f"{rnd.chunks} não existe: rode antes  uv run step05-chunk --round {rnd.n}")
    questions = load_questions(QUESTIONS)
    chunks = load_clusters(rnd.chunks)
    works = {w.rsplit("/", 1)[-1]: v for w, v in Work.load_jsonl(str(rnd.included)).items()}
    keys = sorted({c["key"] for c in chunks})

    embedder = Embedder(batch_size=4)
    query_vectors = embedder.encode_queries(sanitize_subqueries(questions))
    doc_vectors = embedder.encode_documents(embedder.chunk_texts(chunks, with_section=WITH_SECTION))
    store = ChromaStore(CHROMA, name=f"round-{rnd.n}", reset=True)
    store.add_chunks(chunks, doc_vectors)

    with open(rnd.fulltext_dir / "rag_evidence.jsonl", "w", encoding="utf-8") as out:
        for key in keys:
            evidence = {q["id"]: best_chunks(store, key, query_vectors[q["id"]]) for q in questions}
            out.write(json.dumps({"key": key, "id": works[key].id, "evidence": evidence}, ensure_ascii=False) + "\n")
    n = write_reviews(rnd, questions)
    print(f"{n} artigos revisáveis -> {rnd.rag_review_dir.resolve()}")


if __name__ == "__main__":
    main()
