"""
Embeddings da rodada 2 e os 3 trechos por QP de cada artigo, no formato do artefato.
Usa as classes do repo (Embedder, ChromaStore); carrega o modelo na GPU (CUDA, float16) se houver; senão, CPU (float32).
Pontuação de um chunk numa QP = maior cosseno entre ele e as sub_queries da QP (QP1..QP4).
"""
import json
import sys
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer

from sar_review_pipeline.rag.embedds import ChromaStore, Embedder, load_clusters, load_questions, sanitize_subqueries

QPS = ["QP1", "QP2", "QP3", "QP4"]
TOP = 3
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE = torch.float16 if DEVICE == "cuda" else torch.float32


class DeviceEmbedder(Embedder):
    def __init__(self, batch_size: int = 8):
        self.batch_size = batch_size
        self.model = SentenceTransformer(self.MODEL_NAME, device=DEVICE, model_kwargs={"dtype": DTYPE},
                                         processor_kwargs={"padding_side": "left"})


class Evidence:
    @classmethod
    def pages(cls, chunk: dict) -> str:
        if chunk["kind"] == "xml" or chunk["page_start"] is None:
            return "XML"
        if chunk["page_start"] == chunk["page_end"]:
            return f"p. {chunk['page_start']}"
        return f"pp. {chunk['page_start']}–{chunk['page_end']}"

    @classmethod
    def for_paper(cls, chunks: list[dict], doc_vectors, query_vectors: dict) -> dict:
        evidence = {}
        for qp in QPS:
            scores = doc_vectors @ query_vectors[qp].T  # (n_chunks, n_subqueries), já normalizados
            best = scores.max(axis=1)
            order = best.argsort()[::-1][:TOP]
            items = []
            for i in order:
                c = chunks[i]
                items.append({"id": c["chunk_id"], "section": c["section"], "pages": cls.pages(c),
                              "cos": round(float(best[i]), 3), "text": c["text"]})
            evidence[qp] = items
        return evidence


def main():
    chunks_path, out_path, chroma_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    # coleção do Chroma: a 4ª opção evita apagar a coleção de outra rodada (reset=True)
    collection = sys.argv[4] if len(sys.argv) > 4 else "hri-articles-a-rodada2"
    chunks = load_clusters(chunks_path)
    questions = load_questions(Path("src/sar_review_pipeline/rag/questions.json"))
    subqueries = sanitize_subqueries(questions)

    embedder = DeviceEmbedder(batch_size=32 if DEVICE == "cuda" else 8)
    query_vectors = embedder.encode_queries(subqueries)
    doc_vectors = embedder.encode_documents(embedder.chunk_texts(chunks, with_section=False))

    store = ChromaStore(chroma_dir, name=collection, reset=True)
    store.add_chunks(chunks, doc_vectors)

    by_key: dict[str, list[int]] = {}
    for i, c in enumerate(chunks):
        by_key.setdefault(c["key"], []).append(i)
    result = {}
    for key, idxs in by_key.items():
        paper_chunks = [chunks[i] for i in idxs]
        result[key] = Evidence.for_paper(paper_chunks, doc_vectors[idxs], query_vectors)
    out_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"{len(chunks)} chunks, {len(result)} artigos -> {out_path}")


if __name__ == "__main__":
    main()
