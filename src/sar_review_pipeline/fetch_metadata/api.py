import json
from pathlib import Path

import requests

from sar_review_pipeline.work import Work


class OpenAlexAPI:
    def __init__(self, base_url: str = "https://api.openalex.org"):
        self.base_url = base_url
        self.works = {}
        self.metadata: dict[str, Work] = {}

    def get_referenced_works(self, dois: list[str]):
        """
            Gets all OpenAlexID and referenced works from a doi
        """
        # thanks to https://blog.openalex.org/fetch-multiple-dois-in-one-openalex-api-request/
        pipe_separated_dois = "|".join(dois)
        endpoint = self.base_url + f"/works?filter=doi:{pipe_separated_dois}&per-page=50&mailto=carlosvtsdev@gmail.com"
        response = requests.get(endpoint)
        response.raise_for_status()
        self.works = response.json()["results"]

    def extract_metadata(self):
        """
            Pega só os campos úteis de cada work em self.works
            e guarda em self.metadata, indexado pelo id OpenAlex.
        """
        for w in self.works:
            work = Work.from_openalex(w)
            self.metadata[work.id] = work

    def save_raw(self, path: str = "data/raw/start_set.json"):
        """Guarda a resposta bruta, serve de cache e de prova."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.works, ensure_ascii=False, indent=2), encoding="utf-8")
