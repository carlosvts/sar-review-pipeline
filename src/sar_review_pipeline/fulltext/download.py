import csv
import html
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from sar_review_pipeline.fulltext.validate import Validator
from sar_review_pipeline.work import Work


class Downloader:
    DEFAULT_DIR = Path("data/fulltext/docs")
    CONTACT_EMAIL = "carlosvtsdev@gmail.com"
    USER_AGENT = f"sar-review-pipeline (mailto:{CONTACT_EMAIL})"
    TIMEOUT = (10, 60)  # (conexão, leitura) em segundos
    CHUNK_SIZE = 64 * 1024
    DELAY = 1.0  # pausa entre works, em segundos

    # retry só para erros transitórios; 403/404 não adiantam repetir
    MAX_RETRIES = 2
    RETRY_STATUS = {429, 500, 502, 503, 504}
    BACKOFF = 5.0  # segundos, dobra a cada tentativa
    MAX_RETRY_AFTER = 60.0

    # APIs (atributos de classe para poder trocar em teste)
    EUROPEPMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    EUROPEPMC_RENDER = "https://europepmc.org/backend/ptpmcrender.fcgi"
    NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    S2_API = "https://api.semanticscholar.org/graph/v1/paper"
    CROSSREF_API = "https://api.crossref.org/works"
    ARXIV_API = "https://export.arxiv.org/api/query"
    ARXIV_DELAY = 3.0  # o arXiv pede no mínimo 3 s entre chamadas à API
    ARXIV_MIN_TITLE_SIMILARITY = 0.9
    _arxiv_last_call = 0.0
    ATOM = "{http://www.w3.org/2005/Atom}"

    # ordem da cascata; cada nome corresponde a um método _from_<nome>
    SOURCES = ["openalex", "pmc", "crossref", "landing_meta", "semantic_scholar", "arxiv_title"]

    PMCID_RE = re.compile(r"PMC(\d+)", re.I)
    NCBI_PMC_RE = re.compile(r"ncbi\.nlm\.nih\.gov/pmc/articles/(\d+)", re.I)

    # URLs que o Semantic Scholar devolve como "openAccessPdf" mas são páginas, não arquivos
    # landing page: meta tags que apontam para o PDF (padrão Highwire/Google Scholar e repositórios)
    PDF_META_NAMES = {"citation_pdf_url", "bepress_citation_pdf_url", "eprints.document_url"}
    META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.I)
    ATTR_RE = re.compile(r'([\w:.-]+)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)')
    MAX_LANDING_PAGES = 3
    MAX_HTML_BYTES = 1_000_000

    # Crossref: só links de texto completo pensados para mineração (ou sem finalidade declarada)
    CROSSREF_APPLICATIONS = {"text-mining", "unspecified"}
    CROSSREF_SKIP_HOSTS = {"api.elsevier.com", "api.wiley.com"}  # exigem token próprio

    MANUAL_DIR = Path("data/fulltext")

    LANDING_PAGE_PATTERNS = [
        re.compile(r"^https?://(dx\.)?doi\.org/", re.I),
        re.compile(r"figshare\.com/articles/", re.I),
        re.compile(r"/(en/)?publications/[^/]+/?$", re.I),  # páginas do Pure (research.*)
        re.compile(r"ncbi\.nlm\.nih\.gov/pmc/articles/\d+/?$", re.I),
        re.compile(r"pmc\.ncbi\.nlm\.nih\.gov/articles/PMC\d+/?$", re.I),
    ]

    # ---------- HTTP ----------

    @classmethod
    def _request(cls, url: str, **kwargs) -> requests.Response:
        """GET com retry/backoff para 429, 5xx, timeout e erro de conexão."""
        headers = {"User-Agent": cls.USER_AGENT, **kwargs.pop("headers", {})}
        for attempt in range(cls.MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, timeout=cls.TIMEOUT, **kwargs)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == cls.MAX_RETRIES:
                    raise
                time.sleep(cls.BACKOFF * 2**attempt)
                continue
            if response.status_code in cls.RETRY_STATUS and attempt < cls.MAX_RETRIES:
                wait = cls.BACKOFF * 2**attempt
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    wait = min(float(retry_after), cls.MAX_RETRY_AFTER)
                response.close()
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("inalcançável")

    @classmethod
    def _get_json(cls, url: str, **kwargs) -> dict | None:
        """JSON de uma API; None se o registro não existe (404) ou a API falhar."""
        try:
            return cls._request(url, **kwargs).json()
        except (requests.RequestException, ValueError):
            return None

    @classmethod
    def fetch(cls, url: str, tmp_path: Path) -> None:
        """Baixa a url para tmp_path. Levanta requests.RequestException se falhar."""
        with cls._request(url, stream=True) as response:
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_content(cls.CHUNK_SIZE):
                    f.write(chunk)

    # ---------- fontes: cada uma gera (fonte, url) ----------

    @classmethod
    def _from_openalex(cls, work: Work) -> Iterator[tuple[str, str]]:
        for loc in work.oa_locations:
            if loc.get("pdf_url"):
                yield ("openalex", loc["pdf_url"])

    @classmethod
    def find_pmcid(cls, work: Work) -> str | None:
        """PMCID pelas landing pages do OpenAlex; se não houver, busca o DOI na Europe PMC."""
        for loc in work.oa_locations:
            url = loc.get("landing_page_url") or ""
            if m := cls.PMCID_RE.search(url) or cls.NCBI_PMC_RE.search(url):
                return f"PMC{m.group(1)}"
        if not work.doi:
            return None
        data = cls._get_json(
            f"{cls.EUROPEPMC_API}/search",
            params={"query": f'DOI:"{work.doi}"', "format": "json", "resultType": "lite", "pageSize": 1},
        )
        results = ((data or {}).get("resultList") or {}).get("result") or []
        return results[0].get("pmcid") if results else None

    @classmethod
    def _from_pmc(cls, work: Work) -> Iterator[tuple[str, str]]:
        """
        Mesmo texto do PMC por duas APIs: se a Europe PMC falhar (já devolveu 500),
        tenta o efetch do NCBI. O PDF renderizado da Europe PMC fica por último.
        """
        pmcid = cls.find_pmcid(work)
        if not pmcid:
            return
        yield ("europepmc_xml", f"{cls.EUROPEPMC_API}/{pmcid}/fullTextXML")
        query = f"db=pmc&id={pmcid[3:]}&tool=sar-review-pipeline&email={cls.CONTACT_EMAIL}"
        yield ("ncbi_pmc_xml", f"{cls.NCBI_EFETCH}?{query}")
        yield ("europepmc_pdf", f"{cls.EUROPEPMC_RENDER}?accid={pmcid}&blobtype=pdf")

    @classmethod
    def _from_crossref(cls, work: Work) -> Iterator[tuple[str, str]]:
        """Links de texto completo que a editora depositou no metadado do DOI."""
        if not work.doi:
            return
        data = cls._get_json(f"{cls.CROSSREF_API}/{work.doi}", params={"mailto": cls.CONTACT_EMAIL})
        for link in ((data or {}).get("message") or {}).get("link") or []:
            url = link.get("URL") or ""
            if not url or urlparse(url).hostname in cls.CROSSREF_SKIP_HOSTS:
                continue
            if link.get("intended-application", "unspecified") not in cls.CROSSREF_APPLICATIONS:
                continue  # ex.: similarity-checking é para o iThenticate, não para leitura
            content_type = (link.get("content-type") or "unspecified").lower()
            if content_type in {"application/pdf", "application/xml", "text/xml", "unspecified"}:
                yield ("crossref", url)

    @classmethod
    def pdf_urls_from_html(cls, page: str, base_url: str) -> list[str]:
        """Valores das meta tags citation_pdf_url & cia., resolvidos contra a URL final."""
        urls = []
        for tag in cls.META_TAG_RE.findall(page):
            attrs = {k.lower(): html.unescape(v.strip("\"'")) for k, v in cls.ATTR_RE.findall(tag)}
            if attrs.get("name", "").lower() in cls.PDF_META_NAMES and attrs.get("content"):
                urls.append(urljoin(base_url, attrs["content"]))
        return urls

    @classmethod
    def landing_pages(cls, work: Work) -> list[str]:
        pages = [loc["landing_page_url"] for loc in work.oa_locations if loc.get("landing_page_url")]
        if work.doi:
            pages.append(f"https://doi.org/{work.doi}")
        unique = []
        for url in pages:
            # o PMC já é tratado pela fonte pmc, e a web do PMC bloqueia scripts
            if url not in unique and not re.search(r"ncbi\.nlm\.nih\.gov|europepmc\.org", url):
                unique.append(url)
        return unique[: cls.MAX_LANDING_PAGES]

    @classmethod
    def _from_landing_meta(cls, work: Work) -> Iterator[tuple[str, str]]:
        """Abre a landing page e lê a meta tag citation_pdf_url (o que o Google Scholar usa)."""
        for page_url in cls.landing_pages(work):
            try:
                with cls._request(page_url, stream=True) as response:
                    if "html" not in response.headers.get("Content-Type", "").lower():
                        continue
                    raw = response.raw.read(cls.MAX_HTML_BYTES, decode_content=True)
                    final_url = response.url
            except requests.RequestException:
                continue
            page = raw.decode(response.encoding or "utf-8", errors="replace")
            for pdf_url in cls.pdf_urls_from_html(page, final_url):
                yield ("landing_meta", pdf_url)

    @classmethod
    def looks_like_landing_page(cls, url: str) -> bool:
        return any(p.search(url) for p in cls.LANDING_PAGE_PATTERNS)

    @classmethod
    def _from_semantic_scholar(cls, work: Work) -> Iterator[tuple[str, str]]:
        if not work.doi:
            return
        headers = {}
        if key := os.environ.get("S2_API_KEY"):
            headers["x-api-key"] = key
        data = cls._get_json(
            f"{cls.S2_API}/DOI:{work.doi}",
            params={"fields": "openAccessPdf,externalIds"},
            headers=headers,
        )
        if not data:
            return
        url = (data.get("openAccessPdf") or {}).get("url")
        if url and not cls.looks_like_landing_page(url):
            yield ("semantic_scholar", url)
        if arxiv_id := (data.get("externalIds") or {}).get("ArXiv"):
            yield ("arxiv", f"https://arxiv.org/pdf/{arxiv_id}")

    @classmethod
    def normalize_title(cls, title: str) -> str:
        """Minúsculas, sem acentos e sem pontuação, para comparar títulos."""
        title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
        return " ".join(re.sub(r"[^a-z0-9]+", " ", title.lower()).split())

    @classmethod
    def surname(cls, name: str) -> str:
        return cls.normalize_title(name).split(" ")[-1] if name.strip() else ""

    @classmethod
    def _from_arxiv_title(cls, work: Work) -> Iterator[tuple[str, str]]:
        """
        Busca o título na API do arXiv. Só aceita o resultado se o título for
        quase idêntico e, quando o work tem autores, se algum sobrenome bater,
        para não baixar o paper errado.
        """
        if not work.title:
            return
        wanted = cls.normalize_title(work.title)
        if len(wanted.split()) < 4:  # título curto demais gera falso positivo
            return

        wait = cls.ARXIV_DELAY - (time.monotonic() - cls._arxiv_last_call)
        if wait > 0:
            time.sleep(wait)
        cls._arxiv_last_call = time.monotonic()
        try:
            response = cls._request(
                cls.ARXIV_API,
                params={"search_query": f'ti:"{wanted}"', "max_results": 5},
            )
            root = ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError):
            return

        surnames = {cls.surname(a) for a in work.authors if a}
        for entry in root.iter(f"{cls.ATOM}entry"):
            title = entry.findtext(f"{cls.ATOM}title") or ""
            similarity = SequenceMatcher(None, wanted, cls.normalize_title(title)).ratio()
            if similarity < cls.ARXIV_MIN_TITLE_SIMILARITY:
                continue
            entry_surnames = {
                cls.surname(a.findtext(f"{cls.ATOM}name") or "")
                for a in entry.iter(f"{cls.ATOM}author")
            }
            if surnames and not surnames & entry_surnames:
                continue
            # http://arxiv.org/abs/2101.00001v2 -> 2101.00001 (sem versão, para deduplicar com o S2)
            arxiv_id = (entry.findtext(f"{cls.ATOM}id") or "").split("/abs/")[-1]
            arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
            if arxiv_id:
                yield ("arxiv_title", f"https://arxiv.org/pdf/{arxiv_id}")

    @classmethod
    def candidates(cls, work: Work) -> Iterator[tuple[str, str]]:
        """
        Candidatas na ordem de SOURCES. É um gerador: uma API só é consultada
        se as candidatas das fontes anteriores falharem.
        """
        for source in cls.SOURCES:
            yield from getattr(cls, f"_from_{source}")(work)

    # ---------- download ----------

    @classmethod
    def work_key(cls, work: Work) -> str:
        """https://openalex.org/W123 -> W123"""
        return work.id.rsplit("/", 1)[-1]

    @classmethod
    def existing_file(cls, work: Work, dest_dir: Path = DEFAULT_DIR) -> Path | None:
        for ext in ("pdf", "xml"):
            path = dest_dir / f"{cls.work_key(work)}.{ext}"
            if path.exists() and Validator.validate(str(path))[0]:
                return path
        return None

    @classmethod
    def download_work(cls, work: Work, dest_dir: Path = DEFAULT_DIR) -> dict:
        """
        Percorre as candidatas de todas as fontes e fica com a primeira que
        baixar e validar (PDF ou XML). Devolve
        {id, ok, source, url, kind, path, reason, skipped, attempted}.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest_dir / f"{cls.work_key(work)}.part"
        result = {
            "id": work.id,
            "ok": False,
            "source": None,
            "url": None,
            "kind": None,
            "path": None,
            "reason": "",
            "skipped": False,
            "attempted": 0,
        }

        # idempotência: arquivo válido já baixado não é baixado de novo
        if existing := cls.existing_file(work, dest_dir):
            result.update(ok=True, kind=existing.suffix[1:], path=str(existing), skipped=True)
            return result

        reasons = []
        seen: set[str] = set()
        for source, url in cls.candidates(work):
            if url in seen:  # o S2 costuma repetir URLs do OpenAlex
                continue
            seen.add(url)
            result["attempted"] += 1
            try:
                cls.fetch(url, tmp)
            except requests.RequestException as e:
                reasons.append(f"[{source}] {url}: {e}")
                tmp.unlink(missing_ok=True)
                continue

            ok, reason, kind = Validator.validate(str(tmp))
            if ok:
                final = dest_dir / f"{cls.work_key(work)}.{kind}"
                tmp.replace(final)
                result.update(ok=True, source=source, url=url, kind=kind, path=str(final))
                return result
            reasons.append(f"[{source}] {url}: {reason}")
            tmp.unlink(missing_ok=True)

        result["reason"] = "; ".join(reasons) if reasons else "nenhuma candidata em nenhuma fonte"
        return result

    @classmethod
    def download_all(cls, works: dict[str, Work], dest_dir: Path = DEFAULT_DIR) -> list[dict]:
        """Roda download_work em todos os works, com pausa entre os que fizeram requisição."""
        results = []
        total = len(works)
        for i, work in enumerate(works.values(), start=1):
            result = cls.download_work(work, dest_dir)
            results.append(result)
            if result["skipped"]:
                status = f"já baixado ({result['kind']})"
            elif result["ok"]:
                status = f"baixado: {result['kind']} via {result['source']}"
            else:
                status = f"falhou ({result['attempted']} tentativas)"
            print(f"[{i}/{total}] {work.id}  {status}")
            if result["attempted"]:
                time.sleep(cls.DELAY)
        return results

    # ---------- fila manual ----------

    @classmethod
    def export_manual_queue(
        cls, results: list[dict], works: dict[str, Work], out_dir: Path = MANUAL_DIR
    ) -> tuple[Path, Path]:
        """
        Grava os works que nenhuma fonte resolveu em:
          - manual_queue.csv: para conferir/anotar (links, motivos)
          - manual_queue.ris: para importar no Zotero e rodar "Find Available PDF"
            com o acesso institucional (rede/VPN da UFLA)
        É sobrescrito a cada execução, então reflete sempre a última rodada.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        failed = [works[r["id"]] for r in results if not r["ok"]]
        reasons = {r["id"]: r["reason"] for r in results if not r["ok"]}

        csv_path = out_dir / "manual_queue.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["id", "doi", "doi_url", "title", "publication_year",
                            "backward_round", "landing_pages", "reason", "status", "local_path"],
            )
            writer.writeheader()
            for w in failed:
                writer.writerow({
                    "id": w.id,
                    "doi": w.doi or "",
                    "doi_url": f"https://doi.org/{w.doi}" if w.doi else "",
                    "title": w.title or "",
                    "publication_year": w.publication_year or "",
                    "backward_round": w.backward_round,
                    "landing_pages": " | ".join(
                        loc["landing_page_url"] for loc in w.oa_locations if loc.get("landing_page_url")
                    ),
                    "reason": reasons[w.id],
                    "status": "pending",  # você preenche: downloaded / not_retrieved
                    "local_path": "",
                })

        ris_path = out_dir / "manual_queue.ris"
        with open(ris_path, "w", encoding="utf-8") as f:
            for w in failed:
                lines = ["TY  - JOUR"]
                if w.title:
                    lines.append(f"TI  - {w.title}")
                lines += [f"AU  - {a}" for a in w.authors]
                if w.publication_year:
                    lines.append(f"PY  - {w.publication_year}")
                if w.doi:
                    lines += [f"DO  - {w.doi}", f"UR  - https://doi.org/{w.doi}"]
                lines.append(f"ID  - {cls.work_key(w)}")
                lines.append(f"N1  - OpenAlex: {w.id}")
                lines.append("ER  - ")
                f.write("\n".join(lines) + "\n\n")

        return csv_path, ris_path
