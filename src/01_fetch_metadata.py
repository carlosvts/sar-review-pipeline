import requests
import csv
from pathlib import Path
from typing import Any
import json

class DoiParser:
    def __init__(self, csvfile: str):
        self.csvfile:  str  = csvfile
        self.dois: list[str] = []

    def extract_doi(self):
        """
            Extract DOI's from a csvfile
            format is always a csv only file that
            contains the first colunm with DOI's
        """
        with open(self.csvfile, newline="", encoding="utf-8") as f:
            lines = csv.reader(f)
            for line in lines:
                self.dois.append(line[0])
            # removendo a coluna
            self.dois = self.dois[1:]
  
 
class OpenAlexAPI:
    def __init__(self, base_url: str = "https://api.openalex.org"):
        self.base_url = base_url
        self.works = {} 
        self.metadata: dict[str, dict[Any, Any]] = {}
    
    def get_referenced_works(self, dois:list[str]):
        """
            Gets all OpenAlexID and referenced works from a doi
        """
        # thanks to https://blog.openalex.org/fetch-multiple-dois-in-one-openalex-api-request/
        pipe_separated_dois = "|".join(dois)
        endpoint = self.base_url + f"/works?filter=doi:{pipe_separated_dois}&per-page=50&mailto=carlosvtsdev@gmail.com" 
        response = requests.get(endpoint)
        self.works = response.json()["results"]
    
    @staticmethod
    def normalize_doi(doi: str | None) -> str | None:
        """https://doi.org/10.X/Y  ->  10.x/y"""
        if not doi:
            return None
        return doi.lower().replace("https://doi.org/", "")

    @staticmethod
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

    def extract_metadata(self):
        """
            Pega só os campos úteis de cada work em self.works
            e guarda em self.metadata, indexado pelo id OpenAlex.
        """
        for w in self.works:
            # alguns campos aninhados podem vir None, por isso o "or {}"
            oa = w.get("open_access") or {}
            best_oa = w.get("best_oa_location") or {}
            source = (w.get("primary_location") or {}).get("source") or {}
            topic = w.get("primary_topic") or {}
            authorships = w.get("authorships") or []
            abstract = self.rebuild_abstract(w.get("abstract_inverted_index"))

            self.metadata[w["id"]] = {
                "id": w["id"],
                "doi": self.normalize_doi(w.get("doi")),
                "title": w.get("title"),
                "publication_year": w.get("publication_year"),
                "type": w.get("type"),
                "language": w.get("language"),
                "is_retracted": w.get("is_retracted"),
                "is_paratext": w.get("is_paratext"),
                "publisher": source.get("host_organization_name"),
                "abstract": abstract,
                "has_abstract": abstract is not None,
                "referenced_works": w.get("referenced_works") or [],
                "referenced_works_count": w.get("referenced_works_count"),
                "is_oa": oa.get("is_oa"),
                "oa_status": oa.get("oa_status"),
                "pdf_url": best_oa.get("pdf_url"),
                "oa_url": oa.get("oa_url"),
                "journal": source.get("display_name"),
                "cited_by_count": w.get("cited_by_count"),
                "primary_topic": topic.get("display_name"),
                "keywords": [k["display_name"] for k in (w.get("keywords") or [])],
                "first_author": authorships[0]["author"]["display_name"] if authorships else None,
            }

    def save_raw(self, path: str = "data/raw/start_set.json"):
        """Guarda a resposta bruta, serve de cache e de prova."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.works, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    mf = DoiParser("data/start_set_dois.csv")
    mf.extract_doi()
    print(mf.dois)
    oa_api = OpenAlexAPI()
    oa_api.get_referenced_works(mf.dois)
    oa_api.save_raw()
    oa_api.extract_metadata()

    # conferência: algum DOI do start set não voltou do OpenAlex?
    found = {m["doi"] for m in oa_api.metadata.values()}
    missing = [d for d in mf.dois if d not in found]
    print(f"{len(oa_api.metadata)}/{len(mf.dois)} encontrados | faltando: {missing}")

    # no main, depois de extract_metadata()
    for m in oa_api.metadata.values():
        print(m["has_abstract"], m["publisher"], m["type"], m["doi"])
