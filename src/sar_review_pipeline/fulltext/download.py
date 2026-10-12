import time
from pathlib import Path

import requests

from sar_review_pipeline.fulltext.validate import Validator
from sar_review_pipeline.work import Work


class Downloader:
    DEFAULT_DIR = Path("data/fulltext/pdfs")
    USER_AGENT = "sar-review-pipeline (mailto:carlosvtsdev@gmail.com)"
    TIMEOUT = (10, 60)  # (conexão, leitura) em segundos
    CHUNK_SIZE = 64 * 1024
    DELAY = 1.0  # pausa entre works, em segundos

    @classmethod
    def pdf_candidates(cls, work: Work) -> list[str]:
        """pdf_urls das oa_locations, na ordem em que estão (a best vem primeiro)."""
        return [loc["pdf_url"] for loc in work.oa_locations if loc.get("pdf_url")]

    @classmethod
    def output_path(cls, work: Work, dest_dir: Path = DEFAULT_DIR) -> Path:
        """https://openalex.org/W123 -> <dest_dir>/W123.pdf"""
        return dest_dir / f"{work.id.rsplit('/', 1)[-1]}.pdf"

    @classmethod
    def fetch(cls, url: str, tmp_path: Path) -> None:
        """Baixa a url para tmp_path. Levanta requests.RequestException se falhar."""
        with requests.get(
            url,
            headers={"User-Agent": cls.USER_AGENT},
            stream=True,
            timeout=cls.TIMEOUT,
        ) as response:
            response.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_content(cls.CHUNK_SIZE):
                    f.write(chunk)

    @classmethod
    def download_work(cls, work: Work, dest_dir: Path = DEFAULT_DIR) -> dict:
        """
        Tenta as pdf_urls do work, em ordem, e fica com a primeira que baixar e
        validar. Devolve {id, ok, url, path, reason, skipped, attempted}.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        final = cls.output_path(work, dest_dir)
        tmp = final.with_suffix(".part")
        result = {
            "id": work.id,
            "ok": False,
            "url": None,
            "path": None,
            "reason": "",
            "skipped": False,
            "attempted": 0,
        }

        # idempotência: se já baixou e o arquivo continua válido, não baixa de novo
        if final.exists() and Validator.validate_pdf(str(final))[0]:
            result.update(ok=True, path=str(final), skipped=True)
            return result

        candidates = cls.pdf_candidates(work)
        if not candidates:
            result["reason"] = "sem pdf_url"
            return result

        reasons = []
        for url in candidates:
            result["attempted"] += 1
            try:
                cls.fetch(url, tmp)
            except requests.RequestException as e:
                reasons.append(f"{url}: {e}")
                tmp.unlink(missing_ok=True)
                continue

            ok, reason = Validator.validate_pdf(str(tmp))
            if ok:
                tmp.replace(final)
                result.update(ok=True, url=url, path=str(final))
                return result
            reasons.append(f"{url}: {reason}")
            tmp.unlink(missing_ok=True)

        result["reason"] = "; ".join(reasons)
        return result

    @classmethod
    def download_all(
        cls, works: dict[str, Work], dest_dir: Path = DEFAULT_DIR
    ) -> list[dict]:
        """Roda download_work em todos os works, com pausa entre os que fizeram requisição."""
        results = []
        total = len(works)
        for i, work in enumerate(works.values(), start=1):
            result = cls.download_work(work, dest_dir)
            results.append(result)
            if result["skipped"]:
                status = "já baixado"
            elif result["ok"]:
                status = "baixado"
            else:
                status = f"falhou ({result['reason'][:80]})"
            print(f"[{i}/{total}] {work.id}  {status}")
            if result["attempted"]:
                time.sleep(cls.DELAY)
        return results
