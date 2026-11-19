"""Policy PDF -> typed terms. The LLM finds and quotes; we keep only what we can find in
the PDF. One LLM call per policy, over the passages retrieved for each term, with the reply
shape enforced by a JSON schema."""

import json
from decimal import Decimal
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

# Charges a proportionate deduction can touch when the policy says "all expenses except ...".
# Room/ICU are capped separately.
ASSOCIATED = ["surgeon", "ot", "diagnostics", "other"]

# ~6k tokens of passages: fits Groq's free 8k tokens/minute with room for the reply.
PROMPT_BUDGET = 24000

_NUM = {"type": "number"}
_CATS = {"type": "array", "items": {"type": "string", "enum": list(CATEGORIES)}}
_LIMIT = {"kind": {"type": "string", "enum": ["per_day", "pct_si"]}, "amount": _NUM}
_VALUE_FIELDS: dict[str, dict] = {
    "sum_insured": {"amount": _NUM},
    "room_limit": _LIMIT,
    "icu_limit": _LIMIT,
    "proportionate": {"applies": {"type": "boolean"}},
    "proportionate_categories": {"reduced": _CATS, "not_reduced": _CATS},
    "copay_pct": {"amount": _NUM},
    "deductible": {"amount": _NUM},
    "sublimits": {"items": {"type": "array", "items": {
        "type": "object", "properties": {"procedure": {"type": "string"}, "amount": _NUM},
        "required": ["procedure", "amount"]}}},
    "non_payable": {"categories": _CATS},
}


def _term_schema(fields: dict) -> dict:
    props = {"found": {"type": "boolean"}, "page": {"type": "integer"},
             "quote": {"type": "string"}, **fields}
    return {"type": "object", "properties": props, "required": list(props)}


SCHEMA = {"type": "object",
          "properties": {k: _term_schema(v) for k, v in _VALUE_FIELDS.items()},
          "required": list(_VALUE_FIELDS)}

PROMPT = """You read Indian health-insurance policy wordings.
For each term below, find the sentence in the passages that states it.
- found: true only if a passage states it. Otherwise found=false and the other fields are
  placeholders (0, "", false, []).
- quote: that sentence copied word for word from the passage. Never paraphrase.
- page: the page number shown above that passage.
- If the policy explicitly says a term does not apply (e.g. "no deductible applies"),
  found=true with amount 0 (or applies=false) and that sentence as the quote.
- A conditional rule (e.g. co-pay only for some zones or ages) is not a flat rule: found=false.

Terms:
- sum_insured: the sum insured in rupees (amount).
- room_limit: daily room rent limit for a normal room. kind "per_day" with amount in rupees,
  or kind "pct_si" with amount = percent of the sum insured per day.
- icu_limit: same, for ICU.
- proportionate: applies=true if other charges are reduced in proportion when the room
  costs more than the limit.
- proportionate_categories: from the proportionate-deduction clause, "reduced" = the
  categories it names as reduced, "not_reduced" = categories it says are excepted / not
  reduced. Many policies say "all expenses except X and Y": then reduced=[] and
  not_reduced=[X, Y].
- copay_pct: co-payment percent on every claim (amount).
- deductible: deductible in rupees (amount).
- sublimits: caps for named procedures (items of procedure + rupee amount).
- non_payable: categories the policy never pays for. Only list a category if everything in
  it is excluded (e.g. consumables); a few excluded admin charges do not make "other"
  non-payable.

Categories: room, icu, surgeon (surgeon/consultant fees), ot (operation theatre),
diagnostics, medicines, consumables, implants, other (other hospital charges).

Passages:
{passages}
"""

_ADAPTERS = {name: TypeAdapter(field.annotation.model_fields["value"].annotation)
             for name, field in PolicyTerms.model_fields.items()}


def _passages(retrieved: dict[str, list[tuple[int, str]]]) -> str:
    """Round-robin over terms (each term's best hit first), de-duplicated, under budget."""
    picked: dict[tuple[int, str], None] = {}
    size = 0
    depth = max((len(h) for h in retrieved.values()), default=0)
    for rank in range(depth):
        for hits in retrieved.values():
            if rank >= len(hits) or hits[rank] in picked:
                continue
            if size + len(hits[rank][1]) > PROMPT_BUDGET and picked:
                continue
            picked[hits[rank]] = None
            size += len(hits[rank][1])
    return "\n\n".join(f"[page {p}]\n{t}" for p, t in sorted(picked, key=lambda h: h[0]))


def _value(name: str, obj: dict) -> Any:
    if name in ("room_limit", "icu_limit"):
        return {"kind": obj.get("kind"), "amount": obj.get("amount")}
    if name == "proportionate":
        return obj.get("applies")
    if name == "proportionate_categories":
        reduced, excepted = obj.get("reduced") or [], set(obj.get("not_reduced") or [])
        return [c for c in (reduced or ASSOCIATED) if c not in excepted]
    if name == "non_payable":
        return obj.get("categories")
    if name == "sublimits":
        return {str(i["procedure"]): i["amount"] for i in obj.get("items") or []}
    return obj.get("amount")


def _term(name: str, obj: Any, pages: list[str]) -> Term:
    if not isinstance(obj, dict) or not obj.get("found"):
        return Term()
    try:
        value = _ADAPTERS[name].validate_python(_value(name, obj))
        hint = int(obj["page"]) if obj.get("page") else None
    except (ValidationError, TypeError, ValueError, KeyError):
        return Term()
    if value is None:
        return Term()
    if isinstance(value, Decimal) and value < 0:
        return Term()
    quote = str(obj.get("quote") or "")
    page = locate_quote(pages, quote, hint)
    if page is None:
        return Term()
    return Term(value=value, page=page, quote=quote, verified=True)


def extract_terms(pages: list[str], retrieved: dict[str, list[tuple[int, str]]],
                  llm: LLM) -> PolicyTerms:
    reply = llm.json(PROMPT.format(passages=_passages(retrieved)), SCHEMA)
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
