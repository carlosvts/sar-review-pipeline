"""
    Esse arquivo realiza o chunking de cada artigo, etapa 1 do RAG
"""
import json
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
    def __init__(self, max_words: int = 250):
        self.chunks = []
        self.max_words = max_words

    def _close_chunk(self, d, counter, start_page, end_page, start_para, end_para, text):
        """
            Builds the Chunk from the metadata of its last line (d) and stores it
        """
        c = Chunk(
            chunk_id=f"{d['key']}:{counter}",
            id=d["id"], key=d["key"], kind=d["kind"], section=d["section"],
            page_start=start_page, page_end=end_page, para_start=start_para, para_end=end_para,
            text=text,
        )
        self.chunks.append(json.dumps(asdict(c), ensure_ascii=False))

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
                        self._close_chunk(prev_line, counter, start_page, end_page, start_para, end_para, text)
                        counter += 1
                        text = ""
                    prev_section = current_section

                # primeira linha de um chunk: marca onde ele comeca
                if text == "":
                    start_page = line_jsoned["page"]
                    start_para = line_jsoned["para"]

                # acumula o texto (espaco entre paragrafos, texto intacto)
                text = f"{text} {line_jsoned['text']}" if text else line_jsoned["text"]

                end_page = line_jsoned["page"]
                end_para = line_jsoned["para"]
                prev_line = line_jsoned

                # passou do max_words e o paragrafo termina uma frase: fecha o chunk
                # (se terminar no meio da frase, espera o proximo paragrafo)
                ended_sentence = text.rstrip().rstrip("\"'”’)]").endswith((".", "!", "?"))
                if len(text.split()) >= self.max_words and ended_sentence:
                    self._close_chunk(line_jsoned, counter, start_page, end_page, start_para, end_para, text)
                    counter += 1
                    text = ""

        # a ultima secao do arquivo nao tem "proxima" para fecha-la
        if text:
            self._close_chunk(prev_line, counter, start_page, end_page, start_para, end_para, text)

    def save(self, path: Path):
        with open(path, "w", encoding="utf-8") as out:
            for chunk in self.chunks:
                out.write(chunk + "\n")

if __name__ == "__main__":
    papers_dir = Path("/home/carlosvts/coding/ic/sar-review-pipeline/data/fulltext/text")      # ajuste para a pasta dos .jsonl da Fase 04
    out_path = Path("/home/carlosvts/coding/ic/sar-review-pipeline/data/fulltext/chunks.jsonl")

    chunker = Chunker()
    for p in sorted(papers_dir.glob("*.jsonl")):
        chunker.chunkenize(p)
    chunker.save(out_path)

    n_papers = len({json.loads(c)["key"] for c in chunker.chunks})
    print(f"{len(chunker.chunks)} chunks de {n_papers} artigos -> {out_path}")
