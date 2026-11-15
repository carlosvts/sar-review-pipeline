"""
    Etapa 01, forward: busca quem cita cada seed, rodada a rodada, com a triagem por título
    (etapa 02) decidindo a fronteira seguinte, como no backward.

    Rodada 1: os seeds são os artigos do start set.
    Rodada n: os works do forward da rodada n-1 que passaram pelo título (passed_title).
    O forward é independente do backward: os dois partem do start set, e works já vistos no
    backward não são descartados aqui (a união das direções é feita depois, na etapa 04).
    Para quando uma rodada não traz nenhum passed_title novo, ou em --max-rounds (protocolo, 4.4).

    Fontes, por lote de seeds:
      1. OpenAlex, filtro cites:W1|W2|... paginado por cursor
      2. Semantic Scholar, citações de cada seed com DOI; o que o OpenAlex não trouxe é buscado
         no OpenAlex pelo DOI, para todo work ter o mesmo formato e o mesmo ID
    Works já vistos (start set ou forward) são descartados.

    Os arquivos do forward só crescem (append), então a coleta pode ser interrompida e retomada:
    cada fonte registra os seeds que já concluiu (forward_done_seeds.txt para o OpenAlex, uma linha
    no forward_s2_log.jsonl para o Semantic Scholar), e o que já foi gravado não é buscado de novo.
    Uma falha do Semantic Scholar num seed não para a coleta: o seed fica sem linha no log e é
    tentado de novo na próxima execução.
"""
import json
import sys
import time
from dataclasses import asdict
from itertools import count

import requests

from sar_review_pipeline.direction import FORWARD, RAW, START_SET_JSONL
from sar_review_pipeline.screening import screening
from sar_review_pipeline.snowball.openalex import OpenAlexClient, short_id
from sar_review_pipeline.snowball.semantic_scholar import SemanticScholarClient
from sar_review_pipeline.work import Work

FORWARD_RAW = RAW / "forward_raw.jsonl"            # resposta bruta do OpenAlex, um work por linha
DONE_SEEDS = RAW / "forward_done_seeds.txt"        # seeds com as citações do OpenAlex já buscadas
S2_LOG = RAW / "forward_s2_log.jsonl"              # por seed concluído no S2: citações, sem DOI, novas, achadas no OpenAlex
FRONTIER_STATUSES = ("passed_title",)
SEED_BATCH = 50
S2_COOLDOWN = 60  # segundos de espera depois de uma falha do S2 (429 persistente), antes do próximo seed
# campos que Work.from_openalex usa (mais cited_by_count); o resto do registro não é baixado
SELECT = ",".join((
    "id", "doi", "title", "publication_year", "type", "language", "is_retracted", "is_paratext",
    "authorships", "abstract_inverted_index", "referenced_works", "best_oa_location", "locations",
    "cited_by_count",
))


