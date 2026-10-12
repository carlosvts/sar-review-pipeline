import json
from pathlib import Path 
from sar_review_pipeline.work import Work
import csv

class Manifest:
    FIELDNAMES = [
        "id",
        "doi",
        "title",
        "publication_year",
        "backward_round",
        "n_pdf_candidates",
        "n_landing_only",
        "status",
        "source_used",
        "local_path",
    ]
    DEFAULT_PATH = Path("data/fulltext/manifest.csv")

    @classmethod
    def build_row(cls, work: Work) -> dict:
        """Linha inicial (status pending) de um work."""
        n_pdf = sum(1 for loc in work.oa_locations if loc.get("pdf_url"))
        n_landing_only = sum(
            1
            for loc in work.oa_locations
            if not loc.get("pdf_url") and loc.get("landing_page_url")
        )
        return {
            "id": work.id,
            "doi": work.doi or "",
            "title": work.title or "",
            "publication_year": work.publication_year or "",
            "backward_round": work.backward_round,
            "n_pdf_candidates": n_pdf,
            "n_landing_only": n_landing_only,
            "status": "pending",
            "source_used": "",
            "local_path": "",
        }

    @classmethod
    def read_manifest(cls, path: Path) -> dict[str, dict]:
        """Linhas já existentes no manifesto, indexadas por id."""
        if not path.exists():
            return {}
        with open(path, newline="", encoding="utf-8") as f:
            return {row["id"]: row for row in csv.DictReader(f)}

    @classmethod
    def generate_manifest(
        cls,
        jsonl_paths: list[Path],
        out_path: Path = DEFAULT_PATH,
    ) -> None:
        # junta os works; se o id repete, fica o de menor backward_round
        works: dict[str, Work] = {}
        for p in jsonl_paths:
            for work_id, work in Work.load_jsonl(str(p)).items():
                if work_id not in works or work.backward_round < works[work_id].backward_round:
                    works[work_id] = work

        # idempotência: o que já está no manifesto não é tocado
        rows = cls.read_manifest(out_path)
        for work_id, work in works.items():
            if work_id not in rows:
                rows[work_id] = cls.build_row(work)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cls.FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows.values())


if __name__ == "__main__":
    Manifest.generate_manifest([Path("data/jsonl/start_set.jsonl"), Path("data/jsonl/backward.jsonl")])
