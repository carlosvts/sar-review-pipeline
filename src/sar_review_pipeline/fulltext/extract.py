import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pymupdf

from sar_review_pipeline.fulltext.validate import Validator


class Extractor:
    """
    Converte os PDFs/XMLs de data/fulltext/docs/ em parágrafos com seção e página,
    um JSONL por documento em data/fulltext/text/W….jsonl. É a entrada do RAG (Fase 05).

    Cada linha: {id, key, kind, para, section, page, page_end, text}
      - section: caminho da seção ("2 Methods > 2.1 Participants"), ou "" se não identificada
      - page: página no PDF (1-based) onde o parágrafo começa; None para XML
      - page_end: página onde o parágrafo termina (difere de page quando ele atravessa páginas); None para XML
    """

    DOCS_DIR = Path("data/fulltext/docs")
    TEXT_DIR = Path("data/fulltext/text")
    OPENALEX_PREFIX = "https://openalex.org/"

    # a partir destes títulos o resto do documento é descartado (bibliografia etc.)
    STOP_SECTION_RE = re.compile(
        r"^\s*(\d+(\.\d+)*\.?\s+)?(references?|bibliography|literature cited|works cited|referências)\s*$",
        re.I,
    )
    # seções descartadas, mas o documento continua depois delas
    SKIP_SECTION_RE = re.compile(
        r"^\s*(\d+(\.\d+)*\.?\s+)?(acknowledge?ments?|funding( statement| sources?| information)?|"
        r"conflicts? of interests?( statement)?|declaration of (competing )?interests?|competing interests?|"
        r"author contributions?|data availability( statement)?|ethics statement)\s*$",
        re.I,
    )
    # títulos de seção comuns em artigos (para PDF, onde não há marcação)
    KNOWN_HEADINGS_RE = re.compile(
        r"^\s*(\d+(\.\d+)*\.?\s+)?(abstract|introduction|background|related work|literature review|"
        r"methods?|methodology|materials and methods|study design|participants|procedure|measures|"
        r"results?|findings|discussion|conclusions?|limitations|future work|implications|"
        r"appendix( [a-z])?)\s*$",
        re.I,
    )
    NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+(\.\d+){0,3}|[IVX]+)\.?\s+[A-Z][^.!?]{2,80}$")

    MIN_PARAGRAPH_CHARS = 40
    MARGIN_RATIO = 0.06  # topo/rodapé da página: faixa onde ficam cabeçalho e número de página
    MIN_ALPHA_RATIO = 0.5  # descarta blocos que são quase só números/símbolos (tabelas)
    MAX_HEADING_CHARS = 100
    MAX_HEADING_WORDS = 8  # título sem número nem nome conhecido: mais que isso é frase
    MIN_HEADING_ALPHA_RATIO = 0.8  # título é (quase) só letras: "SMAS ¼", "Chantal Huisman 1,*" não são

    # sinais de extração ruim, para conferir à mão
    MIN_DOC_PARAGRAPHS = 10
    MIN_DOC_CHARS = 8_000

    # ---------- utilidades ----------

    @classmethod
    def clean(cls, text: str) -> str:
        text = re.sub(r"(\w)-\s*\n\s*([a-z])", r"\1\2", text)  # hifenização de fim de linha
        text = text.replace("\u00ad", "")  # hífen "suave"
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)  # controle (ex.: \x07 da Springer)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def is_bold(cls, span: dict) -> bool:
        # flag de negrito ou nome da fonte (muitas editoras usam fontes "AdvOTxxxx.B", "Formata-Bold"...)
        return bool(span["flags"] & 16 or re.search(r"(bold|black|heavy|semibold|demi|[.-]b$)", span["font"].lower()))

    @classmethod
    def running_lines(cls, doc: pymupdf.Document) -> set[str]:
        """Linhas curtas que se repetem em várias páginas: cabeçalho/rodapé corrido (nome da revista, 'Article')."""
        pages_with: dict[str, set[int]] = {}
        for page_number, page in enumerate(doc):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = cls.clean("".join(s["text"] for s in line["spans"]))
                    if 0 < len(text) < 100:
                        key = re.sub(r"\d+", "#", text.lower())
                        pages_with.setdefault(key, set()).add(page_number)
        threshold = max(3, len(doc) // 2)
        return {k for k, pages in pages_with.items() if len(pages) >= threshold}

    @classmethod
    def alpha_ratio(cls, text: str) -> float:
        return sum(c.isalpha() for c in text) / max(len(text), 1)

    @classmethod
    def local(cls, el: ET.Element) -> str:
        return el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""

    # ---------- XML (JATS) ----------

    @classmethod
    def xml_text(cls, el: ET.Element) -> str:
        """Texto do elemento sem notas de rodapé, fórmulas e tabelas embutidas."""
        skip = {"table-wrap", "fig", "disp-formula", "inline-formula", "fn", "table"}
        parts = []

        def walk(node: ET.Element) -> None:
            if cls.local(node) in skip:
                if node.tail:
                    parts.append(node.tail)
                return
            if node.text:
                parts.append(node.text)
            for child in node:
                walk(child)
            if node is not el and node.tail:
                parts.append(node.tail)

        walk(el)
        return cls.clean("".join(parts))

    @classmethod
    def extract_xml(cls, path: Path) -> list[dict]:
        root = ET.parse(path).getroot()
        if cls.local(root) == "pmc-articleset":
            root = next(el for el in root if cls.local(el) == "article")

        paragraphs: list[dict] = []

        def add(section: str, text: str) -> None:
            if len(text) >= cls.MIN_PARAGRAPH_CHARS:
                paragraphs.append({"section": section, "page": None, "page_end": None, "text": text})

        # resumo (vale para as QPs)
        for abstract in root.iter():
            if cls.local(abstract) == "abstract":
                for p in abstract.iter():
                    if cls.local(p) == "p":
                        add("Abstract", cls.xml_text(p))
                break

        body = next((el for el in root.iter() if cls.local(el) == "body"), None)
        if body is None:
            return paragraphs

        def walk_sec(sec: ET.Element, path: list[str]) -> None:
            title_el = next((c for c in sec if cls.local(c) == "title"), None)
            label_el = next((c for c in sec if cls.local(c) == "label"), None)
            title = cls.xml_text(title_el) if title_el is not None else ""
            if label_el is not None and title:
                title = f"{cls.xml_text(label_el)} {title}"
            if title and cls.SKIP_SECTION_RE.match(title):
                return
            current = path + [title] if title else path
            section = " > ".join(current)
            for child in sec:
                kind = cls.local(child)
                if kind == "p":
                    add(section, cls.xml_text(child))
                elif kind == "sec":
                    walk_sec(child, current)
                elif kind in {"fig", "table-wrap"}:
                    caption = next((c for c in child.iter() if cls.local(c) == "caption"), None)
                    if caption is not None:
                        add(section, cls.xml_text(caption))
                elif kind == "list":
                    for item in child.iter():
                        if cls.local(item) == "p":
                            add(section, cls.xml_text(item))

        walk_sec(body, [])
        return paragraphs

    # ---------- PDF ----------

    @classmethod
    def body_style(cls, doc: pymupdf.Document) -> tuple[float, str]:
        """Tamanho e fonte mais frequentes (ponderados por caracteres) = texto corrido."""
        sizes: Counter = Counter()
        fonts: Counter = Counter()
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        n = len(span["text"].strip())
                        sizes[round(span["size"], 1)] += n
                        fonts[span["font"]] += n
        size = sizes.most_common(1)[0][0] if sizes else 10.0
        font = fonts.most_common(1)[0][0] if fonts else ""
        return size, font

    @classmethod
    def body_font_size(cls, doc: pymupdf.Document) -> float:
        return cls.body_style(doc)[0]

    NOT_HEADING_RE = re.compile(r"^(table|fig\.?|figure|box|scheme|chart)\s*\d|https?://|@|\bdoi\b", re.I)
    CAPTION_RE = re.compile(r"^(table|fig\.?|figure|box|scheme|chart)\s*\d", re.I)
    PAGE_NUMBER_RE = re.compile(r"^(page\s+)?\d{1,4}(\s*(of|/)\s*\d{1,4})?$", re.I)

    @classmethod
    def is_structural(cls, text: str) -> bool:
        """Tem forma de título de seção: numerado ou nome conhecido (incluindo referências e seções descartadas)."""
        return bool(
            cls.STOP_SECTION_RE.match(text)
            or cls.KNOWN_HEADINGS_RE.match(text)
            or cls.SKIP_SECTION_RE.match(text)
            or cls.NUMBERED_HEADING_RE.match(text)
        )

    @classmethod
    def style_flags(cls, text: str, spans: list[dict], body_size: float, body_font: str) -> dict[str, bool]:
        """Sinais de 'cara de título' de uma linha: fonte maior, negrito, caixa alta, fonte própria."""
        visible = [s for s in spans if s["text"].strip()]
        if not visible:
            return {"bigger": False, "bold": False, "upper": False, "own_font": False}
        letters = [c for c in text if c.isalpha()]
        return {
            "bigger": all(s["size"] >= body_size * 1.12 for s in visible),
            "bold": all(cls.is_bold(s) for s in visible),
            "upper": len(letters) >= 4 and all(c.isupper() for c in letters),
            "own_font": (
                len({s["font"] for s in visible}) == 1
                and visible[0]["font"] != body_font
                and visible[0]["size"] >= body_size * 0.9
            ),
        }

    @classmethod
    def is_heading(
        cls,
        text: str,
        spans: list[dict],
        body_size: float,
        standalone: bool = False,
        body_font: str = "",
        front_matter: bool = False,
    ) -> bool:
        """
        Título = texto curto, sem pontuação final, COM cara de título E com forma de título.
          - cara de título: negrito, fonte maior, caixa alta, ou uma fonte própria
            (diferente da do texto corrido), como nos PDFs da Nature
          - forma de título: numerado, nome conhecido de seção, ou (sem número)
            uma linha sozinha, de 2 a MAX_HEADING_WORDS palavras, quase só letras
        Exigir as duas coisas evita pegar células de tabela como "Funding considerations".
        Sem número nem nome conhecido, caixa alta sozinha não basta (pega título de tabela
        e lista de autores): precisa de negrito, fonte maior ou fonte própria.
        Na 1a página, antes do primeiro título "de verdade" (front_matter), títulos sem
        número são ignorados: ali estão título do artigo, autores e afiliações.
        """
        if not text or len(text) > cls.MAX_HEADING_CHARS or text.endswith((".", ",", ";", ":", "-", "–")):
            return False
        if cls.STOP_SECTION_RE.match(text):
            return True  # "References" sozinho numa linha: confiável mesmo sem estilo
        if cls.NOT_HEADING_RE.search(text):
            return False  # legendas ("Table 2 | ..."), links, e-mails
        style = cls.style_flags(text, spans, body_size, body_font)
        if not any(style.values()):
            return False
        if cls.is_structural(text):
            return True
        if not standalone or front_matter:
            return False
        if not (style["bold"] or style["bigger"] or style["own_font"]):
            return False
        words = text.split()
        return (
            2 <= len(words) <= cls.MAX_HEADING_WORDS
            and text[0].isupper()
            and cls.alpha_ratio(text) >= cls.MIN_HEADING_ALPHA_RATIO
        )

    @classmethod
    def heading_continues(
        cls, line: dict, head_spans: list[dict], head_text: str, body_size: float, body_font: str
    ) -> bool:
        """A linha continua um título que quebrou em duas? Mesma fonte e tamanho do título, e também com cara de título."""
        spans = line["spans"]
        text = cls.clean("".join(s["text"] for s in spans))
        if not text or len(head_text) + 1 + len(text) > cls.MAX_HEADING_CHARS:
            return False
        if cls.NUMBERED_HEADING_RE.match(text) or cls.KNOWN_HEADINGS_RE.match(text):
            return False  # é outro título, não continuação
        visible = [s for s in spans if s["text"].strip()]
        head_visible = [s for s in head_spans if s["text"].strip()]
        if not visible or {s["font"] for s in visible} != {s["font"] for s in head_visible}:
            return False
        if {round(s["size"], 1) for s in visible} != {round(s["size"], 1) for s in head_visible}:
            return False
        return any(cls.style_flags(text, visible, body_size, body_font).values())

    @classmethod
    def read_heading(
        cls, lines: list[dict], i: int, text: str, body_size: float, body_font: str
    ) -> tuple[str, int] | None:
        """
        Confirma o título que começa na linha i e junta as linhas seguintes se ele quebrou em várias.
        Devolve (título, índice da última linha usada), ou None se for texto corrido disfarçado de título.
        """
        if cls.STOP_SECTION_RE.match(text) or cls.KNOWN_HEADINGS_RE.match(text) or cls.SKIP_SECTION_RE.match(text):
            return text, i  # nome de seção completo, não quebra em duas linhas
        head_spans = lines[i]["spans"]
        if i + 1 < len(lines):
            next_spans = lines[i + 1]["spans"]
            next_text = cls.clean("".join(s["text"] for s in next_spans))
            next_styled = any(cls.style_flags(next_text, next_spans, body_size, body_font).values())
            if next_text[:1].islower() and not next_styled:
                return None  # a "frase" segue em minúscula, sem estilo, na linha de baixo: é começo de parágrafo
        title, last = text, i
        while last + 1 < len(lines) and cls.heading_continues(lines[last + 1], head_spans, title, body_size, body_font):
            last += 1
            title = f"{title} {cls.clean(''.join(s['text'] for s in lines[last]['spans']))}"
        if title.endswith((".", "?", "!", ",", ";", ":")):
            return None  # trecho longo em negrito/caixa alta, não título
        return title, last

    @classmethod
    def split_run_in(cls, spans: list[dict]) -> tuple[str, str] | None:
        """
        Título "embutido": '3.2.1. Título' em negrito no começo da linha e o texto corrido logo depois,
        na mesma linha. Devolve (título, resto da linha) ou None.
        """
        k = 0
        while k < len(spans) and (cls.is_bold(spans[k]) or not spans[k]["text"].strip()):
            k += 1
        head, rest = spans[:k], spans[k:]
        if not any(s["text"].strip() for s in head) or not any(s["text"].strip() for s in rest):
            return None
        title = cls.clean("".join(s["text"] for s in head)).strip(" .:—–-")
        if not title or len(title) > cls.MAX_HEADING_CHARS:
            return None
        if not (cls.NUMBERED_HEADING_RE.match(title) or cls.KNOWN_HEADINGS_RE.match(title)):
            return None
        return title, "".join(s["text"] for s in rest)

    @classmethod
    def ordered_blocks(cls, page: pymupdf.Page) -> list[dict]:
        """
        Blocos de texto na ordem de leitura, tratando 2 colunas: blocos de largura
        total (título, figuras largas) cortam a página em faixas; dentro de cada
        faixa vem a coluna da esquerda inteira e depois a da direita.
        """
        mid = page.rect.width / 2
        blocks = [b for b in page.get_text("dict")["blocks"] if b.get("lines")]

        def column(b: dict) -> int:
            x0, x1 = b["bbox"][0], b["bbox"][2]
            if x1 <= mid + 15:
                return 0
            if x0 >= mid - 15:
                return 1
            return -1  # largura total

        full = sorted((b for b in blocks if column(b) == -1), key=lambda b: b["bbox"][1])
        cols = [b for b in blocks if column(b) != -1]
        ordered, top = [], -1.0
        for fb in full + [None]:
            bottom = fb["bbox"][1] if fb else float("inf")
            band = [b for b in cols if top <= b["bbox"][1] < bottom]
            ordered += sorted(band, key=lambda b: (column(b), b["bbox"][1]))
            if fb:
                ordered.append(fb)
                top = fb["bbox"][1]
        return ordered

    @classmethod
    def heading_level(cls, text: str) -> int:
        """'2.1 Participants' -> 2; '3 Results' ou 'Discussion' -> 1."""
        m = re.match(r"^\s*(\d+(?:\.\d+)*)\.?\s", text)
        return m.group(1).count(".") + 1 if m else 1

    @classmethod
    def extract_pdf(cls, path: Path) -> list[dict]:
        """
        Trabalha linha a linha: um título pode vir no mesmo bloco que o texto.
        Quebra parágrafo em título, troca de bloco, recuo de primeira linha ou
        linha anterior curta terminando em ponto.
        """
        paragraphs: list[dict] = []
        section, skipping = "", False
        levels: dict[int, str] = {}  # nível do título -> título, para montar "2 Methods > 2.1 Participants"
        last_level, last_unnumbered = 0, False  # título sem número: nível do anterior + 1 (ou irmão, se o anterior também era)
        seen_structural = False  # já apareceu um título numerado/conhecido?
        buffer: list[str] = []
        buffer_page = buffer_page_end = 0

        def flush() -> None:
            nonlocal buffer
            text = cls.clean("\n".join(buffer))
            buffer = []
            if skipping or not text:
                return
            last = paragraphs[-1] if paragraphs else None
            # parágrafo que continua na próxima coluna/página: a frase anterior não terminou
            if last and last["section"] == section and not last["text"].endswith((".", "?", "!", ":")) and text[0].islower():
                last["text"] = f"{last['text']} {text}"
                last["page_end"] = buffer_page_end
                return
            if len(text) < cls.MIN_PARAGRAPH_CHARS or cls.alpha_ratio(text) < cls.MIN_ALPHA_RATIO:
                return
            paragraphs.append({"section": section, "page": buffer_page, "page_end": buffer_page_end, "text": text})

        def start_section(title: str) -> bool:
            """Abre uma seção nova. Devolve True se for a bibliografia (fim do conteúdo útil)."""
            nonlocal section, skipping, levels, last_level, last_unnumbered, seen_structural
            known = bool(cls.KNOWN_HEADINGS_RE.match(title))
            numbered = bool(cls.NUMBERED_HEADING_RE.match(title))
            if known or numbered:
                seen_structural = True
            flush()
            if cls.STOP_SECTION_RE.match(title):
                return True
            skipping = bool(cls.SKIP_SECTION_RE.match(title))
            if numbered:
                level = cls.heading_level(title)
            elif known or not levels:
                level = 1
            else:
                level = last_level if last_unnumbered else last_level + 1
            last_level, last_unnumbered = level, not (numbered or known)
            levels = {k: v for k, v in levels.items() if k < level}
            levels[level] = title
            section = "" if skipping else " > ".join(levels[k] for k in sorted(levels))
            return False

        with pymupdf.open(path) as doc:
            body_size, body_font = cls.body_style(doc)
            running = cls.running_lines(doc)
            for page_number, page in enumerate(doc, start=1):
                height = page.rect.height
                for block in cls.ordered_blocks(page):
                    flush()  # troca de bloco = novo parágrafo
                    block_x0, block_x1 = block["bbox"][0], block["bbox"][2]
                    # bloco inteiro na faixa de topo/rodapé = cabeçalho/rodapé; um parágrafo que só
                    # termina ali (última linha da página) não entra aqui
                    block_in_margin = block["bbox"][3] < height * cls.MARGIN_RATIO or block["bbox"][1] > height * (1 - cls.MARGIN_RATIO)
                    prev = None
                    in_caption = False  # depois de "Table 2"/"Figure 3" o resto do bloco é legenda, não título
                    lines = block["lines"]
                    merged_until = -1  # linhas já consumidas por um título que quebrou em várias
                    for i, line in enumerate(lines):
                        if i <= merged_until:
                            continue
                        spans = line["spans"]
                        text = cls.clean("".join(s["text"] for s in spans))
                        if not text:
                            continue
                        y0, y1 = line["bbox"][1], line["bbox"][3]
                        line_in_margin = y1 < height * cls.MARGIN_RATIO or y0 > height * (1 - cls.MARGIN_RATIO)
                        if line_in_margin and ((block_in_margin and len(text) < 120) or cls.PAGE_NUMBER_RE.match(text)):
                            continue  # cabeçalho, rodapé, número de página
                        if re.sub(r"\d+", "#", text.lower()) in running:
                            continue  # cabeçalho/rodapé corrido fora da margem
                        if cls.CAPTION_RE.match(text):
                            in_caption = True

                        # título embutido na linha: '3.2.1. Título' em negrito + texto corrido
                        if not in_caption and (prev is None or prev["text"].endswith((".", "?", "!", ":"))):
                            run_in = cls.split_run_in(spans)
                            if run_in:
                                title, rest = run_in
                                if start_section(title):
                                    return paragraphs  # bibliografia: fim do conteúdo útil
                                buffer_page = buffer_page_end = page_number
                                buffer.append(rest)
                                prev = {"bbox": line["bbox"], "text": cls.clean(rest)}
                                continue

                        # "sozinho": bloco curto, ou 1a linha do bloco numa fonte diferente da linha seguinte
                        fonts = {s["font"] for s in spans if s["text"].strip()}
                        next_fonts = {s["font"] for s in lines[i + 1]["spans"] if s["text"].strip()} if i + 1 < len(lines) else set()
                        standalone = len(lines) <= 2 or (i == 0 and len(fonts) == 1 and not fonts & next_fonts)
                        front_matter = page_number == 1 and not seen_structural
                        if not in_caption and cls.is_heading(text, spans, body_size, standalone, body_font, front_matter):
                            heading = cls.read_heading(lines, i, text, body_size, body_font)
                            if heading:
                                title, merged_until = heading
                                if start_section(title):
                                    return paragraphs  # bibliografia: fim do conteúdo útil
                                prev = None
                                continue

                        if prev is not None:
                            size = spans[0]["size"]
                            indented = line["bbox"][0] > prev["bbox"][0] + size * 0.8
                            prev_short = prev["bbox"][2] < block_x1 - size * 2 and prev["text"].endswith((".", "?", "!", ":"))
                            if indented or prev_short:
                                flush()
                        if not buffer:
                            buffer_page = page_number
                        buffer_page_end = page_number
                        buffer.append("".join(s["text"] for s in spans))
                        prev = {"bbox": line["bbox"], "text": text}
            flush()
        return paragraphs

    # ---------- orquestração ----------

    @classmethod
    def output_path(cls, doc_path: Path, text_dir: Path = TEXT_DIR) -> Path:
        return text_dir / f"{doc_path.stem}.jsonl"

    @classmethod
    def quality_flags(cls, paragraphs: list[dict]) -> list[str]:
        flags = []
        n_chars = sum(len(p["text"]) for p in paragraphs)
        if not paragraphs:
            flags.append("sem texto (PDF escaneado? precisa de OCR)")
        elif len(paragraphs) < cls.MIN_DOC_PARAGRAPHS or n_chars < cls.MIN_DOC_CHARS:
            flags.append(f"pouco texto ({len(paragraphs)} parágrafos, {n_chars} caracteres)")
        if paragraphs and not any(p["section"] for p in paragraphs):
            flags.append("nenhuma seção identificada")
        return flags

    @classmethod
    def extract_doc(cls, doc_path: Path, text_dir: Path = TEXT_DIR, force: bool = False) -> dict:
        """Extrai um documento e grava o JSONL. Devolve {key, kind, n_paragraphs, n_chars, flags, skipped}."""
        out = cls.output_path(doc_path, text_dir)
        key = doc_path.stem
        if out.exists() and not force and out.stat().st_mtime >= doc_path.stat().st_mtime:
            n = sum(1 for _ in open(out, encoding="utf-8"))
            return {"key": key, "kind": doc_path.suffix[1:], "n_paragraphs": n, "n_chars": None, "flags": [], "skipped": True}

        ok, reason, kind = Validator.validate(str(doc_path))
        if not ok:
            return {"key": key, "kind": kind, "n_paragraphs": 0, "n_chars": 0, "flags": [f"arquivo inválido: {reason}"], "skipped": False}

        paragraphs = cls.extract_xml(doc_path) if kind == "xml" else cls.extract_pdf(doc_path)
        text_dir.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".part")
        with open(tmp, "w", encoding="utf-8") as f:
            for i, p in enumerate(paragraphs):
                record = {"id": cls.OPENALEX_PREFIX + key, "key": key, "kind": kind, "para": i, **p}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        tmp.replace(out)
        return {
            "key": key,
            "kind": kind,
            "n_paragraphs": len(paragraphs),
            "n_chars": sum(len(p["text"]) for p in paragraphs),
            "flags": cls.quality_flags(paragraphs),
            "skipped": False,
        }

    @classmethod
    def extract_all(cls, docs_dir: Path = DOCS_DIR, text_dir: Path = TEXT_DIR, force: bool = False) -> list[dict]:
        docs = sorted(p for p in docs_dir.glob("W*") if p.suffix in {".pdf", ".xml"})
        results = []
        for i, doc_path in enumerate(docs, start=1):
            try:
                r = cls.extract_doc(doc_path, text_dir, force)
            except Exception as e:  # um arquivo problemático não derruba o lote
                r = {"key": doc_path.stem, "kind": doc_path.suffix[1:], "n_paragraphs": 0, "n_chars": 0,
                     "flags": [f"erro na extração: {e}"], "skipped": False}
            results.append(r)
            status = "já extraído" if r["skipped"] else f"{r['n_paragraphs']} parágrafos"
            flag = f"  ⚠ {'; '.join(r['flags'])}" if r["flags"] else ""
            print(f"[{i}/{len(docs)}] {doc_path.name}  {status}{flag}")
        return results
