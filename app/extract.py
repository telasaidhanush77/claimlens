"""Policy PDF -> typed terms. The LLM finds and quotes; we keep only what we can find in
the PDF. One LLM call per policy, over the passages retrieved for each term."""

import json
from typing import Any
from uuid import UUID

from psycopg_pool import ConnectionPool
from pydantic import TypeAdapter, ValidationError

from app.embed import Embedder
from app.llm import LLM
from app.models import CATEGORIES, PolicyTerms, Term
from app.pdf import locate_quote, read_pages
from app.retrieve import search_many, store

TERM_QUERIES = {
    "sum_insured": "sum insured amount for the policy year",
    "room_limit": "room rent limit per day for a normal room category",
    "icu_limit": "ICU intensive care unit charges limit per day",
    "proportionate": "proportionate deduction associated medical expenses room above limit",
    "proportionate_categories": "associated medical expenses reduced in the same proportion",
    "copay_pct": "co-payment percentage of admissible claim",
    "deductible": "deductible amount borne by the insured before the claim",
    "sublimits": "sub-limit for specific diseases or procedures cataract knee replacement",
    "non_payable": "non-payable items consumables excluded expenses annexure",
}

SHAPES = {
    "sum_insured": "number, rupees",
    "room_limit": '{"kind": "per_day" | "pct_si", "amount": number} for a normal room '
                  '(pct_si = percent of the sum insured per day)',
    "icu_limit": 'same shape as room_limit, for ICU',
    "proportionate": "true if other charges are reduced in proportion when the room costs "
                     "more than the limit, false if the policy says they are not",
    "proportionate_categories": "list of categories that proportionate deduction applies to",
    "copay_pct": "number, percent",
    "deductible": "number, rupees",
    "sublimits": '{"<procedure name>": number rupees, ...}',
    "non_payable": "list of categories the policy never pays for",
}

PROMPT = """You read Indian health-insurance policy wordings.
From the passages below, extract each term. Answer with JSON only, one key per term:
  "<term>": {{"value": <value>, "page": <page number>, "quote": "<the exact sentence from
  the passage that states it, copied word for word>"}}
or "<term>": null when the passages do not state it. Never guess a value: if you can't quote
it, answer null.

Terms and value shapes:
{shapes}

Categories (use only these words): {categories}
(room, icu, surgeon = surgeon/consultant fees, ot = operation theatre, diagnostics,
medicines, consumables, implants, other = other hospital charges)

Passages:
{passages}
"""

_ADAPTERS = {name: TypeAdapter(field.annotation.model_fields["value"].annotation)
             for name, field in PolicyTerms.model_fields.items()}


def _prompt(retrieved: dict[str, list[tuple[int, str]]]) -> str:
    seen: dict[tuple[int, str], None] = {}
    for hits in retrieved.values():
        seen.update(dict.fromkeys(hits))
    passages = "\n\n".join(f"[page {p}]\n{t}" for p, t in sorted(seen, key=lambda h: h[0]))
    shapes = "\n".join(f"- {k}: {v}" for k, v in SHAPES.items())
    return PROMPT.format(shapes=shapes, categories=", ".join(CATEGORIES), passages=passages)


def _term(name: str, raw: Any, pages: list[str]) -> Term:
    if not isinstance(raw, dict) or raw.get("value") is None:
        return Term()
    try:
        value = _ADAPTERS[name].validate_python(raw["value"])
        hint = int(raw["page"]) if raw.get("page") is not None else None
    except (ValidationError, TypeError, ValueError):
        return Term()
    quote = str(raw.get("quote") or "")
    page = locate_quote(pages, quote, hint)
    if page is None:
        return Term()
    return Term(value=value, page=page, quote=quote, verified=True)


def extract_terms(pages: list[str], retrieved: dict[str, list[tuple[int, str]]],
                  llm: LLM) -> PolicyTerms:
    reply = llm.json(_prompt(retrieved))
    return PolicyTerms(**{name: _term(name, reply.get(name), pages) for name in TERM_QUERIES})


def read_policy(pool: ConnectionPool, name: str, data: bytes, embedder: Embedder,
                llm: LLM) -> tuple[UUID, PolicyTerms]:
    pages = read_pages(data)  # raises BadPDF / NoTextLayer before any API call
    with pool.connection() as conn:
        pid = conn.execute("INSERT INTO policies (name, pages, terms) VALUES (%s, %s, '{}') "
                           "RETURNING id", (name, json.dumps(pages))).fetchone()[0]
    try:
        store(pool, pid, pages, embedder)
        hits = search_many(pool, pid, list(TERM_QUERIES.values()), embedder)
        terms = extract_terms(pages, dict(zip(TERM_QUERIES, hits, strict=True)), llm)
    except Exception:
        with pool.connection() as conn:
            conn.execute("DELETE FROM policies WHERE id = %s", (pid,))
        raise
    with pool.connection() as conn:
        conn.execute("UPDATE policies SET terms = %s WHERE id = %s",
                     (terms.model_dump_json(), pid))
    return pid, terms
