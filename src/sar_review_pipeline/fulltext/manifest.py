import csv
from pathlib import Path

from sar_review_pipeline.work import Work


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
        "url_used",
        "kind",
        "local_path",
        "note",
    ]
    # status que o pipeline nunca sobrescreve: "manual" = você recuperou à mão
    PROTECTED_STATUS = {"manual"}
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
            "url_used": "",
            "kind": "",
            "local_path": "",
            "note": "",
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

        cls.write_manifest(rows, out_path)

    @classmethod
    def write_manifest(cls, rows: dict[str, dict], path: Path = DEFAULT_PATH) -> None:
        """Grava o manifesto; colunas que faltam em linhas antigas saem vazias."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cls.FIELDNAMES, restval="", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows.values())
        tmp.replace(path)  # troca atômica: uma queda no meio não corrompe o manifesto

    @classmethod
    def update_from_results(cls, results: list[dict], path: Path = DEFAULT_PATH) -> dict[str, int]:
        """
        Grava no manifesto o resultado do Downloader.download_all:
          - baixou agora: status=downloaded + fonte, URL, tipo e caminho
          - já existia (skipped): status=downloaded, mantendo a fonte que já estava gravada
          - falhou: status=failed + motivo em note
          - linhas com status "manual" nunca são alteradas
        Devolve contadores {updated, protected, missing}; "missing" = id que não está no manifesto.
        """
        rows = cls.read_manifest(path)
        counts = {"updated": 0, "protected": 0, "missing": 0}
        for r in results:
            row = rows.get(r["id"])
            if row is None:
                counts["missing"] += 1
                continue
            if row.get("status") in cls.PROTECTED_STATUS:
                counts["protected"] += 1
                continue
            if r["ok"]:
                row.update(status="downloaded", kind=r["kind"] or "", local_path=r["path"] or "", note="")
                if not r["skipped"]:
                    row.update(source_used=r["source"] or "", url_used=r["url"] or "")
            else:
                row.update(status="failed", note=r["reason"])
            counts["updated"] += 1
        cls.write_manifest(rows, path)
        return counts
