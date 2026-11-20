"""
    Etapa 01: coleta de uma rodada do snowballing, no método do Wohlin.

    Rodada 0: o start set, buscado pelo DOI. Entra como selecionado, sem triagem.
    Rodada N: os seeds são os selecionados no texto completo da rodada N-1 (r<N-1>/selected.jsonl).
    Para cada seed, na mesma rodada:
      - backward: os referenced_works do seed, buscados no OpenAlex em lotes de 50 IDs
      - forward: quem cita o seed, pelo OpenAlex (filtro cites:, paginado por cursor) e pelo
        Semantic Scholar (o que só o S2 conhece é buscado no OpenAlex pelo DOI, para todo work
        ter o mesmo formato e o mesmo ID)
    Works já vistos em qualquer rodada anterior são ignorados (já foram examinados). Um work achado
    pelas duas direções na mesma rodada entra uma vez, com direction = "both".

    A coleta pode ser interrompida e retomada: works.jsonl, raw.jsonl e hits.jsonl só crescem
    (append), e cada fonte registra os seeds que concluiu (backward_done_seeds.txt,
    forward_done_seeds.txt e uma linha por seed no forward_s2_log.jsonl). Uma falha do Semantic
    Scholar num seed não para a coleta: o seed fica sem linha no log e é tentado de novo na próxima
    execução. No fim, works.jsonl é reescrito com a direção de cada work tirada do hits.jsonl.

    hits.jsonl registra cada aresta seed -> work da rodada ({seed, work, direction}): é o que diz
    por qual seed e por qual direção cada artigo chegou.
"""
import json
import sys
import time
from dataclasses import asdict

import requests

from sar_review_pipeline.rounds import START_SET, START_SET_DOIS, Round
from sar_review_pipeline.snowball.openalex import OpenAlexClient, short_id
from sar_review_pipeline.snowball.parser import DoiParser
from sar_review_pipeline.snowball.semantic_scholar import SemanticScholarClient
from sar_review_pipeline.work import Work

SEED_BATCH = 50
ID_BATCH = 50
S2_COOLDOWN = 60  # segundos de espera depois de uma falha do S2 (429 persistente), antes do próximo seed
# campos que Work.from_openalex usa (mais cited_by_count); o resto do registro não é baixado
SELECT = ",".join((
    "id", "doi", "title", "publication_year", "type", "language", "is_retracted", "is_paratext",
    "authorships", "abstract_inverted_index", "referenced_works", "best_oa_location", "locations",
    "cited_by_count",
))


def write_jsonl(path, works) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with tmp.open("w", encoding="utf-8") as f:
        for w in works:
            f.write(json.dumps(asdict(w), ensure_ascii=False) + "\n")
    tmp.replace(path)


def fetch_start_set(force: bool = False) -> dict[str, Work]:
    """Rodada 0: busca os DOIs do start set no OpenAlex (uma vez; --force busca de novo)."""
    if START_SET.works.exists() and not force:
        return Work.load_jsonl(str(START_SET.works))
    parser = DoiParser(str(START_SET_DOIS))
    parser.extract_doi()
    raws = OpenAlexClient().get("doi:" + "|".join(parser.dois), per_page=50, select=SELECT)
    works = {w["id"]: Work.from_openalex(w, round=0, direction="start_set") for w in raws}
    START_SET.dir.mkdir(parents=True, exist_ok=True)
    with START_SET.raw.open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(w, ensure_ascii=False) + "\n" for w in raws)
    write_jsonl(START_SET.works, works.values())
    found = {w.doi for w in works.values()}
    missing = [d for d in parser.dois if d.lower() not in found]
    print(f"Start set: {len(works)} de {len(parser.dois)} DOIs encontrados no OpenAlex")
    for doi in missing:
        print(f"  não encontrado: {doi}")
    return works


