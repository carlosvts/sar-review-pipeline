import json
from pathlib import Path
import time

import requests

from sar_review_pipeline.work import Work


class OpenAlexAPI:
    def __init__(self, base_url: str = "https://api.openalex.org"):
        self.base_url = base_url
        self.works = {}
        self.metadata: dict[str, Work] = {}
        self.backward_works: list[dict[str, Work]] = []
        self.backward_metadata: dict[str, Work] = {}

    
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

    
    def get_backward_ids(self):
        """
            Get all unique ids from start set 
        """
        ids: set[str] = set()
        for work in self.metadata.values():
            ids.update(work.referenced_works)
        # na primeira iteracao, remove o set dos start set
        # nas proximas iteracoes, remove os que ja foram incluidos
        # recursivo...
        ids -= set(self.metadata)
        return sorted(ids)

    
    def get_works_by_ids(self, ids: list[str], batch: int = 50):
        """
            Busca na api os works através do ID, {batch} por vez
            ID's vem no padrao: https://openalex.org/W7114768064
        """
        self.backward_works = []
        for i in range(0, len(ids), batch):
            chunk = [x.replace("https://openalex.org/", "") for x in ids[i:i + batch]]
            endpoint = (self.base_url
                        + f"/works?filter=openalex:{'|'.join(chunk)}"
                        + f"&per-page={batch}&mailto=carlosvtsdev@gmail.com")
            response = requests.get(endpoint)
            response.raise_for_status()
            self.backward_works.extend(response.json()["results"])
            time.sleep(0.2)


    def extract_backward_metadata(self):
        for w in self.backward_works:
            work = Work.from_openalex(w)
            self.backward_metadata[work.id] = work


    def extract_metadata(self):
        """
            Pega só os campos úteis de cada work em self.works
            e guarda em self.metadata, indexado pelo id OpenAlex.
        """
        for w in self.works:
            work = Work.from_openalex(w)
            self.metadata[work.id] = work

    
    def save_raw(self, path: str = "data/raw/start_set.json", works: list[dict] | None = None):
        """Guarda a resposta bruta, serve de cache e de prova."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = self.works if works is None else works
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
