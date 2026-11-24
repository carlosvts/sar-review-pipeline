"""
Coleta da rodada 3: referências (backward) e citações (forward, OpenAlex + Semantic Scholar)
dos incluídos da rodada 2 (include + seed_only/EC4), menos tudo que já foi visto.

O "já visto" é reconstruído pelo OpenAlex, porque os arquivos das rodadas anteriores estão em
outro PC: start set + artigos do artefato + referências e citações do start set (candidatos da
rodada 1) e dos incluídos da rodada 1 (candidatos da rodada 2). Usa as classes do pipeline;
grava em data/rodada3/ no formato Work (um por linha), como a etapa 01.
"""
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import requests

from sar_review_pipeline.snowball.forward import SELECT
from sar_review_pipeline.snowball.openalex import OpenAlexClient, short_id
from sar_review_pipeline.snowball.semantic_scholar import SemanticScholarClient
from sar_review_pipeline.work import Work, normalize_doi

OUT = Path("data/rodada3")
SEED_BATCH = 50
ID_SELECT = "id,doi"


class Neighbors:
    """Referências e citações de um conjunto de seeds (ids e DOIs)."""

    def __init__(self):
        self.openalex = OpenAlexClient()
        self.s2 = SemanticScholarClient()
        self.s2_failed: list[str] = []

    def seed_records(self, ids: list[str]) -> list[dict]:
        records = []
        for i in range(0, len(ids), SEED_BATCH):
            chunk = "|".join(short_id(x) for x in ids[i : i + SEED_BATCH])
            records.extend(self.openalex.get(f"openalex:{chunk}", per_page=SEED_BATCH, select=SELECT))
            time.sleep(0.2)
        return records

    def references(self, seeds: list[dict]) -> set[str]:
        refs = set()
        for s in seeds:
            for r in s.get("referenced_works") or []:
                refs.add(r)
        return refs

    def citations_openalex(self, seeds: list[dict], select: str) -> list[dict]:
        found = []
        for i in range(0, len(seeds), SEED_BATCH):
            chunk = "|".join(short_id(s["id"]) for s in seeds[i : i + SEED_BATCH])
            for raw in self.openalex.get_all(f"cites:{chunk}", select=select):
                found.append(raw)
        return found

    def citations_s2(self, seeds: list[dict]) -> set[str]:
        dois = set()
        for s in seeds:
            doi = normalize_doi(s.get("doi"))
            if not doi:
                continue
            try:
                citing, _, _ = self.s2.citing_dois(doi)
            except requests.RequestException as e:
                print(f"  S2 falhou para {s['id']} ({type(e).__name__})")
                self.s2_failed.append(s["id"])
                time.sleep(60)
                continue
            dois |= citing
        return dois


class Seen:
    """Ids e DOIs já vistos nas rodadas anteriores."""

    def __init__(self):
        self.ids: set[str] = set()
        self.dois: set[str] = set()

    def add_record(self, raw: dict) -> None:
        self.ids.add(raw["id"])
        doi = normalize_doi(raw.get("doi"))
        if doi:
            self.dois.add(doi)

    def add_round(self, nb: Neighbors, seeds: list[dict]) -> dict:
        refs = nb.references(seeds)
        cits = nb.citations_openalex(seeds, ID_SELECT)
        s2 = nb.citations_s2(seeds)
        for s in seeds:
            self.add_record(s)
        self.ids |= refs
        for raw in cits:
            self.add_record(raw)
        self.dois |= s2
        cit_ids = set()
        for raw in cits:
            cit_ids.add(raw["id"])
        return {"refs": refs, "cits": cit_ids, "s2_dois": s2}


