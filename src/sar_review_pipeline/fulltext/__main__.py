"""
    Etapa 04 de uma rodada: texto completo dos incluídos no cluster e a decisão de inclusão.

      step04-fulltext download --round N   baixa os works de r<N>/included.jsonl (N=0: start set)
      step04-fulltext extract              extrai o texto de tudo que já foi baixado (todas as rodadas)
      step04-fulltext screen --round N     gera/atualiza r<N>/fulltext/decisions.csv para a leitura
      step04-fulltext select --round N     grava r<N>/selected.jsonl (os seeds da rodada N+1)
"""
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from sar_review_pipeline.rounds import Round, pop_round
from sar_review_pipeline.fulltext.download import Downloader
from sar_review_pipeline.fulltext.extract import Extractor
from sar_review_pipeline.fulltext.manifest import Manifest
from sar_review_pipeline.work import Work


def extract_jsonl(filepath: Path):
    # le um jsonl e extrai as informacoes sobre o oa_locations
    registers = 0
    empty = 0
    downloadable_pdf = 0
    with open(filepath, encoding="utf-8") as f:
        for jsonl in f:
            data = json.loads(jsonl)
            locations = data['oa_locations']
            registers += 1
            if not locations:
                empty += 1
            pdf_urls = [loc.get('pdf_url') for loc in locations]
            if any(pdf_urls):
                downloadable_pdf += 1
            else:
                print(*(loc.get("landing_page_url") for loc in locations))
    oa_available = registers - empty
    print(f"{filepath.resolve()}   Total: {registers}  Available: {oa_available}  Empty: {empty}, Downloadable: {downloadable_pdf}")


def merge_works(*sources: dict[str, Work]) -> dict[str, Work]:
    """Junta os works; se o id repete, fica o de menor rodada (mesma regra do manifesto)."""
    works: dict[str, Work] = {}
    for source in sources:
        for work_id, work in source.items():
            if work_id not in works or work.round < works[work_id].round:
                works[work_id] = work
    return works


def summarize(results: list[dict], works: dict[str, Work]) -> None:
    ok = [r for r in results if r["ok"]]
    skipped = [r for r in ok if r["skipped"]]
    failed = [r for r in results if not r["ok"]]
    no_candidate = [r for r in failed if r["attempted"] == 0]
    by_source = Counter(r["source"] for r in ok if not r["skipped"])
    by_kind = Counter(r["kind"] for r in ok)
    total = len(results)

    print("\n=== Resumo ===")
    print(f"Works: {total}  Com texto: {len(ok)} ({len(ok) / total:.0%})  "
          f"[baixados agora: {len(ok) - len(skipped)}, já existiam: {len(skipped)}]")
    print(f"Falhas: {len(failed)} ({len(failed) / total:.0%})  "
          f"[sem candidata em nenhuma fonte: {len(no_candidate)}, candidatas falharam: {len(failed) - len(no_candidate)}]")
    print(f"Por fonte (baixados agora): {dict(by_source)}  Por tipo: {dict(by_kind)}")
    print(f"Arquivos em: {Downloader.DEFAULT_DIR.resolve()}")

    for r in failed:
        w = works[r["id"]]
        print(f"\nFALHOU {r['id']}  ({w.publication_year}) {w.title}")
        print(f"  doi: {w.doi}")
        for reason in r["reason"].split("; "):
            print(f"  {reason}")


def extract(force: bool = False) -> None:
    """Converte tudo que está em data/rounds/fulltext/docs/ em parágrafos (data/rounds/fulltext/text/)."""
    results = Extractor.extract_all(force=force)
    done = [r for r in results if r["n_paragraphs"]]
    flagged = [r for r in results if r["flags"]]
    print("\n=== Extração ===")
    print(f"Documentos: {len(results)}  Com texto: {len(done)}  "
          f"Por tipo: {dict(Counter(r['kind'] for r in done))}  Para conferir: {len(flagged)}")
    print(f"Saída em: {Extractor.TEXT_DIR.resolve()}")
    for r in flagged:
        print(f"  ⚠ {r['key']}.{r['kind']}: {'; '.join(r['flags'])}")


def download(rnd: Round) -> None:
    if not rnd.included.exists():
        step = "uv run step01-snowball start" if rnd.n == 0 else f"uv run step03-abstracts include --round {rnd.n}"
        sys.exit(f"{rnd.included} não existe: rode antes  {step}")

    # 1. manifesto da rodada
    Manifest.generate_manifest([rnd.included], rnd.manifest)
    rows = Manifest.read_manifest(rnd.manifest)
    print(f"Manifest ({rnd.name}): {rnd.manifest.resolve()}  Linhas: {len(rows)}\n")

    # 2. download (os arquivos ficam em data/rounds/fulltext/docs, comum a todas as rodadas)
    works = Work.load_jsonl(str(rnd.included))
    print(f"Works: {len(works)}\n")
    results = Downloader.download_all(works)

    # 3. resumo
    summarize(results, works)

    # 4. resultado no manifesto (status, fonte, caminho, motivo da falha)
    counts = Manifest.update_from_results(results, rnd.manifest)
    print(f"\nManifesto atualizado: {counts['updated']} linhas"
          f" (protegidas/manual: {counts['protected']}, fora do manifesto: {counts['missing']})")

    # 5. fila manual (o que nenhuma fonte resolveu)
    csv_path, ris_path = Downloader.export_manual_queue(results, works, rnd.fulltext_dir)
    print(f"\nFila manual: {csv_path.resolve()}")
    print(f"Para o Zotero: {ris_path.resolve()}")


