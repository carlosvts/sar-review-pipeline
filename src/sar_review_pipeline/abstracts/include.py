"""
    Etapa 3 da triagem por abstract: aplica a decisão por cluster.
    Lê as atribuições do KMeans final e grava em r<N>/included.jsonl o Work de cada
    artigo dos clusters mantidos, com o abstract que a cascata do fetch achou.
"""
import csv
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from sar_review_pipeline.rounds import Round
from sar_review_pipeline.work import Work


@dataclass(frozen=True)
class ClusterDecision:
    # os números dos clusters valem só para este fit: outro fit pode renumerá-los (docs/decisoes.md)
    model: str
    k: int
    excluded: dict[int, str]  # cluster -> tema
    metric: str = "cosine"

    def assignments(self, rnd: Round) -> Path:
        return rnd.cluster_dir / self.model / self.metric / f"assignments_k{self.k}.csv"


# uma decisão por rodada, tomada depois do sweep, do fit e da leitura dos clusters (docs/decisoes.md)
DECISIONS: dict[int, ClusterDecision] = {
    # rodada 1, decidida em 20/11/2026 (r1/cluster/mpnet/cosine/assignments_k10.csv). Critério: escopo em
    # SAR em healthcare institucional (hospitais, centros clínicos, ILPI), sem cuidado em casa, mais os
    # clusters de design que respondem às QPs, como na exclusão da pipeline anterior.
    # Mantidos: 1 hospitais e cuidado clínico, 2 atitudes/confiança/UX, 4 eficácia em demência e cuidado de
    # idosos, 5 ética e visão de profissionais no cuidado de idosos, 7 reabilitação, 8 design/aparência/toque,
    # 9 saúde mental e psiquiatria
    1: ClusterDecision(
        model="mpnet",
        k=10,
        excluded={
            0: "Aceitação de SAR por idosos (mais casa que clínico; herdeiro de 'idosos em casa e em lares')",
            3: "Desenvolvimento de plataformas e sistemas de SAR (robôs domésticos para idosos)",
            6: "IA, controle e emoção em robôs sociais (herdeiro de 'robótica social geral', pouco de saúde)",
        },
    ),
}


class Inclusion:
    WORK_FIELDS = {f.name for f in fields(Work)}

    @classmethod
    def decision(cls, rnd: Round) -> ClusterDecision:
        if rnd.n not in DECISIONS:
            raise SystemExit(f"a exclusão por cluster da {rnd.name} ainda não foi decidida (DECISIONS em include.py)")
        return DECISIONS[rnd.n]

    @classmethod
    def load_assignments(cls, path: Path) -> dict[str, int]:
        """id -> cluster."""
        with open(path, newline="", encoding="utf-8") as f:
            return {row["id"]: int(row["cluster"]) for row in csv.DictReader(f)}

    @classmethod
    def load_works(cls, rnd: Round) -> dict[str, Work]:
        """Works de candidates_abstracts.jsonl, só com os campos de Work (sem os da triagem)."""
        works = {}
        with open(rnd.candidates_abstracts, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                works[record["id"]] = Work(**{k: v for k, v in record.items() if k in cls.WORK_FIELDS})
        return works

    @classmethod
    def select(cls, rnd: Round) -> tuple[list[Work], dict[int, int]]:
        """Works dos clusters mantidos, na ordem do assignments, e o tamanho de cada cluster."""
        decision = cls.decision(rnd)
        assignments = cls.load_assignments(decision.assignments(rnd))
        works = cls.load_works(rnd)
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
