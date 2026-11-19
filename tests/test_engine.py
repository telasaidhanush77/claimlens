from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.engine import simulate
from app.models import Estimate, Limit, LineItem, PolicyTerms, RoomOption, Term


def t(value, page=1):
    return Term(value=value, page=page, quote="clause text", verified=True)


def policy(**over) -> PolicyTerms:
    values = dict(
        sum_insured=Decimal(500000),
        room_limit=Limit(kind="pct_si", amount=Decimal(1)),
        icu_limit=Limit(kind="pct_si", amount=Decimal(2)),
        proportionate=True,
        proportionate_categories=["surgeon", "ot", "diagnostics", "other"],
        copay_pct=Decimal(10),
        deductible=Decimal(0),
        sublimits={"knee replacement": Decimal(150000)},
        non_payable=["consumables"],
    )
    values.update(over)
    return PolicyTerms(**{k: t(v) for k, v in values.items()})


def item(desc, cat, amount, days=None):
    return LineItem(description=desc, category=cat, amount=Decimal(amount), days=days)


ABOVE_LIMIT = [
    item("Deluxe room", "room", 32000, 4),
    item("Surgeon", "surgeon", 80000),
    item("Diagnostics", "diagnostics", 20000),
    item("Medicines", "medicines", 30000),
]


def test_room_within_limit_pays_all():
    est = Estimate(items=[item("Room", "room", 16000, 4), item("Surgeon", "surgeon", 50000)])
    assert simulate(policy(copay_pct=Decimal(0)), est).insurer_pays == 66000


def test_room_above_limit_cuts_associated_charges():
    sim = simulate(policy(copay_pct=Decimal(0)), Estimate(items=ABOVE_LIMIT))
    payable = {line.category: line.payable for line in sim.lines}
    assert payable == {"room": 20000, "surgeon": 50000, "diagnostics": 12500,
                       "medicines": 30000}
    assert sim.insurer_pays == 112500
    for line in sim.lines:
        if line.payable < line.billed:
            assert line.notes, line.description


def test_pct_and_per_day_limits_agree():
    est = Estimate(items=ABOVE_LIMIT)
    pct = simulate(policy(copay_pct=Decimal(0)), est)
    per_day = simulate(policy(copay_pct=Decimal(0),
                              room_limit=Limit(kind="per_day", amount=Decimal(5000))), est)
    assert pct.insurer_pays == per_day.insurer_pays == 112500


def test_no_room_limit_no_deduction():
    est = Estimate(items=ABOVE_LIMIT[:2])
    sim = simulate(policy(copay_pct=Decimal(0), room_limit=None), est)
    assert sim.insurer_pays == 112000


def test_non_payable_category_is_zero():
    est = Estimate(items=[item("Surgeon", "surgeon", 50000), item("Gloves", "consumables", 9000)])
    sim = simulate(policy(copay_pct=Decimal(0)), est)
    gloves = next(line for line in sim.lines if line.category == "consumables")
    assert gloves.payable == 0
    assert any("Not payable" in n for n in gloves.notes)
    assert sim.insurer_pays == 50000


def test_sublimit_caps_total():
    est = Estimate(procedure="Knee Replacement",
                   items=[item("Room", "room", 16000, 4), item("Surgeon", "surgeon", 200000)])
    assert simulate(policy(copay_pct=Decimal(0)), est).insurer_pays == 150000


def test_copay_applied_after_deductible():
    est = Estimate(items=[item("Surgeon", "surgeon", 110000)])
    sim = simulate(policy(deductible=Decimal(10000)), est)
    assert sim.insurer_pays == 90000


def test_capped_at_sum_insured():
    est = Estimate(items=[item("Surgeon", "surgeon", 300000)])
    sim = simulate(policy(copay_pct=Decimal(0), sum_insured=Decimal(100000)), est)
    assert sim.insurer_pays == 100000


def test_you_pay_is_billed_minus_insurer():
    sim = simulate(policy(), Estimate(items=ABOVE_LIMIT))
    assert sim.billed == 162000
    assert sim.you_pay == sim.billed - sim.insurer_pays


def test_room_item_requires_days():
    with pytest.raises(ValidationError):
        item("Room", "room", 16000, None)


def test_negative_amount_rejected():
    with pytest.raises(ValidationError):
        item("Surgeon", "surgeon", -5)


def test_cheaper_room_lowers_you_pay():
    options = [RoomOption(name=n, rate_per_day=Decimal(r))
               for n, r in [("General ward", 2500), ("Twin sharing", 4500), ("Deluxe", 8000)]]
    est = Estimate(items=ABOVE_LIMIT, room_options=options)
    sim = simulate(policy(), est)
    by_name = {c.name: c for c in sim.room_choices}
    assert by_name["Twin sharing"].you_pay < by_name["Deluxe"].you_pay
    assert by_name["Deluxe"].insurer_pays == sim.insurer_pays
    assert [c.you_pay for c in sim.room_choices] == sorted(c.you_pay for c in sim.room_choices)
