"""
    Caminhos de cada rodada do snowballing (Wohlin). data/rounds/ é a fonte da verdade:

      r0/                     start set (seeds da rodada 1); entra como selecionado, sem triagem
      r<N>/                   rodada N: backward e forward a partir de r<N-1>/selected.jsonl
        raw.jsonl             resposta bruta do OpenAlex, um work por linha
        works.jsonl           um Work por linha (etapa 01)
        title_screening.*     triagem por título (etapa 02)
        candidates.jsonl      passed_title + needs_context
        candidates_abstracts.jsonl, coverage_report.json   etapa 03, abstracts
        cluster/              embeddings, varreduras e atribuições da rodada (etapa 03)
        included.jsonl        works dos clusters mantidos (etapa 03 -> etapa 04)
        fulltext/             manifesto, fila manual, chunks, revisão do RAG e decisões do texto completo (etapas 04 e 05)
        selected.jsonl        incluídos no texto completo: seeds da rodada N+1
      abstracts_cache/        cache das APIs de abstract, comum a todas as rodadas
      fulltext/docs, text/    PDFs/XMLs baixados e texto extraído, comuns a todas as rodadas
      chroma/                 banco vetorial do RAG, uma coleção por rodada

    Os dados da pipeline anterior (duas cadeias independentes, data/jsonl, data/raw, data/cluster,
    data/fulltext) não são lidos nem alterados.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

DATA = Path("data")
ROOT = DATA / "rounds"
START_SET_DOIS = DATA / "start_set_dois.csv"

ABSTRACTS_CACHE = ROOT / "abstracts_cache"
FULLTEXT_DOCS = ROOT / "fulltext/docs"
FULLTEXT_TEXT = ROOT / "fulltext/text"
CHROMA = ROOT / "chroma"


@dataclass(frozen=True)
class Round:
    n: int

    @property
    def name(self) -> str:
        return f"rodada {self.n}"

    @property
    def dir(self) -> Path:
        return ROOT / f"r{self.n}"

    # etapa 01
    @property
    def raw(self) -> Path:
        return self.dir / "raw.jsonl"

    @property
    def works(self) -> Path:
        return self.dir / "works.jsonl"

    @property
    def unresolved(self) -> Path:
        return self.dir / "unresolved_ids.txt"

    @property
    def backward_done(self) -> Path:
        return self.dir / "backward_done_seeds.txt"

    @property
    def forward_done(self) -> Path:
        return self.dir / "forward_done_seeds.txt"

    @property
    def s2_log(self) -> Path:
        return self.dir / "forward_s2_log.jsonl"

    # etapa 02
    @property
    def title_screening_json(self) -> Path:
        return self.dir / "title_screening.json"

    @property
    def title_screening_jsonl(self) -> Path:
        return self.dir / "title_screening.jsonl"

    @property
    def candidates(self) -> Path:
        return self.dir / "candidates.jsonl"

    # etapa 03
    @property
    def candidates_abstracts(self) -> Path:
        return self.dir / "candidates_abstracts.jsonl"

    @property
    def coverage_report(self) -> Path:
        return self.dir / "coverage_report.json"

    @property
    def cluster_dir(self) -> Path:
        return self.dir / "cluster"

    @property
    def included(self) -> Path:
        # na rodada 0 o start set entra direto no texto completo
        return self.works if self.n == 0 else self.dir / "included.jsonl"

    # etapa 04
    @property
    def fulltext_dir(self) -> Path:
        return self.dir / "fulltext"

    @property
    def manifest(self) -> Path:
        return self.fulltext_dir / "manifest.csv"

    @property
    def decisions(self) -> Path:
        return self.fulltext_dir / "decisions.csv"

    @property
    def chunks(self) -> Path:
        return self.fulltext_dir / "chunks.jsonl"

    @property
    def rag_review_dir(self) -> Path:
        return self.fulltext_dir / "rag_review"

    @property
    def selected(self) -> Path:
        # o start set é selecionado por definição
        return self.works if self.n == 0 else self.dir / "selected.jsonl"


START_SET = Round(0)


def existing_rounds() -> list[Round]:
    """Rodadas com works.jsonl em disco, em ordem."""
    rounds = []
    n = 0
    while Round(n).works.exists():
        rounds.append(Round(n))
        n += 1
    return rounds


def pop_round(args: list[str]) -> tuple[Round, list[str]]:
    """Tira `--round N` dos argumentos (obrigatório; 0 é o start set)."""
    if "--round" not in args:
        sys.exit("faltou --round N (rodada do snowballing; 0 é o start set)")
    i = args.index("--round")
    if i + 1 >= len(args) or not args[i + 1].isdigit():
        sys.exit("--round precisa de um número inteiro")
    n = int(args[i + 1])
    return Round(n), args[:i] + args[i + 2 :]
