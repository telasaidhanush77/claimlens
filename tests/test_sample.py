import json
from pathlib import Path

from app.engine import simulate
from app.models import Estimate, PolicyTerms
from app.pdf import locate_quote, read_pages

SAMPLE = Path(__file__).resolve().parent.parent / "app" / "sample"


def test_sample_terms_all_verified_and_simulate():
    terms = PolicyTerms.model_validate_json((SAMPLE / "terms.json").read_text(encoding="utf-8"))
    pages = read_pages((SAMPLE / "policy.pdf").read_bytes())
    for name, term in terms:
        assert term.verified, name
        assert locate_quote(pages, term.quote, term.page) == term.page, name

    est = Estimate.model_validate(json.loads((SAMPLE / "estimate.json").read_text()))
    sim = simulate(terms, est)
    # Billed 2,76,000. Room limit 1% of 5,00,000 = 5,000/day; room 8,000/day -> pays 20,000.
    # Ratio 5,000/8,000 = 0.625 on surgeon 70,000 -> 43,750, OT 35,000 -> 21,875,
    # diagnostics 18,000 -> 11,250. Implant 90,000 and medicines 22,000 are not cut.
    # Consumables 9,000 not payable. Subtotal 2,08,875 (under the 3,00,000 sub-limit).
    # Co-pay 10% -> 1,87,987.5 -> 1,87,988.
    assert (sim.billed, sim.insurer_pays, sim.you_pay) == (276000, 187988, 88012)
    you_pay = {c.name: c.you_pay for c in sim.room_choices}
    assert you_pay == {"General ward": 33500, "Twin sharing": 34300,
                       "Single private room": 66046, "Deluxe room": 88012}
    assert sim.room_choices[0].name == "General ward"
