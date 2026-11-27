"""Cliente do OpenAlex comum ao backward e ao forward."""
from collections.abc import Iterator

import requests
from dotenv import dotenv_values
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ENV = dotenv_values(".env")
# sem key, a cota diária do OpenAlex é compartilhada por todo o IP
OPENALEX_API_KEY = ENV.get("OPENALEX_API_KEY")
# opcional: e-mail de contato do .env, enviado como mailto
CONTACT_EMAIL = ENV.get("CONTACT_EMAIL")


def short_id(work_id: str) -> str:
    """https://openalex.org/W123 -> W123 (formato dos filtros da API)."""
    return work_id.replace("https://openalex.org/", "")


def session_with_retry() -> requests.Session:
    """Sessão com retry e backoff para 429, 5xx e erro de conexão, respeitando Retry-After."""
    retry = Retry(
        total=6, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",), respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class OpenAlexClient:
    def __init__(self, base_url: str = "https://api.openalex.org"):
        self.base_url = base_url
        self.session = session_with_retry()
        if OPENALEX_API_KEY:
            self.session.headers["Authorization"] = f"Bearer {OPENALEX_API_KEY}"

    def _params(self, filter_expr: str, per_page: int, select: str | None) -> dict:
        params = {"filter": filter_expr, "per-page": per_page}
        if select:
            params["select"] = select
        if CONTACT_EMAIL:
            params["mailto"] = CONTACT_EMAIL
        return params

    def get(self, filter_expr: str, per_page: int = 50, select: str | None = None) -> list[dict]:
        """Uma página de /works com o filtro (até per_page resultados)."""
        response = self.session.get(
            f"{self.base_url}/works", params=self._params(filter_expr, per_page, select), timeout=60
        )
        response.raise_for_status()
        return response.json()["results"]

    def get_all(self, filter_expr: str, per_page: int = 200, select: str | None = None) -> Iterator[dict]:
        """Todos os resultados do filtro, paginando por cursor."""
        params = self._params(filter_expr, per_page, select)
        params["cursor"] = "*"
        while params["cursor"]:
            response = self.session.get(f"{self.base_url}/works", params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            yield from data["results"]
            params["cursor"] = data["meta"].get("next_cursor")
