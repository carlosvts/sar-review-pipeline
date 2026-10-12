import json
from pathlib import Path

from sar_review_pipeline.fulltext.manifest import Manifest


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


def main():
    ROOT = Path()
    DATA = ROOT / "data/"
    START_SET_JSONL = DATA / "jsonl/start_set.jsonl"
    BACKWARD_JSONL = DATA / "jsonl/backward.jsonl"
    # extract_jsonl(START_SET_JSONL)
    # extract_jsonl(BACKWARD_JSONL)

    Manifest.generate_manifest([START_SET_JSONL, BACKWARD_JSONL])
    rows = Manifest.read_manifest(Manifest.DEFAULT_PATH)
    print(f"Manifest: {Manifest.DEFAULT_PATH.resolve()}  Linhas: {len(rows)}")


if __name__ == '__main__':
    main()
