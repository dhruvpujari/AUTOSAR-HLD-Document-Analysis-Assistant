"""PDF parsing, cleaning and section-aware chunking."""
import re
import collections
from dataclasses import dataclass, asdict

try:
    import fitz                      # PyMuPDF
except ImportError:                  # fall back to pdfplumber for text
    fitz = None
try:
    import pdfplumber
except ImportError:
    pdfplumber = None
try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None

from .config import CFG

# "3.1 Swc_DoorLockCtrl" or "4 Interfaces"
HEADING = re.compile(r"^(\d+(?:\.\d+){0,3})\s+([A-Z].{2,90})$")
PAGE_NO = re.compile(r"^(page\s*)?\d+(\s*(of|/)\s*\d+)?$", re.I)


@dataclass
class Chunk:
    text: str
    page: int
    page_end: int
    section: str
    ctype: str          # "text" or "table"

    def dict(self):
        return asdict(self)


# ---------------------------------------------------------------- reading
def _ocr_page(path, page_no):
    """OCR one page, used only when a page has no text layer."""
    if fitz is None or pytesseract is None:
        return ""
    doc = fitz.open(path)
    pix = doc[page_no - 1].get_pixmap(dpi=200)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img)


def read_pdf(path):
    """Returns [{"page": 1, "text": "...", "tables": ["row | row", ...], "ocr": False}]"""
    pages = []
    if fitz is not None:
        doc = fitz.open(path)
        for i, pg in enumerate(doc, start=1):
            pages.append({"page": i, "text": pg.get_text("text"), "tables": [], "ocr": False})
    elif pdfplumber is not None:
        with pdfplumber.open(path) as pdf:
            for i, pg in enumerate(pdf.pages, start=1):
                pages.append({"page": i, "text": pg.extract_text() or "", "tables": [], "ocr": False})
    else:
        raise RuntimeError("Install PyMuPDF or pdfplumber")

    for p in pages:                                   # OCR for scanned pages
        if len(p["text"].strip()) < 30:
            t = _ocr_page(path, p["page"])
            if t.strip():
                p["text"], p["ocr"] = t, True

    if pdfplumber is not None:                        # tables
        with pdfplumber.open(path) as pdf:
            for p, pg in zip(pages, pdf.pages):
                for tb in pg.extract_tables():
                    rows = [" | ".join((c or "").replace("\n", " ").strip() for c in r) for r in tb if r]
                    if len(rows) > 1:
                        p["tables"].append("\n".join(rows))
    return pages


# --------------------------------------------------------------- cleaning
def clean_pages(pages):
    """Drop repeated headers/footers and page numbers, fix hyphenation."""
    counter = collections.Counter()
    for p in pages:
        lines = [l.strip() for l in p["text"].splitlines() if l.strip()]
        for l in set(lines[:2] + lines[-2:]):
            counter[re.sub(r"\d+", "#", l)] += 1
    repeated = {l for l, n in counter.items() if len(pages) >= 4 and n >= 0.5 * len(pages)}

    for p in pages:
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", p["text"])
        keep = []
        for l in text.splitlines():
            s = l.strip()
            if not s or PAGE_NO.match(s) or re.sub(r"\d+", "#", s) in repeated:
                continue
            keep.append(re.sub(r"\s+", " ", s))
        p["text"] = "\n".join(keep)
    return pages


# --------------------------------------------------------------- chunking
def _split_sections(pages):
    sections, cur = [], None
    for p in pages:
        for ln in p["text"].splitlines():
            if HEADING.match(ln):
                cur = {"title": ln, "lines": []}
                sections.append(cur)
            elif cur is None:
                cur = {"title": "Front matter", "lines": []}
                sections.append(cur)
            cur["lines"].append((p["page"], ln))
    return sections


def chunk_document(pages):
    max_w = int(CFG["chunking"]["max_tokens"] * 0.75)
    ov_w = int(CFG["chunking"]["overlap_tokens"] * 0.75)
    chunks = []

    # text chunks, one section at a time
    heading_pages = []                                 # (page, title) for table lookup
    for sec in _split_sections(pages):
        words = []
        for page, ln in sec["lines"]:
            words += [(w, page) for w in ln.split()]
        if sec["lines"]:
            heading_pages.append((sec["lines"][0][0], sec["title"]))
        start = 0
        while start < len(words):
            win = words[start:start + max_w]
            if len(win) >= 8 or not chunks:
                chunks.append(Chunk(" ".join(w for w, _ in win), win[0][1], win[-1][1], sec["title"], "text"))
            if start + max_w >= len(words):
                break
            start += max_w - ov_w

    # table chunks, kept separate so rows are not flattened into prose
    for p in pages:
        title = "Front matter"
        for pg, t in heading_pages:
            if pg <= p["page"]:
                title = t
        for tb in p["tables"]:
            rows = tb.split("\n")
            header, body, buf = rows[0], rows[1:], []
            for r in body:
                buf.append(r)
                if sum(len(x.split()) for x in buf) > max_w:
                    chunks.append(Chunk(f"TABLE ({title}, p.{p['page']})\n{header}\n" + "\n".join(buf),
                                        p["page"], p["page"], title, "table"))
                    buf = []
            if buf:
                chunks.append(Chunk(f"TABLE ({title}, p.{p['page']})\n{header}\n" + "\n".join(buf),
                                    p["page"], p["page"], title, "table"))
    return chunks


def eda_summary(pages, chunks):
    """Numbers for the EDA section of the report."""
    lens = [len(c.text.split()) for c in chunks]
    return {
        "pages": len(pages),
        "ocr_pages": sum(p["ocr"] for p in pages),
        "tables": sum(len(p["tables"]) for p in pages),
        "chunks": len(chunks),
        "table_chunks": sum(c.ctype == "table" for c in chunks),
        "words_per_chunk_min": min(lens) if lens else 0,
        "words_per_chunk_avg": round(sum(lens) / len(lens), 1) if lens else 0,
        "words_per_chunk_max": max(lens) if lens else 0,
        "duplicate_chunks": len(chunks) - len({c.text for c in chunks}),
    }
