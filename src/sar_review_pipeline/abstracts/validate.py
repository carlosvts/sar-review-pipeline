"""
    Decide se um texto serve como abstract: ok, ausente ou invalido.
    Os sinais de contaminação (autores, título, palavras-chave, periódico)
    não invalidam o texto, só viram flags para conferir no relatório.
"""
import re

from sar_review_pipeline.fulltext.download import Downloader
from sar_review_pipeline.work import Work

MIN_ABSTRACT_WORDS = 20  # 20-29 entram; o que for lixo cai num cluster próprio e é excluído na revisão
MIN_TITLE_WORDS_FOR_FLAG = 5  # título curto aparece no abstract sem ser contaminação

# texto que não é abstract (nota de evento, aviso de ausência, cabeçalho de página)
BOILERPLATE_PATTERNS = (
    r"\bno abstract( is)? available\b",
    r"\babstract (is )?not available\b",
    r"^\s*international audience\s*$",
    r"^\s*full text\s*$",
    r"\bpreview this article\b",
    r"^\s*(©|\(c\)|copyright)",  # começa com aviso de copyright: não é o resumo
)

SUSPECT_PATTERNS = {
    "palavras_chave": r"\b(key ?words?|index terms)\b\s*[:—–-]",
    "periodico": r"\bISSN\b|\bvol\.\s*\d|\bpp\.\s*\d|\bproceedings of\b|\bjournal of\b",
    "copyright": r"©|\bcopyright\b|\ball rights reserved\b",
}


class AbstractValidator:
    @classmethod
    def is_boilerplate(cls, text: str) -> bool:
        for pattern in BOILERPLATE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    @classmethod
    def validate(cls, text: str | None) -> tuple[str, str]:
        """(status, motivo); status é ok, ausente ou invalido."""
        if not text or not text.strip():
            return "ausente", ""
        if cls.is_boilerplate(text):
            return "invalido", "boilerplate"
        if len(text.split()) < MIN_ABSTRACT_WORDS:
            return "invalido", "curto"
        return "ok", ""

    @classmethod
    def suspect_flags(cls, text: str, work: Work) -> list[str]:
        """Sinais de que o campo veio misturado com outros metadados."""
        flags = []
        for author in work.authors:
            if author and author in text:
                flags.append("autores")
                break

        title = Downloader.normalize_title(work.title or "")
        if len(title.split()) >= MIN_TITLE_WORDS_FOR_FLAG and title in Downloader.normalize_title(text):
            flags.append("titulo")

        for name, pattern in SUSPECT_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                flags.append(name)
        return flags