class RoundCollector:
    def __init__(self, rnd: Round, use_s2: bool = True):
        if rnd.n < 1:
            raise ValueError("a coleta começa na rodada 1 (a rodada 0 é o start set)")
        self.round = rnd
        self.openalex = OpenAlexClient()
        self.s2 = SemanticScholarClient() if use_s2 else None
        self.works: dict[str, Work] = {}      # works desta rodada
        self.by_doi: dict[str, str] = {}      # doi -> id, desta rodada
        self.previous_ids: set[str] = set()   # works de rodadas anteriores (ignorados)
        self.previous_dois: set[str] = set()
        self.hits: set[tuple[str, str, str]] = set()  # (seed, work, direction)
        self.unresolved: set[str] = set()
        self.backward_done: set[str] = set()
        self.forward_done: set[str] = set()
        self.s2_done: set[str] = set()
        self.s2_failed: set[str] = set()

    # ---------- estado em disco ----------

    @property
    def hits_path(self):
        return self.round.dir / "hits.jsonl"

    def seeds(self) -> dict[str, Work]:
        prev = Round(self.round.n - 1)
        if not prev.selected.exists():
            step = "uv run step01-snowball start" if prev.n == 0 else f"a seleção do texto completo da rodada {prev.n}"
            sys.exit(f"{prev.selected} não existe: rode antes  {step}")
        return Work.load_jsonl(str(prev.selected))

    def load(self) -> None:
        for n in range(self.round.n):
            path = Round(n).works
            if not path.exists():
                sys.exit(f"{path} não existe: as rodadas anteriores precisam estar completas")
            for w in Work.load_jsonl(str(path)).values():
                self.previous_ids.add(w.id)
                if w.doi:
                    self.previous_dois.add(w.doi)
        r = self.round
        if r.works.exists():
            self.works = Work.load_jsonl(str(r.works))
            self.by_doi = {w.doi: w.id for w in self.works.values() if w.doi}
        if self.hits_path.exists():
            with self.hits_path.open(encoding="utf-8") as f:
                for line in f:
                    h = json.loads(line)
                    self.hits.add((h["seed"], h["work"], h["direction"]))
        for path, target in ((r.backward_done, self.backward_done), (r.forward_done, self.forward_done)):
            if path.exists():
                target.update(path.read_text(encoding="utf-8").split())
        if r.unresolved.exists():
            self.unresolved = set(r.unresolved.read_text(encoding="utf-8").split())
        if r.s2_log.exists():
            with r.s2_log.open(encoding="utf-8") as f:
                self.s2_done = {json.loads(line)["seed"] for line in f if line.strip()}

    def mark_done(self, path, target: set[str], seeds: list[Work]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write("".join(s.id + "\n" for s in seeds))
        target.update(s.id for s in seeds)

    def hit(self, seed_id: str, work_id: str, direction: str) -> None:
        key = (seed_id, work_id, direction)
        if key in self.hits:
            return
        self.hits.add(key)
        with self.hits_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"seed": seed_id, "work": work_id, "direction": direction}) + "\n")

    def add(self, raw: dict, direction: str) -> str | None:
        """
        Grava um work desta rodada (raw e Work, em append) se ainda não estiver nela.
        Devolve o id do work desta rodada, ou None se ele já foi visto numa rodada anterior.
        """
        work_id = raw["id"]
        if work_id in self.previous_ids:
            return None
        if work_id in self.works:
            return work_id
        work = Work.from_openalex(raw, round=self.round.n, direction=direction)
        if work.doi and work.doi in self.previous_dois:
            return None  # mesmo DOI com outro ID do OpenAlex numa rodada anterior
        with self.round.raw.open("a", encoding="utf-8") as f:
            f.write(json.dumps(raw, ensure_ascii=False) + "\n")
        with self.round.works.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(work), ensure_ascii=False) + "\n")
        self.works[work_id] = work
        if work.doi:
            self.by_doi[work.doi] = work_id
        return work_id

    # ---------- backward ----------

    def backward(self, seeds: list[Work]) -> int:
        """Referências de um lote de seeds. Devolve quantos works novos entraram na rodada."""
        before = len(self.works)
        refs = {ref for s in seeds for ref in s.referenced_works}
        pending = sorted(refs - self.previous_ids - set(self.works) - self.unresolved)
        returned: set[str] = set()
        for i in range(0, len(pending), ID_BATCH):
            chunk = [short_id(x) for x in pending[i : i + ID_BATCH]]
            for raw in self.openalex.get("openalex:" + "|".join(chunk), per_page=ID_BATCH, select=SELECT):
                returned.add(raw["id"])
                self.add(raw, "backward")
            time.sleep(0.2)
        new_unresolved = {x for x in pending if x not in returned}
        if new_unresolved:
            self.unresolved |= new_unresolved
            self.round.unresolved.write_text("\n".join(sorted(self.unresolved)), encoding="utf-8")
        for s in seeds:
            for ref in s.referenced_works:
                if ref in self.works:
                    self.hit(s.id, ref, "backward")
        return len(self.works) - before

    # ---------- forward ----------

    def forward_openalex(self, seeds: list[Work]) -> int:
        before = len(self.works)
        seed_ids = {s.id for s in seeds}
        ids = "|".join(short_id(s.id) for s in seeds)
        for raw in self.openalex.get_all(f"cites:{ids}", select=SELECT):
            work_id = self.add(raw, "forward")
            if work_id:
                for seed_id in seed_ids.intersection(raw.get("referenced_works") or []):
                    self.hit(seed_id, work_id, "forward")
        return len(self.works) - before

    def needs_s2(self, seed: Work) -> bool:
        return self.s2 is not None and bool(seed.doi) and seed.id not in self.s2_done

    def forward_s2(self, seeds: list[Work]) -> int:
        before = len(self.works)
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
            dois -= self.previous_dois
            known = {d for d in dois if d in self.by_doi}
            # DOIs com | ou , quebrariam o filtro do OpenAlex
            new = sorted(d for d in dois - known if "|" not in d and "," not in d)
            found = 0
            for i in range(0, len(new), ID_BATCH):
                for raw in self.openalex.get("doi:" + "|".join(new[i : i + ID_BATCH]), per_page=ID_BATCH, select=SELECT):
                    if raw["id"] not in self.works and raw["id"] not in self.previous_ids:
                        found += 1
                    work_id = self.add(raw, "forward")
                    if work_id:
                        self.hit(seed.id, work_id, "forward")
            for d in known:
                self.hit(seed.id, self.by_doi[d], "forward")
            with self.round.s2_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "seed": seed.id, "doi": seed.doi, "s2_citations": total, "sem_doi": no_doi,
                    "ja_na_rodada": len(known), "novos_dois": len(new), "achados_no_openalex": found,
                }) + "\n")
            self.s2_done.add(seed.id)
        return len(self.works) - before

    # ---------- rodada ----------

    def finalize(self) -> None:
        """Reescreve works.jsonl com a direção de cada work: backward, forward ou both."""
        directions: dict[str, set[str]] = {}
        for _, work_id, direction in self.hits:
            directions.setdefault(work_id, set()).add(direction)
        for work_id, work in self.works.items():
            found = directions.get(work_id, {work.direction})
            work.direction = "both" if len(found) > 1 else next(iter(found))
        write_jsonl(self.round.works, self.works.values())

    def run(self) -> dict[str, Work]:
        seeds = list(self.seeds().values())
        self.round.dir.mkdir(parents=True, exist_ok=True)
        self.load()
        print(f"{self.round.name}: {len(seeds)} seeds  já vistos em rodadas anteriores: {len(self.previous_ids)}")
        if not seeds:
            print("Nenhum seed: o snowballing convergiu na rodada anterior.")
            return {}

        pending_b = [s for s in seeds if s.id not in self.backward_done]
        pending_f = [s for s in seeds if s.id not in self.forward_done or self.needs_s2(s)]
        print(f"Pendentes: backward {len(pending_b)}, forward {len(pending_f)}")

        for i in range(0, len(pending_b), SEED_BATCH):
            batch = pending_b[i : i + SEED_BATCH]
            added = self.backward(batch)
            self.mark_done(self.round.backward_done, self.backward_done, batch)
            print(f"  backward: seeds {i + len(batch)}/{len(pending_b)}  novos: {added}  (rodada: {len(self.works)})")

        for i in range(0, len(pending_f), SEED_BATCH):
            batch = pending_f[i : i + SEED_BATCH]
            oa_batch = [s for s in batch if s.id not in self.forward_done]
            added_oa = self.forward_openalex(oa_batch) if oa_batch else 0
            if oa_batch:
                self.mark_done(self.round.forward_done, self.forward_done, oa_batch)
            added_s2 = self.forward_s2(batch)
            print(f"  forward: seeds {i + len(batch)}/{len(pending_f)}  novos: OpenAlex {added_oa}, S2 {added_s2}"
                  f"  (rodada: {len(self.works)})")

        self.finalize()
        counts = {}
        for w in self.works.values():
            counts[w.direction] = counts.get(w.direction, 0) + 1
        print(f"\n{self.round.name}: {len(self.works)} works novos  por direção: {counts}"
              f"  sem registro no OpenAlex: {len(self.unresolved)}")
        if self.s2_failed:
            print(f"Semantic Scholar falhou em {len(self.s2_failed)} seed(s): rode o mesmo comando de novo"
                  " para tentar só esses")
        return self.works
