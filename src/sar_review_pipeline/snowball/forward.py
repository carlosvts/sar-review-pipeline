"""
    Etapa 01, forward: busca quem cita cada seed, rodada a rodada, com a triagem por título
    (etapa 02) decidindo a fronteira seguinte, como no backward.

    Rodada 1: os seeds são o start set e os incluídos do backward (included.jsonl).
    Rodada n: os works do forward da rodada n-1 que passaram pelo título (passed_title).
    Para quando uma rodada não traz nenhum passed_title novo, ou em --max-rounds (protocolo, 4.4).

    Fontes, por lote de seeds:
      1. OpenAlex, filtro cites:W1|W2|... paginado por cursor
      2. Semantic Scholar, citações de cada seed com DOI; o que o OpenAlex não trouxe é buscado
         no OpenAlex pelo DOI, para todo work ter o mesmo formato e o mesmo ID
    Works já vistos (start set, backward ou forward) são descartados.

    Os arquivos do forward só crescem (append), então a coleta pode ser interrompida e retomada:
    um seed só entra em forward_done_seeds.txt depois das duas fontes, e o que já foi gravado
    não é buscado de novo.
"""
import json
import sys
from dataclasses import asdict
from itertools import count

from sar_review_pipeline.direction import BACKWARD, FORWARD, RAW, START_SET_JSONL
from sar_review_pipeline.screening import screening
from sar_review_pipeline.snowball.openalex import OpenAlexClient, short_id
from sar_review_pipeline.snowball.semantic_scholar import SemanticScholarClient
from sar_review_pipeline.work import Work

FORWARD_RAW = RAW / "forward_raw.jsonl"            # resposta bruta do OpenAlex, um work por linha
DONE_SEEDS = RAW / "forward_done_seeds.txt"        # seeds com as citações já buscadas nas duas fontes
S2_LOG = RAW / "forward_s2_log.jsonl"              # por seed: citações no S2, sem DOI, novas, fora do OpenAlex
FRONTIER_STATUSES = ("passed_title",)
SEED_BATCH = 50
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
        self.done: set[str] = set()

    def load(self) -> None:
        """Retoma o forward já gravado; start set e backward entram só como já vistos."""
        if FORWARD.works.exists():
            self.forward = Work.load_jsonl(str(FORWARD.works))
        for path in (START_SET_JSONL, BACKWARD.works, FORWARD.works):
            if path.exists():
                for w in Work.load_jsonl(str(path)).values():
                    self.known_ids.add(w.id)
                    if w.doi:
                        self.known_dois.add(w.doi)
        if DONE_SEEDS.exists():
            self.done = set(DONE_SEEDS.read_text(encoding="utf-8").split())

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
            if not seed.doi:
                continue
            dois, total, no_doi = self.s2.citing_dois(seed.doi)
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
        return added

    def fetch_round(self, seeds: dict[str, Work], round: int) -> None:
        pending = [s for s in seeds.values() if s.id not in self.done]
        print(f"Seeds: {len(seeds)}  já buscados: {len(seeds) - len(pending)}  pendentes: {len(pending)}")
        RAW.mkdir(parents=True, exist_ok=True)
        FORWARD.works.parent.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(pending), SEED_BATCH):
            batch = pending[i : i + SEED_BATCH]
            n_openalex = self.from_openalex(batch, round)
            n_s2 = self.from_s2(batch, round) if self.s2 else 0
            with DONE_SEEDS.open("a", encoding="utf-8") as f:
                f.write("".join(s.id + "\n" for s in batch))
            self.done.update(s.id for s in batch)
            print(f"  seeds {i + len(batch)}/{len(pending)}  novos: OpenAlex {n_openalex}, S2 {n_s2}"
                  f"  (forward: {len(self.forward)})")


def first_seeds() -> dict[str, Work]:
    """Start set + incluídos do backward."""
    if not BACKWARD.included.exists():
        sys.exit(f"{BACKWARD.included} não existe: rode antes  uv run step03-abstracts include")
    seeds = Work.load_jsonl(str(START_SET_JSONL))
    seeds.update(Work.load_jsonl(str(BACKWARD.included)))
    return seeds


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