# ---------- decisão do texto completo ----------

DECISION_FIELDS = ["id", "doi", "title", "publication_year", "direction", "text_status", "local_path",
                   "decision", "reason"]
DECISION_VALUES = ("include", "exclude")


def require_included(rnd: Round) -> None:
    if rnd.n < 1:
        sys.exit("a rodada 0 é o start set: já entra como selecionado")
    if not rnd.included.exists():
        sys.exit(f"{rnd.included} não existe: rode antes  uv run step03-abstracts include --round {rnd.n}")


def read_decisions(rnd: Round) -> dict[str, dict]:
    if not rnd.decisions.exists():
        return {}
    with open(rnd.decisions, newline="", encoding="utf-8") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def screen(rnd: Round) -> None:
    """
    Gera ou completa r<N>/fulltext/decisions.csv, uma linha por incluído no cluster.
    As colunas decision (include/exclude) e reason são preenchidas à mão depois da leitura do texto
    completo e nunca são sobrescritas; text_status e local_path vêm do manifesto a cada execução.
    """
    require_included(rnd)
    if not rnd.manifest.exists():
        sys.exit(f"{rnd.manifest} não existe: rode antes  uv run step04-fulltext download --round {rnd.n}")
    works = Work.load_jsonl(str(rnd.included))
    manifest = Manifest.read_manifest(rnd.manifest)
    rows = read_decisions(rnd)
    for work_id, w in works.items():
        m = manifest.get(work_id, {})
        row = rows.setdefault(work_id, {"decision": "", "reason": ""})
        row.update(id=w.id, doi=w.doi or "", title=w.title or "", publication_year=w.publication_year or "",
                   direction=w.direction, text_status=m.get("status", ""), local_path=m.get("local_path", ""))
    rnd.decisions.parent.mkdir(parents=True, exist_ok=True)
    tmp = rnd.decisions.with_suffix(".part")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DECISION_FIELDS, restval="", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows[i] for i in works if i in rows)
    tmp.replace(rnd.decisions)

    decided = Counter(r["decision"] or "pendente" for i, r in rows.items() if i in works)
    text = Counter(r["text_status"] or "?" for i, r in rows.items() if i in works)
    print(f"Decisões ({rnd.name}): {rnd.decisions.resolve()}")
    print(f"  texto: {dict(text)}")
    print(f"  decisão: {dict(decided)}")
    print("Preencha decision (include/exclude) e reason; depois  "
          f"uv run step04-fulltext select --round {rnd.n}")


def select(rnd: Round) -> None:
    """Grava r<N>/selected.jsonl com os include do decisions.csv; para se houver linha pendente."""
    require_included(rnd)
    works = Work.load_jsonl(str(rnd.included))
    rows = read_decisions(rnd)
    missing = [i for i in works if i not in rows]
    invalid = [i for i, r in rows.items() if i in works and r["decision"].strip().lower() not in DECISION_VALUES]
    if missing or invalid:
        print(f"{len(missing)} works sem linha e {len(invalid)} sem decisão válida ({'/'.join(DECISION_VALUES)})"
              f" em {rnd.decisions}")
        for i in (missing + invalid)[:20]:
            print(f"  {i}  {works[i].title}")
        sys.exit(1)
    selected = [works[i] for i in works if rows[i]["decision"].strip().lower() == "include"]
    tmp = rnd.selected.with_suffix(".part")
    with open(tmp, "w", encoding="utf-8") as f:
        for w in selected:
            f.write(json.dumps(asdict(w), ensure_ascii=False) + "\n")
    tmp.replace(rnd.selected)
    by_direction = Counter(w.direction for w in selected)
    print(f"Selecionados ({rnd.name}): {len(selected)} de {len(works)}  por direção: {dict(by_direction)}")
    print(f"Saída: {rnd.selected.resolve()}")
    if selected:
        print(f"Próxima rodada:  uv run step01-snowball round {rnd.n + 1}")
    else:
        print("Nenhum selecionado: o snowballing convergiu.")


USAGE = "uso: step04-fulltext download --round N | extract [--force] | screen --round N | select --round N"


def main():
    args = sys.argv[1:]
    if args and args[0] == "extract":
        extract(force="--force" in args)
        return
    if not args or args[0] not in ("download", "screen", "select"):
        sys.exit(USAGE)
    rnd, _ = pop_round(args[1:])
    {"download": download, "screen": screen, "select": select}[args[0]](rnd)


if __name__ == '__main__':
    main()
