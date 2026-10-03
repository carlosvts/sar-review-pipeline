from dataclasses import dataclass, field, asdict


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
    doi: str | None
    title: str | None
    publication_year: int | None
    type: str | None
    language: str | None
    is_retracted: bool | None
    is_paratext: bool | None
    abstract: str | None
    abstract_source: str | None          # "openalex", "crossref", "pdf" ou None
    referenced_works: list[str] = field(default_factory=list)
    referenced_works_count: int | None = None
    is_oa: bool | None = None
    oa_status: str | None = None
    pdf_url: str | None = None
    oa_url: str | None = None
    journal: str | None = None
    publisher: str | None = None
    cited_by_count: int | None = None
    primary_topic: str | None = None
    keywords: list[str] = field(default_factory=list)
    first_author: str | None = None

    @property
    def has_abstract(self) -> bool:
        return self.abstract is not None

    @classmethod
    def from_openalex(cls, w: dict) -> "Work":
        oa = w.get("open_access") or {}
        best_oa = w.get("best_oa_location") or {}
        source = (w.get("primary_location") or {}).get("source") or {}
        authorships = w.get("authorships") or []
        abstract = rebuild_abstract(w.get("abstract_inverted_index"))
        return cls(
            id=w["id"],
            doi=normalize_doi(w.get("doi")),
            title=w.get("title"),
            publication_year=w.get("publication_year"),
            type=w.get("type"),
            language=w.get("language"),
            is_retracted=w.get("is_retracted"),
            is_paratext=w.get("is_paratext"),
            abstract=abstract,
            abstract_source="openalex" if abstract else None,
            referenced_works=w.get("referenced_works") or [],
            referenced_works_count=w.get("referenced_works_count"),
            is_oa=oa.get("is_oa"),
            oa_status=oa.get("oa_status"),
            pdf_url=best_oa.get("pdf_url"),
            oa_url=oa.get("oa_url"),
            journal=source.get("display_name"),
            publisher=source.get("host_organization_name"),
            cited_by_count=w.get("cited_by_count"),
            primary_topic=(w.get("primary_topic") or {}).get("display_name"),
            keywords=[k["display_name"] for k in (w.get("keywords") or [])],
            first_author=authorships[0]["author"]["display_name"] if authorships else None,
        )
