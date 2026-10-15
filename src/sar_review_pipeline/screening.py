import json
import re
from dataclasses import dataclass
from pathlib import Path

from sar_review_pipeline.work import Work

DATA = Path("data")
RAW = DATA / "raw"
JSONL = DATA / "jsonl"
INPUT_PATHS = [
    JSONL / "backward.jsonl",
]
OUTPUT_JSON_PATH = RAW / "title_screening.json"
OUTPUT_JSONL_PATH = JSONL / "title_screening.jsonl"
OUTPUT_JSONL_FILTERED_PATH = JSONL / "candidates.jsonl"

@dataclass(frozen=True)
class TitleScreeningRule:
    name: str
    patterns: tuple[str, ...]
    # se True, o título também precisa de um termo de HEALTHCARE_CONTEXT
    requires_context: bool = False


INCLUSION_RULES: tuple[TitleScreeningRule, ...] = (
    TitleScreeningRule(
        name="termo específico de SAR",
        patterns=(
            r"\bsocially assistive robot",
            r"\bassistive social robot",
            r"\bcompanion robot",
            r"\brobot(ic)? companion",
            r"\bpet robot",
            r"\brobotic (pet|animal|seal|dog|cat)",
            r"\bcare ?robot",
            r"\bcarebot",
        ),
    ),
    TitleScreeningRule(
        name="robô social genérico",
        patterns=(
            r"\bsocial robot",
            r"\bsocially interactive robot",
            r"\bsars?\b",
            r"\bhumanoid robot",
            # sozinho pega robótica física (braços, monitoramento)
            r"\bassistive robot",
        ),
        requires_context=True,
    ),
)

HEALTHCARE_CONTEXT: tuple[str, ...] = (
    r"\bhealth",
    r"\bassisted living",
    r"\bcare\b",
    r"\bcaregiv",
    r"\bnursing",
    r"\bhospital",
    r"\bclinic",
    r"\bpatient",
    r"\btherap",
    r"\brehabilitat",
    r"\bdementia",
    r"\balzheimer",
    r"\bcognitive (impair|assess|decline)",
    r"\bolder (adult|people|person|user)",
    r"\bpain\b",
    r"\bspecial needs",
    r"\bassisted living",
    r"\belder",
    r"\baged\b",
    r"\bageing|\baging",
    r"\bseniors?\b",
    r"\bautis",
    r"\bdepress",
    r"\blonel",
    r"\bwell-?being",
    r"\bstroke\b",
    r"\bmental",
    r"\bmedical",
    r"\bp(a)?ediatric",
    r"\bdisabilit",
)

def load_works(jsonl_paths: list[Path]) -> dict[str, Work]:
    """Carrega os arquivos de entrada e mantém a ocorrência de menor rodada."""
    works: dict[str, Work] = {}
    for path in jsonl_paths:
        for work_id, work in Work.load_jsonl(str(path)).items():
            previous = works.get(work_id)
            if previous is None or work.backward_round < previous.backward_round:
                works[work_id] = work
    return works


def validate_rules(rules: tuple[TitleScreeningRule, ...]) -> None:
    names: set[str] = set()
    for rule in rules:
        if not rule.name.strip():
            raise ValueError("Cada regra de inclusão precisa ter um nome.")
        if rule.name in names:
            raise ValueError(f"Nome de regra duplicado: {rule.name}")
        names.add(rule.name)
        if not rule.patterns or any(not pattern.strip() for pattern in rule.patterns):
            raise ValueError(
                f"A regra {rule.name!r} precisa ter padrões não vazios."
            )
    # falha cedo se algum regex estiver mal escrito
    for pattern in [p for rule in rules for p in rule.patterns] + list(HEALTHCARE_CONTEXT):
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Regex inválido {pattern!r}: {e}") from e


