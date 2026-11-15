"""
    Etapa 3 da triagem por abstract: aplica a decisão por cluster.
    Lê as atribuições do KMeans final e grava em included.jsonl (da direção) o Work de cada
    artigo dos clusters mantidos, com o abstract que a cascata do fetch achou.
"""
import csv
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from sar_review_pipeline.direction import BACKWARD, Direction
from sar_review_pipeline.work import Work


@dataclass(frozen=True)
class ClusterDecision:
    # os números dos clusters valem só para este assignments: outro fit pode renumerá-los (docs/decisoes.md)
    assignments: Path
    excluded: dict[int, str]  # cluster -> tema


DECISIONS: dict[str, ClusterDecision] = {
    # execução de 14/11/2026 (mpnet, cosseno, K=10); entre parênteses, o número na análise original
    # (results/clustering/mpnet_cosine_k10)
    "backward": ClusterDecision(
        assignments=BACKWARD.cluster_dir / "mpnet/cosine/assignments_k10.csv",
        excluded={
            2: "Robôs humanoides (NAO) em terapia de crianças com TEA (original: 0)",
            6: "SAR para idosos em casa e em lares (original: 1)",
            3: "Robótica social geral, sem tema específico (original: 3)",
            4: "Robôs sociais na educação de crianças (original: 9)",
        },
    ),
    # forward: decisão pendente, depois do clustering
}


class Inclusion:
    WORK_FIELDS = {f.name for f in fields(Work)}

    @classmethod
    def decision(cls, direction: Direction) -> ClusterDecision:
        if direction.name not in DECISIONS:
            raise SystemExit(f"a exclusão por cluster do {direction.name} ainda não foi decidida (DECISIONS em include.py)")
        return DECISIONS[direction.name]

    @classmethod
    def load_assignments(cls, path: Path) -> dict[str, int]:
        """id -> cluster."""
        with open(path, newline="", encoding="utf-8") as f:
            return {row["id"]: int(row["cluster"]) for row in csv.DictReader(f)}

    @classmethod
    def load_works(cls, direction: Direction) -> dict[str, Work]:
        """Works de candidates_abstracts.jsonl, só com os campos de Work (sem os da triagem)."""
        works = {}
        with open(direction.candidates_abstracts, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                works[record["id"]] = Work(**{k: v for k, v in record.items() if k in cls.WORK_FIELDS})
        return works

    @classmethod
    def select(cls, direction: Direction) -> tuple[list[Work], dict[int, int]]:
        """Works dos clusters mantidos, na ordem do assignments, e o tamanho de cada cluster."""
        decision = cls.decision(direction)
        assignments = cls.load_assignments(decision.assignments)
        works = cls.load_works(direction)
        sizes: dict[int, int] = {}
        included = []
        for work_id, cluster in assignments.items():
            sizes[cluster] = sizes.get(cluster, 0) + 1
            if cluster not in decision.excluded:
                included.append(works[work_id])
        return included, dict(sorted(sizes.items()))

    @classmethod
    def save(cls, works: list[Work], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for w in works:
                f.write(json.dumps(asdict(w), ensure_ascii=False) + "\n")