class ForwardSnowballer:
    def __init__(self, use_s2: bool = True):
        self.openalex = OpenAlexClient()
        self.s2 = SemanticScholarClient() if use_s2 else None
        self.forward: dict[str, Work] = {}
        self.known_ids: set[str] = set()
        self.known_dois: set[str] = set()
        self.done: set[str] = set()     # OpenAlex concluído
        self.s2_done: set[str] = set()  # Semantic Scholar concluído
        self.s2_failed: set[str] = set()  # falhas do S2 nesta execução

    def load(self) -> None:
        """Retoma o forward já gravado; o start set entra só como já visto."""
        if FORWARD.works.exists():
            self.forward = Work.load_jsonl(str(FORWARD.works))
        for path in (START_SET_JSONL, FORWARD.works):
            if path.exists():
                for w in Work.load_jsonl(str(path)).values():
                    self.known_ids.add(w.id)
                    if w.doi:
                        self.known_dois.add(w.doi)
        if DONE_SEEDS.exists():
            self.done = set(DONE_SEEDS.read_text(encoding="utf-8").split())
        if S2_LOG.exists():
            with S2_LOG.open(encoding="utf-8") as f:
                self.s2_done = {json.loads(line)["seed"] for line in f if line.strip()}

    def needs_s2(self, seed: Work) -> bool:
        return self.s2 is not None and bool(seed.doi) and seed.id not in self.s2_done

    def add(self, raw: dict, round: int) -> bool:
        """Grava um work novo (raw e Work, em append); devolve False se já tinha sido visto."""
        if raw["id"] in self.known_ids:
            return False
        work = Work.from_openalex(raw, round=round, direction="forward")
        with FORWARD_RAW.open("a", encoding="utf-8") as f:
            f.write(json.dumps(raw, ensure_ascii=False) + "\n")
        with FORWARD.works.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(work), ensure_ascii=False) + "\n")
        self.forward[work.id] = work
        self.known_ids.add(work.id)
        if work.doi:
            self.known_dois.add(work.doi)
        return True

    def from_openalex(self, seeds: list[Work], round: int) -> int:
        ids = "|".join(short_id(s.id) for s in seeds)
        return sum(self.add(raw, round) for raw in self.openalex.get_all(f"cites:{ids}", select=SELECT))

    def from_s2(self, seeds: list[Work], round: int) -> int:
        added = 0
        for seed in seeds:
            if not self.needs_s2(seed):
                continue
            try:
                dois, total, no_doi = self.s2.citing_dois(seed.doi)
            except requests.RequestException as e:
                # sem linha no log: o seed é tentado de novo na próxima execução
                self.s2_failed.add(seed.id)
                print(f"    S2 falhou para {seed.id} ({type(e).__name__}); fica para a próxima execução")
                time.sleep(S2_COOLDOWN)
                continue
            # DOIs com | ou , quebrariam o filtro do OpenAlex
            new = sorted(d for d in dois - self.known_dois if "|" not in d and "," not in d)
            found = 0
            for i in range(0, len(new), 50):
                for raw in self.openalex.get("doi:" + "|".join(new[i : i + 50]), per_page=50, select=SELECT):
                    found += self.add(raw, round)
            added += found
            with S2_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "seed": seed.id, "doi": seed.doi, "round": round, "s2_citations": total,
                    "sem_doi": no_doi, "novos_dois": len(new), "achados_no_openalex": found,
                }) + "\n")
            self.s2_done.add(seed.id)
        return added

    def fetch_round(self, seeds: dict[str, Work], round: int) -> None:
        pending = [s for s in seeds.values() if s.id not in self.done or self.needs_s2(s)]
        n_oa = sum(1 for s in pending if s.id not in self.done)
        n_s2 = sum(1 for s in pending if self.needs_s2(s))
        print(f"Seeds: {len(seeds)}  pendentes: {len(pending)} (OpenAlex: {n_oa}, Semantic Scholar: {n_s2})")
        RAW.mkdir(parents=True, exist_ok=True)
        FORWARD.works.parent.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(pending), SEED_BATCH):
            batch = pending[i : i + SEED_BATCH]
            oa_batch = [s for s in batch if s.id not in self.done]
            added_oa = self.from_openalex(oa_batch, round) if oa_batch else 0
            if oa_batch:
                with DONE_SEEDS.open("a", encoding="utf-8") as f:
                    f.write("".join(s.id + "\n" for s in oa_batch))
                self.done.update(s.id for s in oa_batch)
            added_s2 = self.from_s2(batch, round)
            print(f"  seeds {i + len(batch)}/{len(pending)}  novos: OpenAlex {added_oa}, S2 {added_s2}"
                  f"  (forward: {len(self.forward)})")
        if self.s2_failed:
            print(f"Semantic Scholar falhou em {len(self.s2_failed)} seed(s): rode o mesmo comando de novo"
                  " para tentar só esses")


def first_seeds() -> dict[str, Work]:
    """Start set."""
    if not START_SET_JSONL.exists():
        sys.exit(f"{START_SET_JSONL} não existe: rode antes  uv run step01-snowball")
    return Work.load_jsonl(str(START_SET_JSONL))


def run(max_rounds: int | None = None, use_s2: bool = True) -> None:
    """Etapas 01 e 02, forward: rodada a rodada até a fronteira esvaziar (ou max_rounds)."""
    sn = ForwardSnowballer(use_s2=use_s2)
    sn.load()
    seeds = first_seeds()

    for round in count(1):
        print(f"ITERAÇÃO (forward): {round}")
        sn.fetch_round(seeds, round)
        screening.run(FORWARD)
        screening.filter(FORWARD)

        # nova fronteira: works do forward desta rodada que passaram pelo título
        rows = screening.load_screening_rows(FORWARD)
        new = [w for w in sn.forward.values() if w.backward_round == round]
        seeds = {
            w.id: w for w in new
            if (row := rows.get(w.id)) and row["status"] in FRONTIER_STATUSES
        }
        print(f"{len(new)} works novos na rodada, {len(seeds)} passaram pelo título")
        if not seeds:
            print("Fronteira vazia, forward convergiu.")
            break
        if max_rounds and round >= max_rounds:
            print(f"Limite de {max_rounds} rodada(s) atingido com {len(seeds)} works na fronteira (protocolo, 4.4).")
            break
