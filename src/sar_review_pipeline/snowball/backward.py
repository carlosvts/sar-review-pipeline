"""
    Etapa 01, backward: busca as referências (referenced_works) da fronteira no OpenAlex,
    rodada a rodada, com a triagem por título (etapa 02) decidindo a fronteira seguinte.
"""
import json
import time
from dataclasses import asdict
from itertools import count

from sar_review_pipeline.direction import (
    BACKWARD,
    JSONL,
    RAW,
    START_SET_DOIS,
    START_SET_JSONL,
    START_SET_RAW,
)
from sar_review_pipeline.screening import screening
from sar_review_pipeline.snowball.openalex import OpenAlexClient, short_id
from sar_review_pipeline.snowball.parser import DoiParser
from sar_review_pipeline.work import Work

BACKWARD_RAW = RAW / "backward.json"
UNRESOLVED = RAW / "unresolved_ids.txt"
# só passed_title alimenta a fronteira; needs_context vai para candidates.jsonl
# (via filter) e fica para a triagem de abstract, mas não expande o snowballing
FRONTIER_STATUSES = ("passed_title",)


class BackwardSnowballer:
    def __init__(self, client: OpenAlexClient | None = None):
        self.client = client or OpenAlexClient()
        # start set: sempre buscado de novo a cada execução
        self.startset_raw: list[dict] = []
        self.startset: dict[str, Work] = {}
        # backward: carregado do disco e acumulado entre rodadas
        self.backward_raw: list[dict] = []
        self.backward: dict[str, Work] = {}
        self.unresolved: set[str] = set()

    def fetch_startset(self, dois: list[str]):
        self.startset_raw = self.client.get("doi:" + "|".join(dois))
        self.startset = {
            w["id"]: Work.from_openalex(w, round=0, direction="start_set") for w in self.startset_raw
        }

    def load_backward(self):
        """Retoma as rodadas anteriores, se os arquivos existirem."""
        if BACKWARD_RAW.exists():
            self.backward_raw = json.loads(BACKWARD_RAW.read_text(encoding="utf-8"))
        if BACKWARD.works.exists():
            self.backward = Work.load_jsonl(str(BACKWARD.works))
        # reparseia o raw, para que registros de rodadas anteriores também
        # passem por Work.from_openalex (ex.: oa_locations); o raw não guarda
        # a rodada, então ela vem do JSONL carregado acima
        for w in self.backward_raw:
            prev = self.backward.get(w["id"])
            self.backward[w["id"]] = Work.from_openalex(w, round=prev.backward_round if prev else 1)
        if UNRESOLVED.exists():
            self.unresolved = set(UNRESOLVED.read_text(encoding="utf-8").split())

    def pending_ids(self, sources: dict[str, Work]) -> list[str]:
        """IDs citados por `sources` que ainda não foram vistos."""
        ids: set[str] = set()
        for w in sources.values():
            ids.update(w.referenced_works)
        return sorted(ids - set(self.startset) - set(self.backward) - self.unresolved)

    def fetch_backward(self, ids: list[str], round: int, batch: int = 50):
        returned: set[str] = set()
        for i in range(0, len(ids), batch):
            chunk = [short_id(x) for x in ids[i : i + batch]]
            results = self.client.get("openalex:" + "|".join(chunk), per_page=batch)
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
        START_SET_RAW.write_text(json.dumps(self.startset_raw, ensure_ascii=False, indent=2), encoding="utf-8")
        BACKWARD_RAW.write_text(json.dumps(self.backward_raw, ensure_ascii=False, indent=2), encoding="utf-8")
        UNRESOLVED.write_text("\n".join(sorted(self.unresolved)), encoding="utf-8")
        for path, works in ((START_SET_JSONL, self.startset), (BACKWARD.works, self.backward)):
            with path.open("w", encoding="utf-8") as f:
                for w in works.values():
                    f.write(json.dumps(asdict(w), ensure_ascii=False) + "\n")


def start() -> BackwardSnowballer:
    """Start set rebuscado e backward acumulado carregado do disco."""
    parser = DoiParser(str(START_SET_DOIS))
    parser.extract_doi()
    sn = BackwardSnowballer()
    sn.fetch_startset(parser.dois)
    # carrega o que já foi baixado antes de calcular os pendentes
    sn.load_backward()
    return sn


def run():
    """Etapas 01 e 02, backward: rodada a rodada até a fronteira esvaziar."""
    sn = start()
    # fronteira: works cujas referências ainda vamos buscar
    # na rodada 1 é o start set; depois, só os novos que passaram pelo título
    frontier = sn.startset

    for round in count(1):
        print(f"ITERAÇÃO: {round}")
        ids = sn.pending_ids(frontier)
        # recalcula o que deve ser buscado, se não houver mais nada
        # pula para aproxima rodada ou encerra o snowballing (se fronteira vazia)
        if ids:
            sn.fetch_backward(ids, round=round)
        else:
            print("Nenhuma referência nova para buscar nesta rodada.")
        sn.save()
        screening.run(BACKWARD)
        screening.filter(BACKWARD)

        # nova fronteira: works que entraram nesta rodada e passaram pelo título
        rows = screening.load_screening_rows(BACKWARD)
        frontier = {}
        for work_id, w in sn.backward.items():
            if w.backward_round != round:
                continue
            row = rows.get(work_id)
            if row and row["status"] in FRONTIER_STATUSES:
                frontier[work_id] = w
        print(f"{len(ids)} buscados, {len(frontier)} passaram pelo título")
        if not frontier:
            print("Fronteira vazia, snowballing convergiu.")
            break


def fetch_one_round():
    """step01-fetch: só o start set e a rodada 1 do backward, sem triagem."""
    sn = start()
    ids = sn.pending_ids(sn.startset)
    sn.fetch_backward(ids, round=1)
    sn.save()
    print(f"backward: {len(sn.backward)} | sem registro: {len(sn.unresolved)}")
