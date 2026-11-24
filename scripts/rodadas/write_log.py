"""Gera data/fulltext/rodada2_manual_log.csv e rodada2_pendentes_manual.csv a partir dos resultados."""
import csv, json, sys
from pathlib import Path

S = Path(sys.argv[1]); TODAY = "2026-11-24"
rows = list(csv.DictReader(open(sys.argv[2])))
auto = {r["id"].rsplit("/", 1)[-1]: r for r in json.load(open(S / "rodada2_results.json"))}
agent = {}
for line in open(S / "manual_results.jsonl"):
    if line.strip():
        d = json.loads(line); agent[d["openalex_id"]] = d
manual = json.load(open(S / "manual_done.json"))
failed = json.load(open(S / "failed.json")) if (S / "failed.json").exists() else {}
docs = Path("data/fulltext/docs")

log, pend = [], []
for r in rows:
    k = r["openalex_id"]; a = auto[k]
    entry = {"openalex_id": k, "direction": r["direction"], "title": r["title"], "doi_url": r["doi_url"], "data": TODAY}
    if a["ok"]:
        entry.update(status="auto", fonte=a["source"], url=a["url"], justificativa="cascata automática")
    elif k in manual:
        entry.update(status="manual", fonte=manual[k]["fonte"], url=manual[k]["url"], justificativa="recuperado manualmente")
    elif k in failed:
        entry.update(status="failed", fonte="", url=r["doi_url"], justificativa=failed[k])
        pend.append(entry)
    else:
        g = agent.get(k, {})
        entry.update(status="pending", fonte="", url=g.get("landing_url") or r["doi_url"],
                     justificativa=f"{g.get('status', '')}: {g.get('note', '')}".strip(": "))
        pend.append(entry)
    log.append(entry)

fields = ["openalex_id", "direction", "status", "fonte", "url", "data", "justificativa", "title", "doi_url"]
for path, data in ((Path("data/fulltext/rodada2_manual_log.csv"), log), (Path("data/fulltext/rodada2_pendentes_manual.csv"), pend)):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(data)
counts = {}
for e in log:
    counts.setdefault(e["direction"], {}).setdefault(e["status"], 0); counts[e["direction"]][e["status"]] += 1
print(json.dumps(counts), len(pend))