class Round3:
    @classmethod
    def candidates(cls, nb: Neighbors, seen: Seen, seeds: list[dict]) -> dict[str, Work]:
        refs = nb.references(seeds) - seen.ids
        works: dict[str, Work] = {}
        directions: dict[str, set[str]] = {}

        ref_list = sorted(refs)
        for i in range(0, len(ref_list), SEED_BATCH):
            chunk = "|".join(short_id(x) for x in ref_list[i : i + SEED_BATCH])
            for raw in nb.openalex.get(f"openalex:{chunk}", per_page=SEED_BATCH, select=SELECT):
                works[raw["id"]] = Work.from_openalex(raw, round=3, direction="backward")
                directions.setdefault(raw["id"], set()).add("backward")
            time.sleep(0.2)

        for raw in nb.citations_openalex(seeds, SELECT):
            if raw["id"] in seen.ids or normalize_doi(raw.get("doi")) in seen.dois:
                continue
            if raw["id"] not in works:
                works[raw["id"]] = Work.from_openalex(raw, round=3, direction="forward")
            directions.setdefault(raw["id"], set()).add("forward")

        known_dois = set(seen.dois)
        for w in works.values():
            if w.doi:
                known_dois.add(w.doi)
        new_dois = []
        for doi in sorted(nb.citations_s2(seeds) - known_dois):
            if "|" not in doi and "," not in doi:
                new_dois.append(doi)
        for i in range(0, len(new_dois), SEED_BATCH):
            chunk = "|".join(new_dois[i : i + SEED_BATCH])
            for raw in nb.openalex.get(f"doi:{chunk}", per_page=SEED_BATCH, select=SELECT):
                if raw["id"] in seen.ids or raw["id"] in works:
                    directions.setdefault(raw["id"], set()).add("forward")
                    continue
                works[raw["id"]] = Work.from_openalex(raw, round=3, direction="forward")
                directions.setdefault(raw["id"], set()).add("forward")
            time.sleep(0.2)

        for work_id, w in works.items():
            if directions[work_id] == {"backward", "forward"}:
                w.direction = "both"
        return works

    @classmethod
    def coverage(cls, expected: list[str], found: dict) -> dict:
        pool = found["refs"] | found["cits"]
        hit = []
        miss = []
        for k in expected:
            if "https://openalex.org/" + k in pool:
                hit.append(k)
            else:
                miss.append(k)
        return {"esperados": len(expected), "achados": len(hit), "faltando": miss}

    @classmethod
    def save(cls, works: dict[str, Work], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for w in works.values():
                f.write(json.dumps(asdict(w), ensure_ascii=False) + "\n")

    @classmethod
    def count(cls, works: dict[str, Work]) -> dict:
        counts = {"total": len(works), "por_direction": {}}
        for w in works.values():
            counts["por_direction"][w.direction] = counts["por_direction"].get(w.direction, 0) + 1
        return counts


def main():
    seeds_file = json.load(open(sys.argv[1], encoding="utf-8"))
    nb = Neighbors()
    seen = Seen()

    start = nb.seed_records(seeds_file["start_set"])
    r1_seeds = nb.seed_records(seeds_file["round1_seeds"])
    r2_seeds = nb.seed_records(seeds_file["round2_seeds"])
    print(f"seeds: start {len(start)}, r1 {len(r1_seeds)}, r2 {len(r2_seeds)}")

    found1 = seen.add_round(nb, start)
    print("rodada 1 reconstruída:", Round3.coverage(seeds_file["round1_candidates"], found1))
    found2 = seen.add_round(nb, r1_seeds)
    print("rodada 2 reconstruída:", Round3.coverage(seeds_file["round2_candidates"], found2))
    for k in seeds_file["all_artifact"]:
        seen.ids.add("https://openalex.org/" + k)
    for s in r2_seeds:
        seen.add_record(s)
    print(f"já vistos: {len(seen.ids)} ids, {len(seen.dois)} DOIs")

    works = Round3.candidates(nb, seen, r2_seeds)
    Round3.save(works, OUT / "works.jsonl")
    print("rodada 3:", json.dumps(Round3.count(works)))
    print("S2 falhou em:", nb.s2_failed)


if __name__ == "__main__":
    main()
