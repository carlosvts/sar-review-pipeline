import json
import random
from collections import Counter
from pathlib import Path

from sar_review_pipeline.fulltext.download import Downloader
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


SAMPLE_SIZE = 50
SEED = 42  # semente fixa: a mesma amostra em toda execução


def sample_works(works: dict[str, Work], n: int, seed: int = SEED) -> dict[str, Work]:
    """Amostra aleatória reprodutível de n works."""
    ids = sorted(works)  # ordena antes de sortear, para não depender da ordem do arquivo
    chosen = random.Random(seed).sample(ids, min(n, len(ids)))
    return {i: works[i] for i in chosen}


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


def main():
    ROOT = Path()
    DATA = ROOT / "data/"
    START_SET_JSONL = DATA / "jsonl/start_set.jsonl"
    BACKWARD_JSONL = DATA / "jsonl/backward.jsonl"
    # extract_jsonl(START_SET_JSONL)
    # extract_jsonl(BACKWARD_JSONL)

    # 1. manifesto (start set + backward)
    Manifest.generate_manifest([START_SET_JSONL, BACKWARD_JSONL])
    rows = Manifest.read_manifest(Manifest.DEFAULT_PATH)
    print(f"Manifest: {Manifest.DEFAULT_PATH.resolve()}  Linhas: {len(rows)}\n")

    # 2. amostra do backward (troque SAMPLE_SIZE ou use todos os works para rodar completo)
    backward = Work.load_jsonl(str(BACKWARD_JSONL))
    works = sample_works(backward, SAMPLE_SIZE)
    print(f"Amostra: {len(works)} de {len(backward)} works do backward (seed={SEED})\n")
    results = Downloader.download_all(works)

    # 3. resumo
    summarize(results, works)

if __name__ == '__main__':
    main()
