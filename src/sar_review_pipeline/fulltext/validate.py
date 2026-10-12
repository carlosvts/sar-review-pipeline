"""
    O objetivo principal desse arquivo é: dado um artigo baixado, identificar
    se ele é utilizável ou não
"""
import os

FILE_MINIMUM_SIZE_THRESHOLD = 10_000  # 10 KB, em bytes
PDF_HEADER = b"%PDF-"
PDF_EOF = b"%%EOF"
TAIL_SIZE = 1024


class Validator:
    @classmethod
    def validate_pdf(cls, path: str) -> tuple[bool, str]:
        if not os.path.exists(path):
            return (False, "Arquivo não existe")

        size = os.path.getsize(path)
        if size < FILE_MINIMUM_SIZE_THRESHOLD:
            return (False, "Arquivo menor que 10KB")

        with open(path, mode="rb") as f:
            if f.read(len(PDF_HEADER)) != PDF_HEADER:
                return (False, "Não começa com %PDF-")

            f.seek(max(size - TAIL_SIZE, 0))
            if PDF_EOF not in f.read():
                return (False, "Sem %%EOF no final (download truncado?)")

        return (True, "")
