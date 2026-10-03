from dataclasses import dataclass, field, asdict
import json

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

    @property
    def has_abstract(self) -> bool:
        return self.abstract is not None

    @classmethod
    def from_openalex(cls, w: dict, round = 0) -> "Work":
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
        )
    
    @classmethod
    def load_jsonl(cls, path:str) -> dict[str, "Work"]:
        works = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                w = cls(**json.loads(line))
                works[w.id] = w
        return works
