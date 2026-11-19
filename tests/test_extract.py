from decimal import Decimal

import pytest
from fpdf import FPDF

from app.embed import FakeEmbedder
from app.extract import PROMPT_BUDGET, SCHEMA, TERM_QUERIES, _passages, extract_terms, read_policy
from app.llm import FallbackLLM, LLMError
from app.models import PolicyTerms
from app.pdf import read_pages

PAGES = [
    "Definitions. The Sum Insured under this policy is Rs. 5,00,000 for the policy year. " * 3,
    "Room rent is payable up to 1% of the Sum Insured per day for a normal room. " * 3,
    "A co-payment of 10% shall apply to every admissible claim under this policy. " * 3,
]


class ScriptedLLM:
    def __init__(self, reply=None, error=False):
        self.reply, self.error, self.calls, self.schemas = reply or {}, error, 0, []

    def json(self, prompt: str, schema: dict | None = None) -> dict:
        self.calls += 1
        self.schemas.append(schema)
        if self.error:
            raise LLMError("quota")
        return self.reply


def found(page, quote, **value):
    return {"found": True, "page": page, "quote": quote, **value}


RETRIEVED = {field: [(1, PAGES[0]), (2, PAGES[1]), (3, PAGES[2])] for field in TERM_QUERIES}


def test_every_policy_field_has_a_query_and_schema():
    assert set(TERM_QUERIES) == set(PolicyTerms.model_fields) == set(SCHEMA["properties"])


def test_schema_is_sent_to_the_llm():
    llm = ScriptedLLM({})
    extract_terms(PAGES, RETRIEVED, llm)
    assert llm.schemas == [SCHEMA]


def test_verified_quote_keeps_value():
    llm = ScriptedLLM({"room_limit": found(2, "room rent is payable up to 1% of the sum insured",
                                           kind="pct_si", amount=1)})
    terms = extract_terms(PAGES, RETRIEVED, llm)
    assert terms.room_limit.verified
    assert terms.room_limit.value.amount == Decimal(1)
    assert terms.room_limit.page == 2


def test_not_found_is_none():
    llm = ScriptedLLM({"copay_pct": {"found": False, "page": 0, "quote": "", "amount": 0}})
    assert extract_terms(PAGES, RETRIEVED, llm).copay_pct.value is None


def test_invented_quote_drops_value():
    llm = ScriptedLLM({"copay_pct": found(3, "no co-payment applies to any claim", amount=0)})
    terms = extract_terms(PAGES, RETRIEVED, llm)
    assert terms.copay_pct.value is None
    assert not terms.copay_pct.verified


def test_wrong_page_corrected():
    llm = ScriptedLLM({"copay_pct": found(1, "A co-payment of 10% shall apply", amount=10)})
    assert extract_terms(PAGES, RETRIEVED, llm).copay_pct.page == 3


def test_bad_field_shape_marks_only_that_term():
    llm = ScriptedLLM({
        "room_limit": found(2, "Room rent is payable up to", kind="daily", amount=1),
        "copay_pct": found(3, "A co-payment of 10% shall apply", amount=10),
    })
    terms = extract_terms(PAGES, RETRIEVED, llm)
    assert terms.room_limit.value is None
    assert terms.copay_pct.value == Decimal(10)


def test_category_outside_enum_rejected():
    llm = ScriptedLLM({"non_payable": found(1, "The Sum Insured under this policy",
                                            categories=["gloves"])})
    assert extract_terms(PAGES, RETRIEVED, llm).non_payable.value is None


def test_sublimits_become_a_mapping():
    pages = PAGES + ["Cataract surgery is payable up to Rs. 40,000 per eye. " * 3]
    retrieved = {f: [(4, pages[3])] for f in TERM_QUERIES}
    llm = ScriptedLLM({"sublimits": found(4, "Cataract surgery is payable up to Rs. 40,000",
                                          items=[{"procedure": "Cataract", "amount": 40000}])})
    assert extract_terms(pages, retrieved, llm).sublimits.value == {"Cataract": Decimal(40000)}


def test_non_dict_reply_entries_ignored():
    llm = ScriptedLLM({"room_limit": "1%", "copay_pct": None, "unknown": {"found": True}})
    terms = extract_terms(PAGES, RETRIEVED, llm)
    assert terms.room_limit.value is None and terms.copay_pct.value is None


