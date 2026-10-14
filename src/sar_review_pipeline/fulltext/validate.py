"""
    O objetivo principal desse arquivo é: dado um artigo baixado, identificar
    se ele é utilizável ou não
"""
import os
import xml.etree.ElementTree as ET


class Validator:
    MIN_PDF_SIZE = 10_000  # 10 KB, em bytes
    MIN_XML_BODY_CHARS = 2_000  # texto mínimo no <body> para contar como texto completo
    PDF_HEADER = b"%PDF-"
    PDF_EOF = b"%%EOF"
    TAIL_SIZE = 1024
    HEAD_SIZE = 1024

    @classmethod
    def detect_kind(cls, path: str) -> str | None:
        """'pdf', 'xml' ou None, olhando os primeiros bytes (não confia na extensão nem no Content-Type)."""
        with open(path, mode="rb") as f:
            head = f.read(cls.HEAD_SIZE)
        if head.startswith(cls.PDF_HEADER):
            return "pdf"
        stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")  # BOM e espaços
        if stripped.lower().startswith((b"<!doctype html", b"<html")):
            return None
        if stripped.startswith((b"<?xml", b"<article", b"<pmc-articleset", b"<!DOCTYPE")):
            return "xml"
        return None

    @classmethod
    def validate_pdf(cls, path: str) -> tuple[bool, str]:
        size = os.path.getsize(path)
        with open(path, mode="rb") as f:
            if f.read(len(cls.PDF_HEADER)) != cls.PDF_HEADER:
                return (False, "Não começa com %PDF-")
            if size < cls.MIN_PDF_SIZE:
                return (False, f"PDF menor que {cls.MIN_PDF_SIZE // 1000}KB")
            f.seek(max(size - cls.TAIL_SIZE, 0))
            if cls.PDF_EOF not in f.read():
                return (False, "Sem %%EOF no final (download truncado?)")
        return (True, "")

    @classmethod
    def validate_xml(cls, path: str) -> tuple[bool, str]:
        """
        XML JATS: bem formado, com um <article> (na raiz, como na Europe PMC, ou
        dentro de <pmc-articleset>, como no efetch do NCBI) e um <body> com texto.
        """
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as e:
            return (False, f"XML inválido ({e})")
        local = lambda el: el.tag.rsplit("}", 1)[-1]
        if local(root) == "pmc-articleset":
            article = next((el for el in root if local(el) == "article"), None)
            if article is None:
                return (False, "<pmc-articleset> sem <article> (PMCID inexistente?)")
            root = article
        if local(root) != "article":
            return (False, f"Raiz do XML não é <article> ({root.tag})")
        body = next((el for el in root.iter() if local(el) == "body"), None)
        if body is None:
            return (False, "XML sem <body> (só metadados, sem texto completo)")
        n_chars = len("".join(body.itertext()).strip())
        if n_chars < cls.MIN_XML_BODY_CHARS:
            return (False, f"<body> do XML com pouco texto ({n_chars} caracteres)")
        return (True, "")

    @classmethod
    def validate(cls, path: str) -> tuple[bool, str, str | None]:
        """Devolve (ok, motivo, tipo), com tipo 'pdf' ou 'xml'."""
        if not os.path.exists(path):
            return (False, "Arquivo não existe", None)
        if os.path.getsize(path) == 0:
            return (False, "Arquivo vazio", None)
        kind = cls.detect_kind(path)
        if kind == "pdf":
            return (*cls.validate_pdf(path), kind)
        if kind == "xml":
            return (*cls.validate_xml(path), kind)
        with open(path, mode="rb") as f:
            head = f.read(200).lower()
        if b"<html" in head or b"<!doctype html" in head:
            return (False, "Recebeu HTML em vez de PDF/XML (paywall ou bloqueio?)", None)
        return (False, "Não é PDF nem XML", None)
