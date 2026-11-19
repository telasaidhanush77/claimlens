import pytest
from fpdf import FPDF

from app.pdf import BadPDF, NoTextLayer, locate_quote, normalize, read_pages

FILLER = "This section describes general conditions of the policy in plain words. " * 4


def make_pdf(pages: list[str]) -> bytes:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=11)
    for text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 6, text)
    return bytes(pdf.output())


PAGES = [
    "Definitions. " + FILLER,
    "Room rent is payable up to 1% of the Sum Insured per day. " + FILLER,
    "A co-payment of 10% applies to every admissible claim. " + FILLER,
]


def test_read_pages_returns_one_string_per_page():
    pages = read_pages(make_pdf(PAGES))
    assert len(pages) == 3
    assert "Room rent" in pages[1]


def test_exact_quote_found():
    assert locate_quote(PAGES, "Room rent is payable up to 1% of the Sum Insured", 2) == 2


def test_whitespace_and_case_differences_verify():
    assert locate_quote(PAGES, "room  RENT is\npayable up to 1% of the sum insured", 2) == 2


def test_quote_on_wrong_page_returns_true_page():
    assert locate_quote(PAGES, "A co-payment of 10% applies", 1) == 3


def test_quote_across_page_break():
    pages = ["Room rent is payable up to", "1% of the Sum Insured per day. " + FILLER]
    assert locate_quote(pages, "payable up to 1% of the Sum Insured", 1) == 1


def test_hyphenated_line_break_joins():
    pages = ["The proportion-\nate deduction applies to associated expenses."]
    assert locate_quote(pages, "proportionate deduction applies", None) == 1


def test_rupee_formats_match():
    assert normalize("limit of Rs. 5,000 per day") == normalize("limit of ₹5000 per day")
    assert normalize("INR 5,000") == normalize("₹ 5000")


def test_invented_quote_returns_none():
    assert locate_quote(PAGES, "Room rent is payable without any limit", 2) is None


def test_short_quote_rejected():
    assert locate_quote(PAGES, "Room rent", 2) is None


def test_scanned_pdf_raises_no_text_layer():
    pdf = FPDF()
    pdf.add_page()
    with pytest.raises(NoTextLayer):
        read_pages(bytes(pdf.output()))


def test_garbage_bytes_raise_bad_pdf():
    with pytest.raises(BadPDF):
        read_pages(b"not a pdf at all")


def test_hyphen_at_line_end_matches_hyphenated_quote():
    pages = ["A co-\npayment of 10% applies to every admissible claim."]
    assert locate_quote(pages, "A co-payment of 10% applies", None) == 1


def test_parser_crash_becomes_bad_pdf(monkeypatch):
    import app.pdf as pdf_mod

    class Boom:
        def __init__(self, *a, **k):
            raise RecursionError("deep")
    monkeypatch.setattr(pdf_mod, "PdfReader", Boom)
    with pytest.raises(BadPDF):
        read_pages(b"%PDF-1.4")
