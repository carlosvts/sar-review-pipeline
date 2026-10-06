import json
from dataclasses import asdict, dataclass, field


def normalize_doi(doi: str | None) -> str | None:
    """https://doi.org/10.X/Y  ->  10.x/y"""
    if not doi:
        return None
    return doi.lower().replace("https://doi.org/", "")


def rebuild_abstract(inverted_index: dict | None) -> str | None:
    """
    OpenAlex devolve {palavra: [posições]}.
    Aqui reordenamos pelas posições para obter o texto.
    """
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def extract_oa_locations(w: dict) -> list[dict]:
    """
    Lista enxuta das locations OA de um work, para a etapa de download.
    A best_oa_location vem primeiro (is_best=True); duplicatas e itens
    sem pdf_url e sem landing_page_url são descartados.
    """

    def key(loc: dict) -> tuple[str | None, str | None]:
        return loc.get("pdf_url"), loc.get("landing_page_url")

    best = w.get("best_oa_location") or {}
    best_key = key(best) if best else None

    out: list[dict] = []
    seen: set[tuple[str | None, str | None]] = set()
    for loc in w.get("locations") or []:
        if not loc.get("is_oa"):
            continue
        k = key(loc)
        if not any(k) or k in seen:
            continue
        seen.add(k)
        out.append(
            {
                "pdf_url": k[0],
                "landing_page_url": k[1],
                "source": (loc.get("source") or {}).get("display_name"),
                "license": loc.get("license"),
                "version": loc.get("version"),
                "is_best": k == best_key,
            }
        )
    # deixa os melhores primeiro  
    out.sort(key=lambda x: not x["is_best"])
    return out


@dataclass
class Work:
    id: str
    doi: str | None = None
    title: str | None = None
    abstract: str | None = None
    abstract_source: str | None = None
    authors: list[str] = field(default_factory=list)
    publication_year: int | None = None
    type: str | None = None
    language: str | None = None
    is_retracted: bool | None = None
    is_paratext: bool | None = None
    referenced_works: list[str] = field(default_factory=list)
    # numero de recursoes do backward snowballing
    backward_round: int = 0
    # locations OA candidatas ao download de texto completo (etapa 04)
    oa_locations: list[dict] = field(default_factory=list)

    @property
    def has_abstract(self) -> bool:
        return self.abstract is not None

    @classmethod
    def from_openalex(cls, w: dict, round=0) -> "Work":
        abstract = rebuild_abstract(w.get("abstract_inverted_index"))
        return cls(
            id=w["id"],
            doi=normalize_doi(w.get("doi")),
            title=w.get("title"),
            abstract=abstract,
            abstract_source="openalex" if abstract else None,
            authors=[
                name
                for a in (w.get("authorships") or [])
                if (name := (a.get("author") or {}).get("display_name"))
            ],
            publication_year=w.get("publication_year"),
            type=w.get("type"),
            language=w.get("language"),
            is_retracted=w.get("is_retracted"),
            is_paratext=w.get("is_paratext"),
            referenced_works=w.get("referenced_works") or [],
            backward_round=round,
            oa_locations=extract_oa_locations(w),
        )

    @classmethod
    def load_jsonl(cls, path: str) -> dict[str, "Work"]:
        works = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                w = cls(**json.loads(line))
                works[w.id] = w
        return works
