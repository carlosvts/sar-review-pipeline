"""
    Caminhos de cada direção do snowballing. data/ é a fonte da verdade entre as duas:
    a coleta muda (snowball/backward.py e snowball/forward.py), o resto da pipeline
    (triagem por título, abstracts, clustering, inclusão) é o mesmo código com outros arquivos.

    O backward mantém os caminhos que já existiam antes do forward, para não mover dados.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

DATA = Path("data")
RAW = DATA / "raw"
JSONL = DATA / "jsonl"

START_SET_DOIS = DATA / "start_set_dois.csv"
START_SET_RAW = RAW / "start_set.json"
START_SET_JSONL = JSONL / "start_set.jsonl"


@dataclass(frozen=True)
class Direction:
    name: str
    works: Path                  # um Work por linha (saída da etapa 01)
    title_screening_json: Path   # triagem por título acumulada (etapa 02)
    title_screening_jsonl: Path
    candidates: Path             # passed_title + needs_context (etapa 02)
    candidates_abstracts: Path   # candidatos com abstract e regra de decisão (etapa 03)
    coverage_report: Path
    cluster_dir: Path            # embeddings, varreduras e atribuições (etapa 03)
    included: Path               # works dos clusters mantidos (etapa 03 -> etapa 04)


BACKWARD = Direction(
    name="backward",
    works=JSONL / "backward.jsonl",
    title_screening_json=RAW / "title_screening.json",
    title_screening_jsonl=JSONL / "title_screening.jsonl",
    candidates=JSONL / "candidates.jsonl",
    candidates_abstracts=JSONL / "candidates_abstracts.jsonl",
    coverage_report=DATA / "abstracts/coverage_report.json",
    cluster_dir=DATA / "cluster",
    included=JSONL / "included.jsonl",
)

FORWARD = Direction(
    name="forward",
    works=JSONL / "forward.jsonl",
    title_screening_json=RAW / "forward_title_screening.json",
    title_screening_jsonl=JSONL / "forward_title_screening.jsonl",
    candidates=JSONL / "forward_candidates.jsonl",
    candidates_abstracts=JSONL / "forward_candidates_abstracts.jsonl",
    coverage_report=DATA / "abstracts/forward_coverage_report.json",
    cluster_dir=DATA / "cluster/forward",
    included=JSONL / "forward_included.jsonl",
)

DIRECTIONS = {d.name: d for d in (BACKWARD, FORWARD)}


def pop_direction(args: list[str]) -> tuple[Direction, list[str]]:
    """Tira `--direction <nome>` dos argumentos; sem ele, a direção é backward."""
    if "--direction" not in args:
        return BACKWARD, args
    i = args.index("--direction")
    if i + 1 >= len(args) or args[i + 1] not in DIRECTIONS:
        sys.exit(f"--direction precisa ser uma de: {', '.join(DIRECTIONS)}")
    return DIRECTIONS[args[i + 1]], args[:i] + args[i + 2 :]
