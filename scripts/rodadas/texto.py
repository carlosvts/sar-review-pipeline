"""
Extração e chunks no padrão das rodadas 2 e 3 (data/fulltext/), com as classes do pipeline (Extractor, Chunker).
Os comandos step04-fulltext extract e step05-chunk do pipeline por rodada gravam em data/rounds/; este script
só troca os caminhos.

  uv run python scripts/rodadas/texto.py extract
  uv run python scripts/rodadas/texto.py chunk <included.jsonl> <chunks.jsonl>
"""
import json
import sys
from pathlib import Path

from sar_review_pipeline.fulltext.extract import Extractor
from sar_review_pipeline.rag.chunking import Chunker
from sar_review_pipeline.work import Work

DOCS = Path("data/fulltext/docs")
TEXT = Path("data/fulltext/text")


class Texto:
    @classmethod
    def extract(cls) -> dict:
        results = Extractor.extract_all(DOCS, TEXT)
        counts = {"documentos": len(results), "com_texto": 0, "para_conferir": {}}
        for r in results:
            if r["n_paragraphs"]:
                counts["com_texto"] += 1
            if r["flags"]:
                counts["para_conferir"][r["key"]] = "; ".join(r["flags"])
        return counts

    @classmethod
    def chunk(cls, included_path: Path, chunks_path: Path) -> dict:
        keys = set()
        for work_id in Work.load_jsonl(str(included_path)):
            keys.add(work_id.rsplit("/", 1)[-1])
        texts = {}
        for path in TEXT.glob("*.jsonl"):
            texts[path.stem] = path
        chunker = Chunker()
        for key in sorted(keys & set(texts)):
            chunker.chunkenize(texts[key])
        dropped = chunker.drop_headers()
        chunker.save(chunks_path)

        papers = set()
        for c in chunker.chunks:
            papers.add(json.loads(c)["key"])
        return {"incluidos": len(keys), "com_texto": len(keys & set(texts)), "sem_texto": sorted(keys - set(texts)),
                "chunks": len(chunker.chunks), "artigos": len(papers), "cabecalhos_removidos": dropped,
                "saida": str(chunks_path)}


def main():
    if sys.argv[1:2] == ["extract"]:
        print(json.dumps(Texto.extract(), ensure_ascii=False, indent=1))
    elif sys.argv[1:2] == ["chunk"] and len(sys.argv) == 4:
        print(json.dumps(Texto.chunk(Path(sys.argv[2]), Path(sys.argv[3])), ensure_ascii=False, indent=1))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