def test_single_llm_call_for_all_terms():
    llm = ScriptedLLM({})
    extract_terms(PAGES, RETRIEVED, llm)
    assert llm.calls == 1


def test_passages_capped_but_every_term_keeps_its_best_hit():
    big = {f: [(i, f"{f} passage {i} " + "x" * 1950) for i in range(1, 6)] for f in TERM_QUERIES}
    text = _passages(big)
    assert len(text) <= PROMPT_BUDGET + 200
    for f in TERM_QUERIES:
        assert f"{f} passage 1 " in text


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
    llm = ScriptedLLM({"copay_pct": found(3, "A co-payment of 10% shall apply", amount=10)})
    pid, terms = read_policy(pool, "p.pdf", read_pages(_pdf(PAGES)), FakeEmbedder(), llm)
    assert terms.copay_pct.verified
    with pool.connection() as conn:
        saved = conn.execute("SELECT terms FROM policies WHERE id=%s", (pid,)).fetchone()[0]
        assert saved["copay_pct"]["value"] == "10"
        assert conn.execute("SELECT count(*) FROM chunks WHERE policy_id=%s",
                            (pid,)).fetchone()[0] > 0


def test_read_policy_llm_failure_leaves_nothing_behind(pool):
    with pytest.raises(LLMError):
        read_policy(pool, "p.pdf", read_pages(_pdf(PAGES)), FakeEmbedder(), ScriptedLLM(error=True))
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) FROM policies").fetchone()[0] == 0


QUOTE = "The Sum Insured under this policy"


def test_proportionate_except_list_becomes_the_reduced_categories():
    llm = ScriptedLLM({"proportionate_categories": found(
        1, QUOTE, reduced=[], not_reduced=["medicines", "consumables", "implants", "diagnostics"])})
    value = extract_terms(PAGES, RETRIEVED, llm).proportionate_categories.value
    assert sorted(value) == ["ot", "other", "surgeon"]


def test_proportionate_named_list_kept_minus_exclusions():
    llm = ScriptedLLM({"proportionate_categories": found(
        1, QUOTE, reduced=["surgeon", "ot", "medicines"], not_reduced=["medicines"])})
    value = extract_terms(PAGES, RETRIEVED, llm).proportionate_categories.value
    assert sorted(value) == ["ot", "surgeon"]


def test_value_must_appear_in_quote():
    llm = ScriptedLLM({"copay_pct": found(3, "A co-payment of 10% shall apply", amount=20)})
    assert extract_terms(PAGES, RETRIEVED, llm).copay_pct.value is None


def test_limit_kind_must_match_quote():
    llm = ScriptedLLM({"room_limit": found(2, "Room rent is payable up to 1% of the Sum Insured",
                                           kind="per_day", amount=1)})
    assert extract_terms(PAGES, RETRIEVED, llm).room_limit.value is None


def test_generic_quote_cannot_verify_a_number():
    llm = ScriptedLLM({"copay_pct": found(2, "Room rent is payable up to", amount=10)})
    assert extract_terms(PAGES, RETRIEVED, llm).copay_pct.value is None


def test_indian_digit_grouping_matches():
    llm = ScriptedLLM({"sum_insured": found(1, "The Sum Insured under this policy is Rs. 5,00,000",
                                            amount=500000)})
    assert extract_terms(PAGES, RETRIEVED, llm).sum_insured.value == Decimal(500000)


def test_explicit_none_quote_verifies_zero():
    pages = PAGES + ["No deductible applies under this policy at all. " * 3]
    retrieved = {f: [(4, pages[3])] for f in TERM_QUERIES}
    llm = ScriptedLLM({"deductible": found(4, "No deductible applies under this policy", amount=0)})
    assert extract_terms(pages, retrieved, llm).deductible.value == Decimal(0)


def test_extracted_copay_over_100_rejected():
    pages = PAGES + ["A co-payment of 150% applies to each claim. " * 3]
    retrieved = {f: [(4, pages[3])] for f in TERM_QUERIES}
    llm = ScriptedLLM({"copay_pct": found(4, "A co-payment of 150% applies", amount=150)})
    assert extract_terms(pages, retrieved, llm).copay_pct.value is None
