"""PDF text per page, and the check that keeps the LLM honest: a quote only counts if it
is really in the document."""

import io
import re

from pypdf import PdfReader

MIN_TEXT_CHARS = 200
MIN_QUOTE_CHARS = 12


class BadPDF(ValueError):
    pass


class NoTextLayer(BadPDF):
    pass


def read_pages(data: bytes) -> list[str]:
    """Text of each page (index 0 = page 1)."""
    try:
        pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages]
    except Exception as exc:  # untrusted input: any parser failure means "not a readable PDF"
        raise BadPDF(f"not a readable PDF: {exc}") from exc
    if sum(len(p.strip()) for p in pages) < MIN_TEXT_CHARS:
        raise NoTextLayer("no text layer")
    return pages


def normalize(s: str) -> str:
    s = s.lower().translate(str.maketrans("‘’“”–—", "''\"\"--"))
    s = re.sub(r"(?<=[a-z])-\s*(?=[a-z])", "", s)  # co-payment / co-\npayment -> copayment
    s = s.replace("₹", " rs ")
    s = re.sub(r"\b(?:rs\.?|inr)(?=[\s\d])", " rs ", s)
    s = re.sub(r"(?<=\d),(?=\d)", "", s)  # 5,000 -> 5000
    return " ".join(s.split())


def locate_quote(pages: list[str], quote: str, page_hint: int | None) -> int | None:
    """1-based page holding the quote, or None. Checks the hinted page first, then its
    neighbours, then everything; a quote may run over into the next page."""
    q = normalize(quote or "")
    if len(q) < MIN_QUOTE_CHARS:
        return None
    norm = [normalize(p) for p in pages]
    order = []
    if page_hint:
        order += [page_hint - 1, page_hint - 2, page_hint]
    order += range(len(norm))
    for i in dict.fromkeys(order):
        if not 0 <= i < len(norm):
            continue
        if q in norm[i]:
            return i + 1
        if i + 1 < len(norm) and q in f"{norm[i]} {norm[i + 1]}" and q not in norm[i + 1]:
            return i + 1
    return None
