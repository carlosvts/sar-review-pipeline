"""Citações de um artigo no Semantic Scholar (complemento do OpenAlex no forward)."""
import time

from sar_review_pipeline.snowball.openalex import ENV, session_with_retry
from sar_review_pipeline.work import normalize_doi

# opcional: sem ela, a cota é compartilhada (muitos 429 e pausa maior entre chamadas)
S2_API_KEY = ENV.get("S2_API_KEY")


class SemanticScholarClient:
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    PAGE = 1000  # máximo do endpoint de citações

    def __init__(self):
        self.session = session_with_retry()
        if S2_API_KEY:
            self.session.headers["x-api-key"] = S2_API_KEY
        # com chave: 1 requisição por segundo; sem chave, mais folga
        self.pause = 1.1 if S2_API_KEY else 3.0

    def citing_dois(self, doi: str) -> tuple[set[str], int, int]:
        """
        DOIs dos artigos que citam `doi`. Devolve (dois, total de citações, citações sem DOI);
        as sem DOI não têm como ser cruzadas com o OpenAlex e só entram na contagem.
        """
        dois: set[str] = set()
        total = no_doi = 0
        offset = 0
        while True:
            response = self.session.get(
                f"{self.BASE_URL}/paper/DOI:{doi}/citations",
                params={"fields": "externalIds", "limit": self.PAGE, "offset": offset},
                timeout=60,
            )
            time.sleep(self.pause)
            if response.status_code == 404:  # o S2 não conhece o DOI
                break
            response.raise_for_status()
            data = response.json()
            for item in data.get("data") or []:
                total += 1
                citing_doi = ((item.get("citingPaper") or {}).get("externalIds") or {}).get("DOI")
                if citing_doi:
                    dois.add(normalize_doi(citing_doi))
                else:
                    no_doi += 1
            if data.get("next") is None:
                break
            offset = data["next"]
        return dois, total, no_doi
