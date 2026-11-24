"""Junta status do texto, evidência do RAG e recomendações da rodada 2 no data.json do artefato."""
import csv
import json
import sys
from pathlib import Path

S = Path(sys.argv[1])
DATA = S / "artifact-files/9d84cd5d-6ac0-452e-b997-ff595f43f5fa/data.json"
REC_FIELDS = ("decision", "code", "qp", "why", "confidence", "basis")


class Merge:
    @classmethod
    def load_recs(cls) -> dict:
        recs = {}
        for i in range(1, 6):
            for r in json.load(open(S / f"rec_out_{i}.json", encoding="utf-8")):
                recs[r["key"]] = r
        return recs

    @classmethod
    def text_status(cls) -> dict:
        status = {}
        for r in csv.DictReader(open("data/fulltext/rodada2_manual_log.csv", encoding="utf-8")):
            status[r["openalex_id"]] = {"auto": "downloaded", "manual": "manual", "failed": "failed"}[r["status"]]
        return status

    @classmethod
    def run(cls) -> dict:
        d = json.load(open(DATA, encoding="utf-8"))
        ev = json.load(open(S / "gpu_in/evidence_r2.json", encoding="utf-8"))
        recs = cls.load_recs()
        status = cls.text_status()
        counts = {"evidence": 0, "rec": 0, "changed": 0, "locked": 0}
        for p in d["papers"]:
            if p["round"] != 2:
                continue
            p["text_status"] = status[p["key"]]
            if p.get("locked"):
                counts["locked"] += 1
                continue
            p["evidence"] = ev[p["key"]]
            counts["evidence"] += 1
            r = recs[p["key"]]
            rec = {}
            for f in REC_FIELDS:
                rec[f] = r[f]
            p["rec"] = rec
            counts["rec"] += 1
            if r.get("changed"):
                counts["changed"] += 1
        json.dump(d, open(DATA, "w", encoding="utf-8"), ensure_ascii=False)
        return counts


if __name__ == "__main__":
    print(Merge.run())
