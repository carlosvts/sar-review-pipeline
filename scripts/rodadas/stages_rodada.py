"""
Etapas 02 e 03 de uma rodada com as funções do pipeline, só trocando os caminhos: o Round do pipeline aponta
para data/rodada<N>/ (padrão das rodadas 2 e 3) em vez de data/rounds/r<N>/.

  uv run python scripts/rodadas/stages_rodada.py <N> title       triagem por título (screening.run + filter)
  uv run python scripts/rodadas/stages_rodada.py <N> abstracts   abstracts dos candidatos (step03-abstracts fetch)
  uv run --extra cluster-sentence-transformers python scripts/rodadas/stages_rodada.py <N> sweep     varredura de K (mpnet)
  uv run --extra cluster-sentence-transformers python scripts/rodadas/stages_rodada.py <N> fit <K>   KMeans final
  uv run python scripts/rodadas/stages_rodada.py <N> include     aplica data/rodada<N>/cluster_decision.json
"""
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sar_review_pipeline.rounds import Round


@dataclass(frozen=True)
class Rodada(Round):
    @property
    def name(self) -> str:
        return f"rodada{self.n}"

    @property
    def dir(self) -> Path:
        return Path(f"data/rodada{self.n}")

    @property
    def coverage_report(self) -> Path:
        return self.dir / "abstracts_coverage_report.json"


class Stages:
    @classmethod
    def title(cls, rnd: Rodada) -> dict:
        from sar_review_pipeline.screening import screening

        total = screening.run(rnd)
        screening.filter(rnd)
        rows = screening.load_screening_rows(rnd)
        counts = {"triados": total, "por_status": {}, "candidatos_por_direction": {}}
        for row in rows.values():
            status = row["status"]
            counts["por_status"][status] = counts["por_status"].get(status, 0) + 1
            if status in ("passed_title", "needs_context"):
                key = f"{row['direction']}/{status}"
                counts["candidatos_por_direction"][key] = counts["candidatos_por_direction"].get(key, 0) + 1
        return counts

    @classmethod
    def abstracts(cls, rnd: Rodada) -> None:
        from sar_review_pipeline.abstracts.__main__ import fetch

        fetch(rnd)

    @classmethod
    def sweep(cls, rnd: Rodada) -> None:
        from sar_review_pipeline.abstracts.__main__ import sweep as run_sweep

        run_sweep(rnd, "mpnet")

    @classmethod
    def fit(cls, rnd: Rodada, k: int) -> None:
        from sar_review_pipeline.abstracts.__main__ import fit as run_fit

        run_fit(rnd, "mpnet", k)

    @classmethod
    def include(cls, rnd: Rodada) -> dict:
        """Aplica a decisão do revisor (data/rodada<N>/cluster_decision.json) com o Inclusion do pipeline."""
        from sar_review_pipeline.abstracts import include as inc

        decision = json.load(open(rnd.dir / "cluster_decision.json", encoding="utf-8"))
        excluded = {}
        for cluster, theme in decision["excluidos"].items():
            excluded[int(cluster)] = theme
        kept = {}
        for cluster, theme in decision["mantidos"].items():
            kept[int(cluster)] = theme
        inc.DECISIONS[rnd.n] = inc.ClusterDecision(model="mpnet", k=decision["k"], excluded=excluded, kept=kept,
                                                   k_rationale=decision.get("criterio_k", ""))

        works, sizes = inc.Inclusion.select(rnd)
        inc.Inclusion.save(works, rnd.included)
        counts = {"clusters": {}, "incluidos": len(works), "por_direction": {}}
        for cluster, size in sizes.items():
            counts["clusters"][cluster] = {"artigos": size, "decisao": "excluido" if cluster in excluded else "mantido"}

        with open(rnd.dir / f"rodada{rnd.n}_download.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["openalex_id", "doi", "doi_url", "direction", "year", "title"])
            for w in works:
                counts["por_direction"][w.direction] = counts["por_direction"].get(w.direction, 0) + 1
                doi_url = f"https://doi.org/{w.doi}" if w.doi else ""
                writer.writerow([w.id.rsplit("/", 1)[-1], w.doi or "", doi_url, w.direction,
                                 w.publication_year or "", w.title or ""])
        return counts


def main():
    rnd = Rodada(int(sys.argv[1]))
    step = sys.argv[2]
    if step == "title":
        print(json.dumps(Stages.title(rnd), ensure_ascii=False))
    elif step == "abstracts":
        Stages.abstracts(rnd)
    elif step == "sweep":
        Stages.sweep(rnd)
    elif step == "fit":
        Stages.fit(rnd, int(sys.argv[3]))
    elif step == "include":
        print(json.dumps(Stages.include(rnd), ensure_ascii=False))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
