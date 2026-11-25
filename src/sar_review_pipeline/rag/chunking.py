"""
    Esse arquivo realiza o chunking de cada artigo, etapa 1 do RAG
"""
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from sar_review_pipeline.rounds import FULLTEXT_TEXT, pop_round
from sar_review_pipeline.work import Work


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
        # trecho sem pontuação de frase (tabela, lista) que ainda passa do teto: janelas de max_words palavras
        out = []
        for piece in pieces:
            words = piece.split()
            if len(words) <= self.hard_max_words:
                out.append(piece)
            else:
                out += [" ".join(words[i:i + self.max_words]) for i in range(0, len(words), self.max_words)]
        return out

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
                    # fecha o chunk da secao que acabou (end_* ainda sao da linha anterior)
                    if text:
                        counter += self._close_chunk(prev_line, counter, start_page, end_page, start_para, end_para, text)
                        text = ""
                    prev_section = current_section

                # paragrafo gigante e quebrado em frases; os pedacos herdam pagina e para da linha
                for piece in self._split_paragraph(line_jsoned["text"]):
                    # juntar o pedaco estouraria o teto: fecha o chunk atual antes, se ele terminou uma frase
                    # ou se já passou do max_words (o teto vale mesmo sem fim de frase)
                    n = len(text.split())
                    if text and n + len(piece.split()) > self.hard_max_words and (self._ended_sentence(text) or n >= self.max_words):
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

    def drop_headers(self) -> int:
        """
            Tira o chunk de cabeçalho de cada artigo (título, autores, afiliações): o primeiro chunk,
            sem seção, quando o artigo tem seções depois e o chunk não traz o abstract.
            Ele subia para o topo das buscas sem responder a nenhuma QP. Devolve quantos saíram.
        """
        chunks = [json.loads(c) for c in self.chunks]
        sectioned = {c["key"] for c in chunks if c["section"]}
        first: dict[str, str] = {}
        for c in chunks:
            first.setdefault(c["key"], c["chunk_id"])
        drop = {
            c["chunk_id"] for c in chunks
            if first[c["key"]] == c["chunk_id"] and not c["section"] and c["key"] in sectioned
            and "abstract" not in c["text"].lower()
        }
        self.chunks = [json.dumps(c, ensure_ascii=False) for c in chunks if c["chunk_id"] not in drop]
        return len(drop)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as out:
            for chunk in self.chunks:
                out.write(chunk + "\n")


def main():
    # uv run step05-chunk --round N  -> chunks dos incluídos no cluster da rodada que têm texto extraído
    rnd, _ = pop_round(sys.argv[1:])
    if not rnd.included.exists():
        sys.exit(f"{rnd.included} não existe: rode antes a etapa 03 da rodada {rnd.n}")
    keys = {w.rsplit("/", 1)[-1] for w in Work.load_jsonl(str(rnd.included))}
    texts = {p.stem: p for p in FULLTEXT_TEXT.glob("*.jsonl")}
    chunker = Chunker()
    for key in sorted(keys & set(texts)):
        chunker.chunkenize(texts[key])
    dropped = chunker.drop_headers()
    chunker.save(rnd.chunks)

    n_papers = len({json.loads(c)["key"] for c in chunker.chunks})
    print(f"{rnd.name}: {len(keys)} incluídos, {len(keys & set(texts))} com texto extraído"
          f" (sem texto: rode  uv run step04-fulltext extract  ou veja a fila manual)")
    print(f"{len(chunker.chunks)} chunks de {n_papers} artigos ({dropped} cabeçalhos removidos) -> {rnd.chunks}")


if __name__ == "__main__":
    main()
