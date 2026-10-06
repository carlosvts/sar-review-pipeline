import json 
from pathlib import Path

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
    oa_available = registers - empty
    print(f"{filepath.resolve()}   Total: {registers}  Available: {oa_available}  Empty: {empty}, Downloadable: {downloadable_pdf}")


def main():
    ROOT = Path()
    DATA = ROOT / "data/"
    START_SET_JSONL = DATA / "jsonl/start_set.jsonl"
    BACKWARD_JSONL = DATA / "jsonl/backward.jsonl"
    extract_jsonl(START_SET_JSONL)
    extract_jsonl(BACKWARD_JSONL)

if __name__ == '__main__':
    main()
