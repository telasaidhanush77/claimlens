from decimal import Decimal

import pytest
from fpdf import FPDF

from app.embed import FakeEmbedder
from app.extract import TERM_QUERIES, extract_terms, read_policy
from app.llm import FallbackLLM, LLMError
from app.models import PolicyTerms

PAGES = [
    "Definitions. The Sum Insured under this policy is Rs. 5,00,000 for the policy year. " * 3,
    "Room rent is payable up to 1% of the Sum Insured per day for a normal room. " * 3,
    "A co-payment of 10% shall apply to every admissible claim under this policy. " * 3,
]


class ScriptedLLM:
    def __init__(self, reply=None, error=False):
        self.reply, self.error, self.calls = reply or {}, error, 0

    def json(self, prompt: str) -> dict:
        self.calls += 1
        if self.error:
            raise LLMError("quota")
        return self.reply


RETRIEVED = {field: [(1, PAGES[0]), (2, PAGES[1]), (3, PAGES[2])] for field in TERM_QUERIES}


def test_every_policy_field_has_a_query():
    assert set(TERM_QUERIES) == set(PolicyTerms.model_fields)


def test_verified_quote_keeps_value():
    llm = ScriptedLLM({"room_limit": {"value": {"kind": "pct_si", "amount": 1}, "page": 2,
                                      "quote": "room rent is payable up to 1% of the sum insured"}})
    terms = extract_terms(PAGES, RETRIEVED, llm)
    assert terms.room_limit.verified
    assert terms.room_limit.value.amount == Decimal(1)
    assert terms.room_limit.page == 2


def test_invented_quote_drops_value():
    llm = ScriptedLLM({"copay_pct": {"value": 0, "page": 3,
                                     "quote": "no co-payment applies to any claim"}})
    terms = extract_terms(PAGES, RETRIEVED, llm)
    assert terms.copay_pct.value is None
    assert not terms.copay_pct.verified


def test_wrong_page_corrected():
    llm = ScriptedLLM({"copay_pct": {"value": 10, "page": 1,
                                     "quote": "A co-payment of 10% shall apply"}})
    assert extract_terms(PAGES, RETRIEVED, llm).copay_pct.page == 3


def test_bad_field_shape_marks_only_that_term():
    llm = ScriptedLLM({
        "room_limit": {"value": "one percent", "page": 2, "quote": "Room rent is payable up to"},
        "copay_pct": {"value": 10, "page": 3, "quote": "A co-payment of 10% shall apply"},
    })
    terms = extract_terms(PAGES, RETRIEVED, llm)
    assert terms.room_limit.value is None
    assert terms.copay_pct.value == Decimal(10)


def test_category_outside_enum_rejected():
    llm = ScriptedLLM({"non_payable": {"value": ["gloves"], "page": 1,
                                       "quote": "The Sum Insured under this policy"}})
    assert extract_terms(PAGES, RETRIEVED, llm).non_payable.value is None


def test_non_dict_reply_entries_ignored():
    llm = ScriptedLLM({"room_limit": "1%", "copay_pct": None, "unknown": {"value": 1}})
    terms = extract_terms(PAGES, RETRIEVED, llm)
    assert terms.room_limit.value is None and terms.copay_pct.value is None


def test_single_llm_call_for_all_terms():
    llm = ScriptedLLM({})
    extract_terms(PAGES, RETRIEVED, llm)
    assert llm.calls == 1


def test_fallback_used_when_primary_fails():
    primary, secondary = ScriptedLLM(error=True), ScriptedLLM({"ok": 1})
    assert FallbackLLM(primary, secondary).json("x") == {"ok": 1}
    assert primary.calls == secondary.calls == 1


def test_both_providers_fail_raises_llm_error():
    with pytest.raises(LLMError):
        FallbackLLM(ScriptedLLM(error=True), ScriptedLLM(error=True)).json("x")


def _pdf(pages):
    pdf = FPDF()
    pdf.set_font("Helvetica", size=11)
    for text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 6, text)
    return bytes(pdf.output())


def test_read_policy_saves_verified_terms(pool):
    llm = ScriptedLLM({"copay_pct": {"value": 10, "page": 3,
                                     "quote": "A co-payment of 10% shall apply"}})
    pid, terms = read_policy(pool, "p.pdf", _pdf(PAGES), FakeEmbedder(), llm)
    assert terms.copay_pct.verified
    with pool.connection() as conn:
        saved = conn.execute("SELECT terms FROM policies WHERE id=%s", (pid,)).fetchone()[0]
        assert saved["copay_pct"]["value"] == "10"
        assert conn.execute("SELECT count(*) FROM chunks WHERE policy_id=%s",
                            (pid,)).fetchone()[0] > 0


def test_read_policy_llm_failure_leaves_nothing_behind(pool):
    with pytest.raises(LLMError):
        read_policy(pool, "p.pdf", _pdf(PAGES), FakeEmbedder(), ScriptedLLM(error=True))
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) FROM policies").fetchone()[0] == 0


def test_flattened_object_value_accepted():
    llm = ScriptedLLM({"room_limit": {"kind": "pct_si", "amount": 1, "page": 2,
                                      "quote": "Room rent is payable up to 1% of the Sum Insured"}})
    terms = extract_terms(PAGES, RETRIEVED, llm)
    assert terms.room_limit.verified and terms.room_limit.value.amount == Decimal(1)


def test_bare_value_without_quote_dropped():
    llm = ScriptedLLM({"sublimits": {"Cataract surgery": 40000}})
    assert extract_terms(PAGES, RETRIEVED, llm).sublimits.value is None