def screen_title(
    work: Work, rules: tuple[TitleScreeningRule, ...]
) -> tuple[str, str, str]:
    """Mantém títulos com algum termo configurado e exclui os demais.

    Termos genéricos sem contexto de saúde no título ficam como
    "needs_context": seguem para a triagem de abstract, mas não
    alimentam a fronteira do snowballing.
    """
    if not work.title or not work.title.strip():
        return "pending_title", "", ""
    if not rules:
        return "pending_rules", "", ""

    title = work.title
    # a ordem das regras importa: as específicas vêm antes das genéricas
    for rule in rules:
        for pattern in rule.patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if not match:
                continue
            if not rule.requires_context:
                return "passed_title", rule.name, match.group(0)
            if any(re.search(c, title, re.IGNORECASE) for c in HEALTHCARE_CONTEXT):
                return "passed_title", rule.name, match.group(0)
            return "needs_context", rule.name, match.group(0)
    return "excluded_by_title", "", ""


def build_row(
        work: Work, rules: tuple[TitleScreeningRule, ...]
) -> dict[str, str | int]:
    status, matched_rule, matched_keyword = screen_title(work, rules)
    return {
        "id": work.id,
        "doi": work.doi or "",
        "title": work.title or "",
        "publication_year": work.publication_year or "",
        "backward_round": work.backward_round,
        "status": status,
        "matched_rule": matched_rule,
        "matched_keyword": matched_keyword,
    }


def load_screening_rows(
    jsonl_path: Path, json_path: Path
) -> dict[str, dict[str, str | int]]:
    """Lê a triagem acumulada; usa o JSON bruto como fallback."""
    if jsonl_path.exists():
        with jsonl_path.open(encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
    elif json_path.exists():
        records = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        records = []

    rows: dict[str, dict[str, str | int]] = {}
    for row in records:
        work_id = row.get("id")
        if not work_id:
            raise ValueError("Registro de triagem sem campo 'id'.")
        rows[work_id] = row
    return rows


def save_screening_rows(
    rows: dict[str, dict[str, str | int]], jsonl_path: Path, json_path: Path
) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(list(rows.values()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run(
    input_paths: list[Path] = INPUT_PATHS,
    output_json_path: Path = OUTPUT_JSON_PATH,
    output_jsonl_path: Path = OUTPUT_JSONL_PATH,
    rules: tuple[TitleScreeningRule, ...] = INCLUSION_RULES,
) -> int:
    validate_rules(rules)
    works = load_works(input_paths)
    rows = load_screening_rows(output_jsonl_path, output_json_path)

    for work_id, work in works.items():
        if work_id not in rows:
        #       rows[work_id]["backward_round"] = 98
        #else:
            rows[work_id] = build_row(work, rules)

    save_screening_rows(rows, output_jsonl_path, output_json_path)
    return len(rows)

def filter(path: Path) -> None:
    """
        procura em title_screening.jsonl e gera candidates.jsonl,
        arquivo com todos os artigos que não foram excluidos na primeira etapa
        (passed_title e needs_context; a triagem de abstract decide os segundos)
    """
    # lista com todos os artigos passados
    passed_titles = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f: 
            article = json.loads(line)
            if article['status'] in ("passed_title", "needs_context"):
                passed_titles.append(article)
    
    # "w": title_screening.jsonl é o arquivo acumulado, esse aqui guarda as iterações 
    with open(OUTPUT_JSONL_FILTERED_PATH, "w", encoding="utf-8") as f:
        for article in passed_titles:
            f.write(json.dumps(article) + "\n")


def main() -> None:
    count = run()
    filter(OUTPUT_JSONL_PATH)
    if not INCLUSION_RULES:
        print(
            f"Triagem de títulos gerada para {count} works em "
            f"{OUTPUT_JSON_PATH} e {OUTPUT_JSONL_PATH}; "
            "nenhuma regra foi configurada, então todos permanecem pendentes."
        )
    else:
        print(
            f"Triagem de títulos gerada para {count} works em "
            f"{OUTPUT_JSON_PATH} e {OUTPUT_JSONL_PATH}."
        )


if __name__ == "__main__":
    main()
