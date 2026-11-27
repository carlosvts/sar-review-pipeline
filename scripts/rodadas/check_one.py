import sys, csv
from difflib import SequenceMatcher
import pymupdf
from sar_review_pipeline.fulltext.download import Downloader
from sar_review_pipeline.fulltext.validate import Validator
rows = {r["openalex_id"]: r for r in csv.DictReader(open(sys.argv[1]))}
for path in sys.argv[2:]:
    key = path.rsplit("/", 1)[-1].split(".")[0]
    ok, reason, kind = Validator.validate(path)
    doc = pymupdf.open(path); text = " ".join(doc[i].get_text() for i in range(min(3, len(doc))))
    want = Downloader.normalize_title(rows[key]["title"]); got = Downloader.normalize_title(text); n = len(want); best = 0
    for i in range(0, max(1, len(got)-n+1), 20):
        best = max(best, SequenceMatcher(None, want, got[i:i+n]).ratio())
        if best > .95: break
    print(key, ok, reason, kind, f"pags={len(doc)} sim={best:.2f}")
