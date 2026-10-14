import json
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


@dataclass(frozen=True)
class TitleScreeningRule:
    name: str
    keywords: tuple[str, ...]


EXCLUSION_RULES: tuple[TitleScreeningRule, ...] = (
    TitleScreeningRule(
        name="trata sobre SARs",
        keywords=("sar", "social robot", "companion robot", "socially assistive robot", "assistive robot", "socially assistive robotics", "pet robot",),
    ),
    TitleScreeningRule(
        name="escopo em healthcare",
        keywords=("social robot in care",),
    ),
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
            raise ValueError("Cada regra de exclusão precisa ter um nome.")
        if rule.name in names:
            raise ValueError(f"Nome de regra duplicado: {rule.name}")
        names.add(rule.name)
        if not rule.keywords or any(not keyword.strip() for keyword in rule.keywords):
            raise ValueError(
                f"A regra {rule.name!r} precisa ter palavras-chave não vazias."
            )


def screen_title(
    work: Work, rules: tuple[TitleScreeningRule, ...]
) -> tuple[str, str, str]:
    """Mantém títulos com algum termo configurado e exclui os demais."""
    if not work.title or not work.title.strip():
        return "pending_title", "", ""
    if not rules:
        return "pending_rules", "", ""

    title = work.title.casefold()
    for rule in rules:
        for keyword in rule.keywords:
            if keyword.casefold() in title:
                return "passed_title", rule.name, keyword
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
    rules: tuple[TitleScreeningRule, ...] = EXCLUSION_RULES,
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


def main() -> None:
    count = run()
    if not EXCLUSION_RULES:
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
