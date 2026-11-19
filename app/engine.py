"""The claim engine: pure arithmetic over typed policy terms. No I/O, no LLM.

Order (each stage writes a Step): non-payables -> room/ICU caps -> proportionate
deduction -> procedure sub-limit -> deductible -> co-pay -> sum-insured cap."""

from decimal import ROUND_HALF_UP, Decimal

from app.models import (
    ASSOCIATED,
    Estimate,
    Limit,
    LineItem,
    LineResult,
    PolicyTerms,
    RoomChoice,
    Simulation,
    Step,
    Term,
)

ZERO = Decimal(0)


def limit_per_day(limit: Limit | None, sum_insured: Decimal | None) -> Decimal | None:
    if limit is None:
        return None
    if limit.kind == "per_day":
        return limit.amount
    if sum_insured is None:  # "1% of SI" with no SI known: can't apply it
        return None
    return sum_insured * limit.amount / 100


def _rupees(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _fmt(x: Decimal) -> str:
    return f"₹{_rupees(x):,}"


def _p(term: Term) -> str:
    return f" (p.{term.page})" if term.page else ""


def _room_rate(lines: list[LineItem]) -> Decimal | None:
    rates = [li.amount / li.days for li in lines if li.category == "room" and li.days]
    return max(rates) if rates else None


def simulate(terms: PolicyTerms, est: Estimate) -> Simulation:
    si = terms.sum_insured.value
    room_cap = limit_per_day(terms.room_limit.value, si)
    icu_cap = limit_per_day(terms.icu_limit.value, si)
    non_payable = set(terms.non_payable.value or [])
    results = [LineResult(description=li.description, category=li.category,
                          billed=li.amount, payable=li.amount) for li in est.items]
    total = lambda: sum((r.payable for r in results), ZERO)  # noqa: E731
    steps = [Step(label="Billed by the hospital", total_after=total())]

    # 1. Items the policy never pays for.
    for r in results:
        if r.category in non_payable:
            r.payable = ZERO
            r.notes.append(f"Not payable under this policy{_p(terms.non_payable)}")
    if any(r.category in non_payable for r in results):
        steps.append(Step(label="Remove non-payable items", total_after=total(),
                          page=terms.non_payable.page))

    # 2. Room and ICU rent above the daily limit.
    capped_page = None
    for li, r in zip(est.items, results, strict=True):
        if li.category == "room":
            cap, term = room_cap, terms.room_limit
        elif li.category == "icu":
            cap, term = icu_cap, terms.icu_limit
        else:
            continue
        if cap is None or r.payable == ZERO:
            continue
        rate = li.amount / li.days
        if rate > cap:
            r.payable = cap * li.days
            capped_page = capped_page or term.page
            r.notes.append(f"Paid up to {_fmt(cap)}/day, your room is {_fmt(rate)}/day"
                           f"{_p(term)}")
    if capped_page or any(r.payable < r.billed and r.category in ("room", "icu")
                          and r.category not in non_payable for r in results):
        steps.append(Step(label="Cap room / ICU rent at the daily limit", total_after=total(),
                          page=capped_page))

    # 3. Proportionate deduction: a pricier room shrinks the linked charges too.
    rate = _room_rate(est.items)
    if terms.proportionate.value and room_cap and rate and rate > room_cap:
        ratio = room_cap / rate
        named = terms.proportionate_categories.value
        cut = set(named if named is not None else ASSOCIATED) - {"room", "icu"}
        why = "" if named is not None else ", standard associated charges assumed"
        changed = False
        for r in results:
            if r.category in cut and r.payable > ZERO:
                r.payable = r.payable * ratio
                changed = True
                r.notes.append(f"Cut to {ratio * 100:.1f}% because the room is above your "
                               f"limit{_p(terms.proportionate)}{why}")
        if changed:
            steps.append(Step(label=f"Proportionate deduction ({ratio * 100:.1f}%)",
                              total_after=total(), page=terms.proportionate.page))

    claim = total()

    # 4. Procedure sub-limit.
    sublimits = {k.strip().lower(): v for k, v in (terms.sublimits.value or {}).items()}
    proc = (est.procedure or "").strip().lower()
    if proc in sublimits and claim > sublimits[proc]:
        claim = sublimits[proc]
        steps.append(Step(label=f"Sub-limit for {est.procedure}: {_fmt(claim)}",
                          total_after=claim, page=terms.sublimits.page))

    # 5-7. Deductible, co-pay, sum insured.
    if terms.deductible.value:
        claim = max(ZERO, claim - terms.deductible.value)
        steps.append(Step(label=f"Deductible {_fmt(terms.deductible.value)}",
                          total_after=claim, page=terms.deductible.page))
    if terms.copay_pct.value:
        claim = claim * (100 - terms.copay_pct.value) / 100
        steps.append(Step(label=f"Co-pay {terms.copay_pct.value}%", total_after=claim,
                          page=terms.copay_pct.page))
    if si is not None and claim > si:
        claim = si
        steps.append(Step(label="Capped at sum insured", total_after=claim,
                          page=terms.sum_insured.page))

    billed = _rupees(sum((li.amount for li in est.items), ZERO))
    insurer = _rupees(claim)
    sim = Simulation(lines=results, steps=steps, billed=billed, insurer_pays=insurer,
                     you_pay=billed - insurer)
    if est.room_options:
        sim.room_choices = compare_rooms(terms, est)
    return sim


def compare_rooms(terms: PolicyTerms, est: Estimate) -> list[RoomChoice]:
    """Re-run the claim once per room option, swapping the room rate on every room line."""
    choices = []
    for opt in est.room_options:
        items = [li.model_copy(update={"amount": opt.rate_per_day * li.days})
                 if li.category == "room" else li for li in est.items]
        sim = simulate(terms, Estimate(procedure=est.procedure, items=items))
        choices.append(RoomChoice(name=opt.name, rate_per_day=opt.rate_per_day,
                                  insurer_pays=sim.insurer_pays, you_pay=sim.you_pay))
    return sorted(choices, key=lambda c: c.you_pay)
