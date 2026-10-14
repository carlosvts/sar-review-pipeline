from sentence_transformers import SentenceTransformer
from pathlib import Path
import torch
import json
import chromadb

ROOT = Path(__file__).resolve().parents[3]
CLUSTER_FILE = ROOT / "data/fulltext/chunks.jsonl"
QUESTIONS = ROOT / "src/sar_review_pipeline/rag/questions.json"


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
                print(f"  cos={1 - dist:.3f}  {cid}  {doc}")


if __name__ == "__main__":
    SANITY_KEY = "W4210814395" # paper para o teste de sanidade
    SANITY_QP = "QP5"

    questions = load_questions(Path(QUESTIONS))
    sn_subqueries = sanitize_subqueries(questions)
    document = load_clusters(Path(CLUSTER_FILE))

    embedder = Embedder()
    query_vectors = embedder.encode_queries(sn_subqueries)

    # mesmo document, duas entradas (A: texto, B: secao + texto), uma colecao para cada
    for suffix, with_section in (("a", False), ("b", True)):
        texts = embedder.chunk_texts(document, with_section=with_section)
        doc_vectors = embedder.encode_documents(texts)

        store = ChromaStore(ROOT / "data/chroma", name=f"hri-articles-{suffix}", reset=True)
        store.add_chunks(document, doc_vectors)

        print(f"\n=== versao {suffix.upper()} | {SANITY_KEY} | {SANITY_QP} ===")
        res = store.search_paper(SANITY_KEY, query_vectors[SANITY_QP], k=3)
        store.print_results(sn_subqueries[SANITY_QP], res)
