"""Busca os 83 candidatos da rodada 2 no OpenAlex e grava um Work por linha (sem baixar nada)."""
import csv
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import requests

from sar_review_pipeline.work import Work

OPENALEX_WORK = "https://api.openalex.org/works/{}"
ROUND = 2
DELAY = 0.2


class Rodada2:
    @classmethod
    def read_csv(cls, path: Path) -> list[dict]:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    @classmethod
    def fetch_raw(cls, openalex_id: str) -> dict | None:
        """/works/{id} segue o redirect de registro fundido; None se não existir."""
        response = requests.get(OPENALEX_WORK.format(openalex_id), timeout=(10, 60))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    @classmethod
    def fetch_all(cls, rows: list[dict]) -> dict:
        works = []
        missing = []
        merged = []
        for row in rows:
            raw = cls.fetch_raw(row["openalex_id"])
            time.sleep(DELAY)
            if raw is None:
                missing.append(row["openalex_id"])
                continue
            returned = raw["id"].rsplit("/", 1)[-1]
            if returned != row["openalex_id"]:
                merged.append({"csv": row["openalex_id"], "openalex": returned})
            works.append(Work.from_openalex(raw, round=ROUND, direction=row["direction"]))
        return {"works": works, "missing": missing, "merged": merged}

    @classmethod
    def save(cls, works: list[Work], path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for work in works:
                f.write(json.dumps(asdict(work), ensure_ascii=False) + "\n")

    @classmethod
    def count(cls, works: list[Work]) -> dict:
        counts = {"total": len(works), "por_direction": {}, "com_pdf_url": 0, "sem_oa_locations": 0, "sem_doi": 0}
        for work in works:
            counts["por_direction"][work.direction] = counts["por_direction"].get(work.direction, 0) + 1
            has_pdf = False
            for loc in work.oa_locations:
                if loc.get("pdf_url"):
                    has_pdf = True
            if has_pdf:
                counts["com_pdf_url"] += 1
            if not work.oa_locations:
                counts["sem_oa_locations"] += 1
            if not work.doi:
                counts["sem_doi"] += 1
        return counts


def main():
    csv_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    rows = Rodada2.read_csv(csv_path)
    result = Rodada2.fetch_all(rows)
    Rodada2.save(result["works"], out_path)
    print(f"linhas no CSV: {len(rows)}")
    print(f"devolvidos: {len(result['works'])}")
    print(f"não encontrados: {result['missing']}")
    print(f"ids diferentes (fundidos): {result['merged']}")
    print(f"contagem: {json.dumps(Rodada2.count(result['works']), ensure_ascii=False)}")
    print(f"saída: {out_path}")


if __name__ == "__main__":
    main()
