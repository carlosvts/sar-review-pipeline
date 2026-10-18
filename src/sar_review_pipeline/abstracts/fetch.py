"""
    Recolhe o abstract de cada candidato numa cascata de APIs, parando na
    primeira fonte que devolver um abstract válido. Toda resposta das APIs
    (inclusive "não encontrado") vai para um cache em disco, então rodar de
    novo não refaz chamadas. Falha transitória (timeout, 5xx) não é guardada.
"""
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from sar_review_pipeline.abstracts.validate import AbstractValidator
from sar_review_pipeline.fulltext.download import Downloader
from sar_review_pipeline.work import Work

load_dotenv()
S2_API_KEY = os.environ.get("S2_API_KEY")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL")

# sem DOI, só aceita o match por título se for praticamente idêntico e do mesmo ano
TITLE_MIN_SIMILARITY = 0.95


class AbstractFetcher:
    CACHE_DIR = Path("data/abstracts/cache")
    TIMEOUT = (10, 60)
    MAX_RETRIES = 3
    RETRY_STATUS = {429, 500, 502, 503, 504}
    BACKOFF = 5.0  # segundos, dobra a cada tentativa

    # ordem da cascata; cada nome (menos openalex, que já vem no registro) tem um _from_<nome>
    SOURCES = ["openalex", "semantic_scholar", "crossref", "europepmc", "arxiv"]
    # pausa mínima entre chamadas à mesma API, em segundos
    DELAYS = {"semantic_scholar": 1.1, "crossref": 0.25, "europepmc": 0.2, "arxiv": 3.0}
    _last_call: dict[str, float] = {}
    _cache: dict[str, dict] = {}

    S2_API = "https://api.semanticscholar.org/graph/v1/paper"
    CROSSREF_API = "https://api.crossref.org/works"
    EUROPEPMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    ARXIV_API = "https://export.arxiv.org/api/query"
    ATOM = "{http://www.w3.org/2005/Atom}"
    ARXIV_NS = "{http://arxiv.org/schemas/atom}"

    TAG_RE = re.compile(r"<[^>]+>")

    # ---------- HTTP ----------

    @classmethod
    def _wait(cls, source: str) -> None:
        wait = cls.DELAYS[source] - (time.monotonic() - cls._last_call.get(source, 0.0))
        if wait > 0:
            time.sleep(wait)
        cls._last_call[source] = time.monotonic()

    @classmethod
    def _get(cls, source: str, url: str, params: dict | None = None, headers: dict | None = None) -> requests.Response | None:
        """GET com pausa por API e retry; None se o registro não existe (404)."""
        headers = dict(headers or {})
        if CONTACT_EMAIL:
            headers["User-Agent"] = f"sar-review-pipeline (mailto:{CONTACT_EMAIL})"
        for attempt in range(cls.MAX_RETRIES + 1):
            cls._wait(source)
            try:
                response = requests.get(url, params=params, headers=headers, timeout=cls.TIMEOUT)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == cls.MAX_RETRIES:
                    raise
                time.sleep(cls.BACKOFF * 2**attempt)
                continue
            if response.status_code == 404:
                return None
            if response.status_code in cls.RETRY_STATUS and attempt < cls.MAX_RETRIES:
                time.sleep(cls.BACKOFF * 2**attempt)
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("inalcançável")

    # ---------- cache ----------

    @classmethod
    def cache_key(cls, source: str, work: Work) -> str:
        # o arXiv não tem busca por DOI, então é sempre por título
        if work.doi and source != "arxiv":
            return f"doi:{work.doi}"
        return f"title:{Downloader.normalize_title(work.title or '')}|{work.publication_year}"

    @classmethod
    def load_cache(cls, source: str) -> dict:
        if source not in cls._cache:
            cls._cache[source] = {}
            path = cls.CACHE_DIR / f"{source}.jsonl"
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        entry = json.loads(line)
                        cls._cache[source][entry["key"]] = entry["result"]
        return cls._cache[source]

    @classmethod
    def save_to_cache(cls, source: str, key: str, result: dict | None) -> None:
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cls.CACHE_DIR / f"{source}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "result": result}, ensure_ascii=False) + "\n")
        cls._cache[source][key] = result

    @classmethod
    def lookup(cls, source: str, work: Work) -> dict | None:
        """Resposta da fonte para o work, do cache ou da API."""
        cache = cls.load_cache(source)
        key = cls.cache_key(source, work)
        if key in cache:
            return cache[key]
        result = getattr(cls, f"_from_{source}")(work)
        cls.save_to_cache(source, key, result)
        return result

    # ---------- comparação e limpeza ----------

    @classmethod
    def clean_text(cls, text: str | None) -> str | None:
        """Tira tags (JATS da Crossref, HTML da Europe PMC) e espaços repetidos."""
        if not text:
            return None
        text = html.unescape(cls.TAG_RE.sub(" ", text))
        return " ".join(text.split()) or None

    @classmethod
    def title_matches(cls, work: Work, title: str | None, year: int | None) -> bool:
        if not work.title or not title or not work.publication_year:
            return False
        if year != work.publication_year:
            return False
        wanted = Downloader.normalize_title(work.title)
        similarity = SequenceMatcher(None, wanted, Downloader.normalize_title(title)).ratio()
        return similarity >= TITLE_MIN_SIMILARITY

    @classmethod
    def found(cls, abstract: str | None, matched_by: str, title: str | None, year: int | None) -> dict | None:
        abstract = cls.clean_text(abstract)
        if not abstract:
            return None
        return {"abstract": abstract, "matched_by": matched_by, "title": title, "year": year}

    # ---------- fontes: cada uma devolve found(...) ou None ----------

    @classmethod
    def _from_semantic_scholar(cls, work: Work) -> dict | None:
        headers = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}
        params = {"fields": "title,abstract,year"}
        if work.doi:
            response = cls._get("semantic_scholar", f"{cls.S2_API}/DOI:{work.doi}", params, headers)
            if response is None:
                return None
            paper = response.json()
            return cls.found(paper.get("abstract"), "doi", paper.get("title"), paper.get("year"))

        if not work.title:
            return None
        params["query"] = work.title
        response = cls._get("semantic_scholar", f"{cls.S2_API}/search/match", params, headers)
        if response is None:
            return None
        for paper in response.json().get("data") or []:
            if cls.title_matches(work, paper.get("title"), paper.get("year")):
                return cls.found(paper.get("abstract"), "titulo", paper.get("title"), paper.get("year"))
        return None

    @classmethod
    def crossref_year(cls, item: dict) -> int | None:
        parts = (item.get("issued") or {}).get("date-parts") or [[None]]
        return parts[0][0] if parts[0] else None

    @classmethod
    def _from_crossref(cls, work: Work) -> dict | None:
        params = {"mailto": CONTACT_EMAIL} if CONTACT_EMAIL else {}
        if work.doi:
            response = cls._get("crossref", f"{cls.CROSSREF_API}/{quote(work.doi, safe='/')}", params)
            if response is None:
                return None
            item = response.json().get("message") or {}
            title = (item.get("title") or [None])[0]
            return cls.found(item.get("abstract"), "doi", title, cls.crossref_year(item))

        if not work.title:
            return None
        params.update({"query.bibliographic": work.title, "rows": 5, "select": "title,abstract,issued"})
        response = cls._get("crossref", cls.CROSSREF_API, params)
        if response is None:
            return None
        for item in (response.json().get("message") or {}).get("items") or []:
            title = (item.get("title") or [None])[0]
            year = cls.crossref_year(item)
            if cls.title_matches(work, title, year):
                return cls.found(item.get("abstract"), "titulo", title, year)
        return None

    @classmethod
    def _from_europepmc(cls, work: Work) -> dict | None:
        """Europe PMC indexa o PubMed (fonte MED), então cobre os dois."""
        if work.doi:
            query = f'DOI:"{work.doi}"'
            matched_by = "doi"
        elif work.title:
            query = f'TITLE:"{Downloader.normalize_title(work.title)}"'
            matched_by = "titulo"
        else:
            return None
        params = {"query": query, "format": "json", "resultType": "core", "pageSize": 5}
        response = cls._get("europepmc", cls.EUROPEPMC_API, params)
        if response is None:
            return None
        for item in (response.json().get("resultList") or {}).get("result") or []:
            year = int(item["pubYear"]) if str(item.get("pubYear", "")).isdigit() else None
            if matched_by == "titulo" and not cls.title_matches(work, item.get("title"), year):
                continue
            return cls.found(item.get("abstractText"), matched_by, item.get("title"), year)
        return None

    @classmethod
    def _from_arxiv(cls, work: Work) -> dict | None:
        """
        Busca por título. Aceita a entrada se o DOI informado no arXiv bater com o
        do work ou, se não, pela mesma regra de título + ano das outras fontes.
        """
        if not work.title:
            return None
        wanted = Downloader.normalize_title(work.title)
        params = {"search_query": f'ti:"{wanted}"', "max_results": 5}
        response = cls._get("arxiv", cls.ARXIV_API, params)
        if response is None:
            return None
        root = ET.fromstring(response.content)
        for entry in root.iter(f"{cls.ATOM}entry"):
            title = " ".join((entry.findtext(f"{cls.ATOM}title") or "").split())
            published = entry.findtext(f"{cls.ATOM}published") or ""
            year = int(published[:4]) if published[:4].isdigit() else None
            arxiv_doi = (entry.findtext(f"{cls.ARXIV_NS}doi") or "").lower()
            if work.doi and arxiv_doi == work.doi:
                return cls.found(entry.findtext(f"{cls.ATOM}summary"), "doi", title, year)
            if cls.title_matches(work, title, year):
                return cls.found(entry.findtext(f"{cls.ATOM}summary"), "titulo", title, year)
        return None

    # ---------- cascata ----------

    @classmethod
    def find_abstract(cls, work: Work) -> dict:
        """
        Percorre SOURCES até achar um abstract válido. Devolve
        {abstract, abstract_source, abstract_match, abstract_status, abstract_flags, rejected, errors}.
        abstract_status fica "invalido" se alguma fonte devolveu texto mas nenhum passou na validação.
        """
        result = {
            "abstract": None,
            "abstract_source": None,
            "abstract_match": None,
            "abstract_status": "ausente",
            "abstract_flags": [],
            "rejected": [],
            "errors": [],
        }
        for source in cls.SOURCES:
            if source == "openalex":
                text = work.abstract
                matched_by = "registro"
            else:
                try:
                    hit = cls.lookup(source, work)
                except (requests.RequestException, ValueError, ET.ParseError) as e:
                    result["errors"].append(f"[{source}] {e}")
                    continue
                text = hit["abstract"] if hit else None
                matched_by = hit["matched_by"] if hit else None

            status, reason = AbstractValidator.validate(text)
            if status == "ok":
                result.update(
                    abstract=text,
                    abstract_source=source,
                    abstract_match=matched_by,
                    abstract_status="ok",
                    abstract_flags=AbstractValidator.suspect_flags(text, work),
                )
                return result
            if status == "invalido":
                result["abstract_status"] = "invalido"
                result["rejected"].append(
                    {"source": source, "reason": reason, "words": len(text.split()), "text": text[:300]}
                )
        return result
