"""
    Esse arquivo realiza o chunking de cada artigo, etapa 1 do RAG
"""
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Chunk:
    chunk_id: str
    id: str
    key: str
    kind: str
    section: str
    page_start: int | None
    page_end: int | None
    para_start: int
    para_end: int
    text: str


class Chunker:
    def __init__(self, max_words: int = 250, hard_max_words: int = 350, min_words: int = 40):
        self.chunks = []
        self.max_words = max_words  # alvo: passou disso e terminou uma frase, fecha o chunk
        self.hard_max_words = hard_max_words  # teto: nenhum chunk deve passar disso (limite do embedding ~512 tokens)
        self.min_words = min_words  # chunk menor que isso e colado no anterior da mesma secao

    @staticmethod
    def _ended_sentence(text: str) -> bool:
        return text.rstrip().rstrip("\"'”’)]").endswith((".", "!", "?"))

    def _split_paragraph(self, text: str) -> list[str]:
        """
            Paragrafo gigante (acima do teto) vira pedacos de ~max_words, quebrando so no fim de frase.
            Os pedacos sao trechos literais do paragrafo, so o espaco entre eles e normalizado.
        """
        if len(text.split()) <= self.hard_max_words:
            return [text]
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(\[])", text)
        pieces = []
        current = ""
        for s in sentences:
            if current and len(current.split()) + len(s.split()) > self.max_words:
                pieces.append(current)
                current = s
            else:
                current = f"{current} {s}" if current else s
        pieces.append(current)
        return pieces

    def _close_chunk(self, d, counter, start_page, end_page, start_para, end_para, text) -> int:
        """
            Builds the Chunk from the metadata of its last line (d) and stores it.
            Chunk pequeno demais e colado no anterior se for da mesma secao (nao cria chunk novo).
            Devolve quantos chunks novos foram criados (0 ou 1), para o counter acompanhar.
        """
        n_words = len(text.split())
        # se nao tiver um minimo, adiciona no ultimo chunk salvo
        if n_words < self.min_words and self.chunks:
            last = json.loads(self.chunks[-1])
            if (last["key"] == d["key"] and last["section"] == d["section"]
                    and len(last["text"].split()) + n_words <= self.hard_max_words):
                last["text"] = f"{last['text']} {text}"
                last["page_end"] = end_page
                last["para_end"] = end_para
                self.chunks[-1] = json.dumps(last, ensure_ascii=False)
                return 0

        c = Chunk(
            chunk_id=f"{d['key']}:{counter}",
            id=d["id"], key=d["key"], kind=d["kind"], section=d["section"],
            page_start=start_page, page_end=end_page, para_start=start_para, para_end=end_para,
            text=text,
        )
        self.chunks.append(json.dumps(asdict(c), ensure_ascii=False))
        return 1

    def chunkenize(self, path: Path):
        """
            Opens an article, transform it into chunks
        """
        text = ""
        prev_section = ""
        prev_line = None
        counter = 0
        start_page = 1
        end_page = 1
        start_para = 1
        end_para = 1
        with open(path, mode="r", encoding="utf-8") as f:
            # junta o text até acabar
            for line in f:
                if not line.strip():
                    continue
                line_jsoned = json.loads(line)

                current_section = line_jsoned["section"]

                if (prev_section != current_section):
                    print(f"END OF SECTION: {prev_section},  PAGE_START - PAGE_END : {start_page} - {end_page}")
                    print(f"START-PARA - END-PARA {start_para} - {end_para}")
                    print()
                    print("\nSTARTING SECTION", current_section)
                    # fecha o chunk da secao que acabou (end_* ainda sao da linha anterior)
                    if text:
                        counter += self._close_chunk(prev_line, counter, start_page, end_page, start_para, end_para, text)
                        text = ""
                    prev_section = current_section

                # paragrafo gigante e quebrado em frases; os pedacos herdam pagina e para da linha
                for piece in self._split_paragraph(line_jsoned["text"]):
                    # juntar o pedaco estouraria o teto: fecha o chunk atual antes (se ele terminou uma frase)
                    if text and len(text.split()) + len(piece.split()) > self.hard_max_words and self._ended_sentence(text):
                        counter += self._close_chunk(prev_line, counter, start_page, end_page, start_para, end_para, text)
                        text = ""

                    # primeira linha de um chunk: marca onde ele comeca
                    if text == "":
                        start_page = line_jsoned["page"]
                        start_para = line_jsoned["para"]

                    # acumula o texto (espaco entre paragrafos, texto intacto)
                    text = f"{text} {piece}" if text else piece

                    # page_end existe nos jsonl novos (paragrafo que atravessa pagina); nos antigos cai em page
                    end_page = line_jsoned.get("page_end", line_jsoned["page"])
                    end_para = line_jsoned["para"]
                    prev_line = line_jsoned

                    # passou do max_words e o paragrafo termina uma frase: fecha o chunk
                    # (se terminar no meio da frase, espera o proximo paragrafo)
                    if len(text.split()) >= self.max_words and self._ended_sentence(text):
                        counter += self._close_chunk(line_jsoned, counter, start_page, end_page, start_para, end_para, text)
                        text = ""

        # a ultima secao do arquivo nao tem "proxima" para fecha-la
        if text:
            self._close_chunk(prev_line, counter, start_page, end_page, start_para, end_para, text)

    def save(self, path: Path):
        with open(path, "w", encoding="utf-8") as out:
            for chunk in self.chunks:
                out.write(chunk + "\n")

def main():
    ROOT = Path(__file__).resolve().parents[3]
    papers_dir = ROOT / "data" / "fulltext" / "text"    # ajuste para a pasta dos .jsonl da Fase 04
    out_path = ROOT / "data" / "fulltext" / "chunks.jsonl" 

    chunker = Chunker()
    for p in sorted(papers_dir.glob("*.jsonl")):
        chunker.chunkenize(p)
    chunker.save(out_path)

    n_papers = len({json.loads(c)["key"] for c in chunker.chunks})
    print(f"{len(chunker.chunks)} chunks de {n_papers} artigos -> {out_path}")


if __name__ == "__main__":
    main()
