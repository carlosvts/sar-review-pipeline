import json
from pathlib import Path
from dataclasses import asdict
import time


import requests

from sar_review_pipeline.work import Work

BACKWARD_RAW   = "data/raw/backward.json"
BACKWARD_JSONL = "data/jsonl/backward.jsonl"
UNRESOLVED     = "data/raw/unresolved_ids.txt"


class OpenAlexSnowballer:
    def __init__(self, base_url: str = "https://api.openalex.org"):
        self.base_url = base_url
        self.works = {}
        self.metadata: dict[str, Work] = {}
        self.backward_works: list[dict] = []
        self.backward_metadata: dict[str, Work] = {}
        self.unresolved: set[str] = set()

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
            work = Work.from_openalex(w, round=0)
            self.metadata[work.id] = work

    # ---------- backward (acumula entre rodadas) ----------

    def load_backward(self):
        """Retoma o estado das rodadas anteriores, se os arquivos existirem."""
        if Path(BACKWARD_RAW).exists():
            self.backward_works = json.loads(Path(BACKWARD_RAW).read_text(encoding="utf-8"))
        if Path(BACKWARD_JSONL).exists():
            self.backward_metadata = Work.load_jsonl(BACKWARD_JSONL)
        if Path(UNRESOLVED).exists():
            self.unresolved = set(Path(UNRESOLVED).read_text(encoding="utf-8").split())

    def get_backward_ids(self, sources: dict[str, Work]) -> list[str]:
        """
            IDs referenciados pelos works em `sources` que ainda não foram vistos
            (nem no start set, nem em rodadas anteriores, nem os sem registro).
        """
        ids: set[str] = set()
        for work in sources.values():
            ids.update(work.referenced_works)
        ids -= set(self.metadata) | set(self.backward_metadata) | self.unresolved
        return sorted(ids)

    def get_works_by_ids(self, ids: list[str], round: int, batch: int = 50):
        """Busca em lotes e ACUMULA em self.backward_works / self.backward_metadata."""
        returned: set[str] = set()
        for i in range(0, len(ids), batch):
            chunk = [x.replace("https://openalex.org/", "") for x in ids[i:i + batch]]
            endpoint = (self.base_url
                        + f"/works?filter=openalex:{'|'.join(chunk)}"
                        + f"&per-page={batch}&mailto=carlosvtsdev@gmail.com")
            response = requests.get(endpoint)
            response.raise_for_status()
            results = response.json()["results"]
            self.backward_works.extend(results)
            for w in results:
                work = Work.from_openalex(w, round=round)
                self.backward_metadata[work.id] = work
                returned.add(work.id)
            time.sleep(0.2)
        self.unresolved |= {x for x in ids if x not in returned}

    def save_backward(self):
        self.save_raw(BACKWARD_RAW, self.backward_works)
        self.save_metadata(self.backward_metadata, BACKWARD_JSONL)
        Path(UNRESOLVED).write_text("\n".join(sorted(self.unresolved)), encoding="utf-8")

    # ---------- escrita ----------

    def save_raw(self, path: str = "data/raw/start_set.json", works: list[dict] | None = None):
        """Guarda a resposta bruta, serve de cache e de prova."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = self.works if works is None else works
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_metadata(self, works: dict[str, Work], path: str):
        """Salva os Work limpos em JSONL, um por linha."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for w in works.values():
                f.write(json.dumps(asdict(w), ensure_ascii=False) + "\n")
