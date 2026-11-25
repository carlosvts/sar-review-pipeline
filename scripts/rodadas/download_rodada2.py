"""Roda a cascata do Downloader sobre os works de uma rodada, sem tocar em arquivos que já existem.

Grava em data/fulltext/docs/ (padrão das rodadas 2 e 3), não em data/rounds/fulltext/docs/ do pipeline por rodada.
"""
import json
import sys
from pathlib import Path

from sar_review_pipeline.fulltext.download import Downloader
from sar_review_pipeline.work import Work

DOCS = Path("data/fulltext/docs")


class Rodada2Download:
    @classmethod
    def load_works(cls, path: Path) -> dict[str, Work]:
        # os JSONL das rodadas 2 e 3 são de antes do merge: o campo `round` se chamava `backward_round`
        works = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                if "backward_round" in data:
                    data["round"] = data.pop("backward_round")
                work = Work(**data)
                works[work.id] = work
        return works

    @classmethod
    def already_on_disk(cls, work: Work, dest_dir: Path) -> bool:
        key = Downloader.work_key(work)
        for ext in ("pdf", "xml"):
            if (dest_dir / f"{key}.{ext}").exists():
                return True
        return False

    @classmethod
    def split(cls, works: dict[str, Work], dest_dir: Path) -> dict:
        todo = {}
        kept = []
        for work_id, work in works.items():
            if cls.already_on_disk(work, dest_dir):
                kept.append(work_id)
            else:
                todo[work_id] = work
        return {"todo": todo, "kept": kept}

    @classmethod
    def count(cls, results: list[dict], works: dict[str, Work]) -> dict:
        counts = {"total": len(results), "ok": 0, "failed": 0, "por_fonte": {}, "por_direction": {}}
        for r in results:
            direction = works[r["id"]].direction
            by_dir = counts["por_direction"].setdefault(direction, {"ok": 0, "failed": 0})
            if r["ok"]:
                counts["ok"] += 1
                by_dir["ok"] += 1
                counts["por_fonte"][r["source"]] = counts["por_fonte"].get(r["source"], 0) + 1
            else:
                counts["failed"] += 1
                by_dir["failed"] += 1
        return counts


def main():
    works_path, results_path = Path(sys.argv[1]), Path(sys.argv[2])
    works = Rodada2Download.load_works(works_path)
    parts = Rodada2Download.split(works, DOCS)
    print(f"works: {len(works)}  já no disco (não mexo): {len(parts['kept'])}  a baixar: {len(parts['todo'])}")
    results = Downloader.download_all(parts["todo"], DOCS)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(json.dumps(Rodada2Download.count(results, works), ensure_ascii=False))
    print(f"resultados: {results_path}")


if __name__ == "__main__":
    main()
