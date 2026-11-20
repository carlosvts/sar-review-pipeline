import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from collections import Counter

from sar_review_pipeline.rounds import Round, pop_round
from sar_review_pipeline.work import Work

# as regras são as mesmas em todas as rodadas; só os arquivos mudam (rounds.py)

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
            r"\bsocial(ly)?(\s+[\w-]+){0,2}\s+robot",
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
            if previous is None or work.round < previous.round:
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
        "round": work.round,
        "direction": work.direction,
        "status": status,
        "matched_rule": matched_rule,
        "matched_keyword": matched_keyword,
    }


def load_screening_rows(rnd: Round) -> dict[str, dict[str, str | int]]:
    """Lê a triagem acumulada da rodada; usa o JSON bruto como fallback."""
    jsonl_path, json_path = rnd.title_screening_jsonl, rnd.title_screening_json
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
    rnd: Round,
    rules: tuple[TitleScreeningRule, ...] = INCLUSION_RULES,
) -> int:
    validate_rules(rules)
    works = load_works([rnd.works])
    rows = load_screening_rows(rnd)

    for work_id, work in works.items():
        if work_id not in rows:
            rows[work_id] = build_row(work, rules)
        else:
            # a direção só é fechada no fim da coleta (both), depois da primeira triagem
            rows[work_id]["direction"] = work.direction

    save_screening_rows(rows, rnd.title_screening_jsonl, rnd.title_screening_json)
    return len(rows)

def filter(rnd: Round) -> None:
    """
        procura em title_screening.jsonl e gera candidates.jsonl (da rodada),
        arquivo com todos os artigos que não foram excluidos na primeira etapa
        (passed_title e needs_context; a triagem de abstract decide os segundos)
    """
    # lista com todos os artigos passados
    passed_titles = []
    with open(rnd.title_screening_jsonl, "r", encoding="utf-8") as f:
        for line in f: 
            article = json.loads(line)
            if article['status'] in ("passed_title", "needs_context"):
                passed_titles.append(article)
    
    # "w": title_screening.jsonl é o arquivo acumulado, esse aqui guarda as iterações 
    with open(rnd.candidates, "w", encoding="utf-8") as f:
        for article in passed_titles:
            f.write(json.dumps(article) + "\n")


def screen_abstracts(
    title_screening_path: Path, works: dict[str, Work]
) -> dict[str, str]:
    """
    TODO (etapa 03): triagem por abstract. Ainda não implementada.

    Entrada: `title_screening_path` (data/raw/title_screening.json). Só entram
    os registros com status "passed_title" ou "needs_context"; os
    "excluded_by_title" e "pending_title" ficam de fora.

    As linhas de title_screening.json não guardam o abstract. Ele vem do
    `Work` em `works` (sn.backward), pelo id: `works[row["id"]].abstract`.

    TODO: Precisamos decidir o que fazer com os abstracts que o OpenAlex não resolve
    """
    raise NotImplementedError("triagem por abstract: etapa 03, a implementar")


def print_summary(rnd: Round) -> None:
    rows = load_screening_rows(rnd).values()
    by_status = Counter(r["status"] for r in rows)
    by_direction = Counter((r["direction"], r["status"]) for r in rows)
    print(f"Triagem por título ({rnd.name}): {dict(by_status)}")
    for (d, status), n in sorted(by_direction.items()):
        print(f"  {d:9s} {status:18s} {n}")
    print(f"Candidatos (passed_title + needs_context): {rnd.candidates}")


def main() -> None:
    # uv run step02-screen-titles --round N
    rnd, _ = pop_round(sys.argv[1:])
    count = run(rnd)
    filter(rnd)
    paths = f"{rnd.title_screening_json} e {rnd.title_screening_jsonl}"
    if not INCLUSION_RULES:
        print(
            f"Triagem de títulos ({rnd.name}) gerada para {count} works em {paths}; "
            "nenhuma regra foi configurada, então todos permanecem pendentes."
        )
    else:
        print(f"Triagem de títulos ({rnd.name}) gerada para {count} works em {paths}.")


if __name__ == "__main__":
    main()
