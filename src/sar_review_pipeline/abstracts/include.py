"""
    Etapa 3 da triagem por abstract: aplica a decisão por cluster.
    Lê as atribuições do KMeans final e grava em r<N>/included.jsonl o Work de cada
    artigo dos clusters mantidos, com o abstract que a cascata do fetch achou.
"""
import csv
import json
from dataclasses import asdict, dataclass, field, fields
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
    kept: dict[int, str] = field(default_factory=dict)  # cluster -> tema, só para o registro
    k_rationale: str = ""  # por que este K (vai para results/rounds/r<N>/summary.json)

    def assignments(self, rnd: Round) -> Path:
        return rnd.cluster_dir / self.model / self.metric / f"assignments_k{self.k}.csv"


# uma decisão por rodada, tomada depois do sweep, do fit e da leitura dos clusters (docs/decisoes.md)
DECISIONS: dict[int, ClusterDecision] = {
    # rodada 1 (r1/cluster/mpnet/cosine/assignments_k10.csv). Revisada em 20/11/2026 com o orientador: fica
    # *somente* o cluster 1, SAR em hospitais e cuidado clínico (o foco da pesquisa). A primeira versão do dia
    # mantinha 1, 2, 4, 5, 7, 8 e 9 (295 artigos); ver docs/decisoes.md.
    1: ClusterDecision(
        model="mpnet",
        k=10,
        excluded={
            0: "Aceitação de SAR por idosos",
            2: "Atitudes, confiança e UX de robôs sociais",
            3: "Desenvolvimento de plataformas e sistemas de SAR",
            4: "Eficácia de SAR e robôs de companhia em demência e cuidado de idosos",
            5: "Ética e visão de profissionais no cuidado de idosos",
            6: "IA, controle e emoção em robôs sociais",
            7: "SAR em reabilitação (AVC, cardíaca)",
            8: "Design, aparência, morfologia e toque",
            9: "SAR em saúde mental e psiquiatria",
        },
        kept={1: "SAR em hospitais e cuidado clínico"},
        k_rationale=("cotovelo sem quebra clara; silhouette 0,0907, pico local e o maior a partir de K=5 "
                     "(K=2 a K=4 maiores, mas grosseiros demais para decidir por tema); escolha do usuário em 20/11/2026"),
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
