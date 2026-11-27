import csv, sys, re
from difflib import SequenceMatcher
from pathlib import Path
import pymupdf
from sar_review_pipeline.fulltext.download import Downloader

rows = {r["openalex_id"]: r for r in csv.DictReader(open(sys.argv[1]))}
for path in sorted(Path("data/fulltext/docs").iterdir()):
    key = path.stem
    want = Downloader.normalize_title(rows[key]["title"])
    if path.suffix == ".pdf":
        doc = pymupdf.open(path)
        text = " ".join(doc[i].get_text() for i in range(min(2, len(doc))))
        pages = len(doc)
    else:
        text = path.read_text(errors="ignore")[:200000]
        text = re.sub(r"<[^>]+>", " ", text)
        pages = "-"
    got = Downloader.normalize_title(text)
    # janela deslizante: melhor trecho do tamanho do título
    n = len(want)
    best = 0.0
    for i in range(0, max(1, len(got) - n + 1), 20):
        best = max(best, SequenceMatcher(None, want, got[i:i + n]).ratio())
        if best > 0.95:
            break
    flag = "" if best >= 0.8 else "  <-- CONFERIR"
    print(f"{key} {path.suffix} pags={pages} sim={best:.2f}{flag}")
