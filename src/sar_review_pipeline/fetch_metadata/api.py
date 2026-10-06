import json
import time
from dataclasses import asdict
from pathlib import Path

import requests

from sar_review_pipeline.work import Work

# paths para os arquivos
RAW = Path("data/raw")
JSONL = Path("data/jsonl")


class OpenAlexSnowballer:
    def __init__(self, base_url: str = "https://api.openalex.org"):
        self.base_url = base_url
        # start set: sempre buscado de novo a cada execução
        self.startset_raw: list[dict[str, Work]] = []
        self.startset: dict[Work, Work] = {}
        # backward: carregado do disco e acumulado entre rodadas
        self.backward_raw: list[dict[str, Work]] = []
        self.backward: dict[str, Work] = {}
        self.unresolved: set[str] = set()

    # abstrai a logica de buscar na api em uma unica funcao, busca per_page artigos de uma vez só
    def _get(self, filter_expr: str, per_page: int = 50) -> list[dict[str, Work]]:
        endpoint = (
            self.base_url
            + f"/works?filter={filter_expr}"
            + f"&per-page={per_page}&mailto=carlosvtsdev@gmail.com"
        )
        response = requests.get(endpoint)
        response.raise_for_status()
        return response.json()["results"]

    def fetch_startset(self, dois: list[str]):
        self.startset_raw = self._get("doi:" + "|".join(dois))
        self.startset = {
            w["id"]: Work.from_openalex(w, round=0) for w in self.startset_raw
        }

    def load_backward(self):
        """Retoma as rodadas anteriores, se os arquivos existirem."""
        if (RAW / "backward.json").exists():
            self.backward_raw = json.loads(
                (RAW / "backward.json").read_text(encoding="utf-8")
            )
        if (JSONL / "backward.jsonl").exists():
            self.backward = Work.load_jsonl(str(JSONL / "backward.jsonl"))
        if (RAW / "unresolved_ids.txt").exists():
            self.unresolved = set(
                (RAW / "unresolved_ids.txt").read_text(encoding="utf-8").split()
            )

    def pending_ids(self, sources: dict[str, Work]) -> list[str]:
        """IDs citados por `sources` que ainda não foram vistos."""
        ids: set[str] = set()
        for w in sources.values():
            ids.update(w.referenced_works)
        return sorted(ids - set(self.startset) - set(self.backward) - self.unresolved)

    def fetch_backward(self, ids: list[str], round: int, batch: int = 50):
        returned: set[str] = set()
        for i in range(0, len(ids), batch):
            # esse replace existe pois os ids seguem nesse padrao
            # "https://openalex.org/XXXXXXXXXX" <-- queremos o XXXXXXXXXX
            chunk = [x.replace("https://openalex.org/", "") for x in ids[i : i + batch]]
            results = self._get("openalex:" + "|".join(chunk), per_page=batch)
            self.backward_raw.extend(results)
            for w in results:
                work = Work.from_openalex(w, round=round)
                self.backward[work.id] = work
                returned.add(work.id)
            time.sleep(0.2)
        self.unresolved |= {x for x in ids if x not in returned}

    def save(self):
        RAW.mkdir(parents=True, exist_ok=True)
        JSONL.mkdir(parents=True, exist_ok=True)
        # paths para escrever, write_text
        (RAW / "start_set.json").write_text(
            json.dumps(self.startset_raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (RAW / "backward.json").write_text(
            json.dumps(self.backward_raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (RAW / "unresolved_ids.txt").write_text(
            "\n".join(sorted(self.unresolved)), encoding="utf-8"
        )
        for name, works in (("start_set", self.startset), ("backward", self.backward)):
            with (JSONL / f"{name}.jsonl").open("w", encoding="utf-8") as f:
                for w in works.values():
                    f.write(json.dumps(asdict(w), ensure_ascii=False) + "\n")
