"""
Junta status do texto, evidência do RAG e recomendações de uma rodada no data.json do artefato de triagem.
Só mexe nos artigos da rodada pedida; as outras rodadas e as decisões salvas no banco do artefato ficam como estão.

  uv run python scripts/rodadas/merge_artifact.py <data.json> <rodada> <evidence.json> <log.csv> <recs.json>...

Artigos da rodada que ainda não estão no data.json são adicionados a partir de data/rodada<N>/included.jsonl.

Os failed do log ficam locked, com o motivo de EC6 do log, sem evidência e sem recomendação.
"""
import csv
import json
import sys
from pathlib import Path

REC_FIELDS = ("decision", "code", "qp", "why", "confidence", "basis")
STATUS = {"auto": "downloaded", "manual": "manual", "failed": "failed"}
EC6_PREFIX = ("EC6: texto completo indisponível após tentativa de acesso (download automático e busca manual "
              "pela UFLA/Portal CAPES em {data}). ")


class Merge:
    @classmethod
    def load_recs(cls, paths: list[Path]) -> dict:
        recs = {}
        for path in paths:
            for r in json.load(open(path, encoding="utf-8")):
                recs[r["key"]] = r
        return recs

    @classmethod
    def load_log(cls, path: Path) -> dict:
        log = {}
        for r in csv.DictReader(open(path, encoding="utf-8")):
            log[r["openalex_id"]] = r
        return log

    @classmethod
    def locked_reason(cls, justificativa: str, data: str) -> str:
        detail = justificativa.removeprefix("EC6:").strip()
        year, month, day = data.split("-")
        return EC6_PREFIX.format(data=f"{day}/{month}/{year}") + detail

    @classmethod
    def add_missing(cls, d: dict, rnd: int) -> int:
        """Acrescenta ao data.json os artigos de data/rodada<N>/included.jsonl que ainda não estão lá."""
        keys = set()
        for p in d["papers"]:
            keys.add(p["key"])
        added = 0
        with open(Path(f"data/rodada{rnd}") / "included.jsonl", encoding="utf-8") as f:
            for line in f:
                w = json.loads(line)
                key = w["id"].rsplit("/", 1)[-1]
                if key in keys:
                    continue
                d["papers"].append({
                    "key": key, "round": rnd, "title": w["title"], "doi": w.get("doi"),
                    "year": w.get("publication_year"), "direction": w["direction"],
                    "authors": w["authors"][:3], "n_authors": len(w["authors"]), "type": w.get("type"),
                    "abstract": w.get("abstract"), "text_status": "", "locked": False, "locked_reason": "",
                    "evidence": None, "rec": None,
                })
                added += 1
        return added

    @classmethod
    def run(cls, data_path: Path, rnd: int, evidence_path: Path, log_path: Path, rec_paths: list[Path]) -> dict:
        d = json.load(open(data_path, encoding="utf-8"))
        ev = json.load(open(evidence_path, encoding="utf-8"))
        log = cls.load_log(log_path)
        recs = cls.load_recs(rec_paths)
        counts = {"adicionados": cls.add_missing(d, rnd), "artigos": 0, "evidence": 0, "rec": 0, "locked": 0,
                  "sem_evidencia": []}
        for p in d["papers"]:
            if p["round"] != rnd:
                continue
            counts["artigos"] += 1
            entry = log[p["key"]]
            p["text_status"] = STATUS[entry["status"]]
            if entry["status"] == "failed":
                p["locked"] = True
                p["locked_reason"] = cls.locked_reason(entry["justificativa"], entry["data"])
                p["evidence"] = None
                p["rec"] = None
                counts["locked"] += 1
                continue
            if p["key"] not in ev:
                counts["sem_evidencia"].append(p["key"])
                continue
            p["evidence"] = ev[p["key"]]
            counts["evidence"] += 1
            r = recs[p["key"]]
            rec = {}
            for f in REC_FIELDS:
                rec[f] = r[f]
            p["rec"] = rec
            counts["rec"] += 1
        json.dump(d, open(data_path, "w", encoding="utf-8"), ensure_ascii=False)
        return counts


def main():
    data_path, rnd, evidence_path, log_path = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    rec_paths = []
    for arg in sys.argv[5:]:
        rec_paths.append(Path(arg))
    print(json.dumps(Merge.run(data_path, rnd, evidence_path, log_path, rec_paths), ensure_ascii=False))


if __name__ == "__main__":
    main()
