"""
    Etapa 3 da triagem por abstract: aplica a decisão por cluster.
    Lê as atribuições do KMeans final e grava em included.jsonl o Work de cada
    artigo dos clusters mantidos, com o abstract que a cascata do fetch achou.
"""
import csv
import json
from dataclasses import asdict, fields
from pathlib import Path

from sar_review_pipeline.work import Work

# execução de 14/11/2026 (mpnet, cosseno, K=10). Os números dos clusters valem só para
# este assignments_k10.csv: outra execução do fit pode renumerá-los (ver docs/decisoes.md)
ASSIGNMENTS_PATH = Path("data/cluster/mpnet/cosine/assignments_k10.csv")

# clusters excluídos, com o tema e o número que o cluster tinha na análise original (results/clustering/mpnet_cosine_k10)
EXCLUDED_CLUSTERS = {
    2: "Robôs humanoides (NAO) em terapia de crianças com TEA (original: 0)",
    6: "SAR para idosos em casa e em lares (original: 1)",
    3: "Robótica social geral, sem tema específico (original: 3)",
    4: "Robôs sociais na educação de crianças (original: 9)",
}


class Inclusion:
    RECORDS_PATH = Path("data/jsonl/candidates_abstracts.jsonl")
    OUTPUT_PATH = Path("data/jsonl/included.jsonl")
    WORK_FIELDS = {f.name for f in fields(Work)}

    @classmethod
    def load_assignments(cls, path: Path = ASSIGNMENTS_PATH) -> dict[str, int]:
        """id -> cluster."""
        with open(path, newline="", encoding="utf-8") as f:
            return {row["id"]: int(row["cluster"]) for row in csv.DictReader(f)}

    @classmethod
    def load_works(cls) -> dict[str, Work]:
        """Works de candidates_abstracts.jsonl, só com os campos de Work (sem os da triagem)."""
        works = {}
        with open(cls.RECORDS_PATH, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                works[record["id"]] = Work(**{k: v for k, v in record.items() if k in cls.WORK_FIELDS})
        return works

    @classmethod
    def select(cls) -> tuple[list[Work], dict[int, int]]:
        """Works dos clusters mantidos, na ordem do assignments, e o tamanho de cada cluster."""
        assignments = cls.load_assignments()
        works = cls.load_works()
        sizes: dict[int, int] = {}
        included = []
        for work_id, cluster in assignments.items():
            sizes[cluster] = sizes.get(cluster, 0) + 1
            if cluster not in EXCLUDED_CLUSTERS:
                included.append(works[work_id])
        return included, dict(sorted(sizes.items()))

    @classmethod
    def save(cls, works: list[Work], path: Path = OUTPUT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for w in works:
                f.write(json.dumps(asdict(w), ensure_ascii=False) + "\n")
