"""
Etapas 02 e 03 da rodada 3 com as funções do pipeline, só trocando os caminhos (Direction própria).
  title     -> triagem por título (screening.run + screening.filter)
  abstracts -> abstracts dos candidatos (step03-abstracts fetch)
  sweep     -> varredura de K com mpnet (cotovelo e silhouette); roda com o extra cluster-sentence-transformers
"""
import json
import sys
from collections import Counter
from pathlib import Path

from sar_review_pipeline.direction import Direction

ROOT = Path("data/rodada3")
RODADA3 = Direction(
    name="rodada3",
    works=ROOT / "works.jsonl",
    title_screening_json=ROOT / "title_screening.json",
    title_screening_jsonl=ROOT / "title_screening.jsonl",
    candidates=ROOT / "candidates.jsonl",
    candidates_abstracts=ROOT / "candidates_abstracts.jsonl",
    coverage_report=ROOT / "abstracts_coverage_report.json",
    cluster_dir=ROOT / "cluster",
    included=ROOT / "included.jsonl",
)


def title() -> None:
    from sar_review_pipeline.screening import screening

    total = screening.run(RODADA3)
    screening.filter(RODADA3)
    rows = screening.load_screening_rows(RODADA3)
    by_status = Counter()
    by_dir = Counter()
    for row in rows.values():
        by_status[row["status"]] += 1
        if row["status"] in ("passed_title", "needs_context"):
            by_dir[(row["direction"], row["status"])] += 1
    print(f"triados: {total}")
    print("por status:", json.dumps(dict(by_status)))
    print("candidatos por direction:", {f"{d}/{s}": n for (d, s), n in sorted(by_dir.items())})


def abstracts() -> None:
    from sar_review_pipeline.abstracts.__main__ import fetch

    fetch(RODADA3)


class CpuLoader:
    """load_model do PaperEmbedder em CPU: mesmo modelo, revisão, dtype e max_length do MODELS."""

    @staticmethod
    def load_model(embedder) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        embedder.device = "cpu"
        model_kwargs = dict(embedder.config.get("model_kwargs", {}))
        model_kwargs["dtype"] = getattr(torch, embedder.config["dtype"])
        embedder.model = SentenceTransformer(
            embedder.config["base"],
            revision=embedder.config["base_revision"],
            device="cpu",
            model_kwargs=model_kwargs,
            processor_kwargs=embedder.config.get("processor_kwargs", {}),
        )
        embedder.model.max_seq_length = embedder.config["max_length"]
        embedder.encode_batch = embedder.encode_sentence_transformers
        embedder.model.eval()


def sweep() -> None:
    from sar_review_pipeline.abstracts.__main__ import sweep as run_sweep
    from sar_review_pipeline.abstracts.embed import PaperEmbedder

    # este notebook não tem GPU; o mpnet em float32 dá o mesmo resultado em CPU
    PaperEmbedder.load_model = CpuLoader.load_model
    run_sweep(RODADA3, "mpnet")


def fit() -> None:
    from sar_review_pipeline.abstracts.__main__ import fit as run_fit
    from sar_review_pipeline.abstracts.embed import PaperEmbedder

    PaperEmbedder.load_model = CpuLoader.load_model
    run_fit(RODADA3, "mpnet", int(sys.argv[2]))


def include() -> None:
    """Etapa 3: aplica a decisão do revisor (data/rodada3/cluster_decision.json) com o Inclusion do pipeline."""
    import csv
    from sar_review_pipeline.abstracts import include as inc

    decision = json.load(open(ROOT / "cluster_decision.json", encoding="utf-8"))
    excluded = {}
    for cluster, theme in decision["excluidos"].items():
        excluded[int(cluster)] = theme
    inc.DECISIONS[RODADA3.name] = inc.ClusterDecision(assignments=Path(decision["assignments"]), excluded=excluded)

    works, sizes = inc.Inclusion.select(RODADA3)
    inc.Inclusion.save(works, RODADA3.included)
    for cluster, size in sizes.items():
        status = "excluído" if cluster in excluded else "mantido"
        print(f"  {cluster:2d}: {size:4d}  {status}")

    by_dir = Counter()
    with open(ROOT / "rodada3_download.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["openalex_id", "doi", "doi_url", "direction", "year", "title"])
        for w in works:
            by_dir[w.direction] += 1
            writer.writerow([w.id.rsplit("/", 1)[-1], w.doi or "", f"https://doi.org/{w.doi}" if w.doi else "",
                             w.direction, w.publication_year or "", w.title or ""])
    print(f"incluídos: {len(works)}  por direction: {dict(by_dir)}")


def main():
    steps = {"title": title, "abstracts": abstracts, "sweep": sweep, "fit": fit, "include": include}
    steps[sys.argv[1]]()


if __name__ == "__main__":
    main()
