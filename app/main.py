"""HTTP API. Routes are thin: reading lives in app.extract, arithmetic in app.engine."""

import json
import logging
from functools import cache
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from app.config import Settings
from app.db import make_pool, migrate
from app.deps import build_embedder, build_llm, live_reading_enabled
from app.embed import Embedder
from app.engine import simulate
from app.extract import read_policy
from app.llm import LLM, LLMError
from app.models import Estimate, PolicyTerms, Simulation, Term
from app.pdf import BadPDF, NoTextLayer, read_pages

log = logging.getLogger("claimlens")
ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "sample"
WEB = ROOT.parent / "web" / "out"
MAX_UPLOAD = 15 * 1024 * 1024
MAX_PAGES = 150

MSG_SCANNED = ("This PDF has no text layer (scanned). Upload the text version of your "
               "policy wording.")
MSG_BAD_PDF = "That file isn't a readable PDF."
MSG_LLM_DOWN = "Couldn't read the policy right now, try again in a minute."
MSG_NO_KEYS = "Live policy reading is off on this server; try the sample policy."
MSG_TOO_BIG = "That PDF is over 15 MB."
MSG_TOO_LONG = (f"That PDF is over {MAX_PAGES} pages. Upload the policy wording only, not a "
                "bundle of documents.")


@cache
def get_settings() -> Settings:
    return Settings()


@cache
def _pool(url: str) -> ConnectionPool:
    pool = make_pool(url)
    migrate(pool)
    return pool


def get_pool(settings: Settings = Depends(get_settings)) -> ConnectionPool:
    return _pool(settings.database_url)


def get_embedder(settings: Settings = Depends(get_settings)) -> Embedder:
    return build_embedder(settings)


def get_llm(settings: Settings = Depends(get_settings)) -> LLM:
    return build_llm(settings)


class PolicyOut(BaseModel):
    id: UUID
    name: str
    terms: PolicyTerms


class SimulateIn(BaseModel):
    policy_id: UUID
    estimate: Estimate


app = FastAPI(title="ClaimLens")


@app.middleware("http")
async def reject_oversized_upload(request: Request, call_next):
    """Refuse a too-large upload from its Content-Length, before the body is spooled."""
    size = request.headers.get("content-length", "")
    too_big = size.isdigit() and int(size) > MAX_UPLOAD + 64 * 1024  # + multipart overhead
    if request.url.path == "/api/policies" and too_big:
        return JSONResponse({"detail": MSG_TOO_BIG}, status_code=413)
    return await call_next(request)


def _load(pool: ConnectionPool, policy_id: UUID) -> PolicyOut:
    with pool.connection() as conn:
        row = conn.execute("SELECT id, name, terms FROM policies WHERE id = %s",
                           (policy_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Policy not found.")
    return PolicyOut(id=row[0], name=row[1], terms=PolicyTerms.model_validate(row[2]))


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/api/policies", response_model=PolicyOut)
def upload_policy(file: UploadFile, pool: ConnectionPool = Depends(get_pool),
                  settings: Settings = Depends(get_settings),
                  embedder: Embedder = Depends(get_embedder),
                  llm: LLM = Depends(get_llm)) -> PolicyOut:
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, MSG_TOO_BIG)
    try:
        pages = read_pages(data)  # fail fast on scans / junk before keys or any API call
    except NoTextLayer as exc:
        raise HTTPException(422, MSG_SCANNED) from exc
    except BadPDF as exc:
        raise HTTPException(422, MSG_BAD_PDF) from exc
    if len(pages) > MAX_PAGES:
        raise HTTPException(422, MSG_TOO_LONG)
    if not live_reading_enabled(settings):
        raise HTTPException(503, MSG_NO_KEYS)
    name = (file.filename or "policy.pdf")[:200]
    try:
        pid, terms = read_policy(pool, name, pages, embedder, llm)
    except LLMError as exc:
        log.warning("policy read failed: %s", exc)
        raise HTTPException(502, MSG_LLM_DOWN) from exc
    return PolicyOut(id=pid, name=name, terms=terms)


@app.post("/api/policies/sample", response_model=PolicyOut)
def sample_policy(pool: ConnectionPool = Depends(get_pool)) -> PolicyOut:
    terms = PolicyTerms.model_validate_json((SAMPLE / "terms.json").read_text(encoding="utf-8"))
    pages = read_pages((SAMPLE / "policy.pdf").read_bytes())
    name = "Sample policy (fictional)"
    with pool.connection() as conn:
        pid = conn.execute("INSERT INTO policies (name, pages, terms) VALUES (%s, %s, %s) "
                           "RETURNING id", (name, json.dumps(pages),
                                            terms.model_dump_json())).fetchone()[0]
    return PolicyOut(id=pid, name=name, terms=terms)


@app.get("/api/policies/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: UUID, pool: ConnectionPool = Depends(get_pool)) -> PolicyOut:
    return _load(pool, policy_id)


@app.put("/api/policies/{policy_id}/terms", response_model=PolicyOut)
def put_terms(policy_id: UUID, body: PolicyTerms,
              pool: ConnectionPool = Depends(get_pool)) -> PolicyOut:
    """Save the user's values. A term only stays verified if its value is unchanged; anything
    the user typed is stored as 'entered by you' (no page, no quote, not verified)."""
    saved = _load(pool, policy_id)
    merged = {}
    for name, new in body:
        old: Term = getattr(saved.terms, name)
        merged[name] = old if (old.verified and new.value == old.value) else \
            Term(value=new.value)
    terms = PolicyTerms(**merged)
    with pool.connection() as conn:
        conn.execute("UPDATE policies SET terms = %s WHERE id = %s",
                     (terms.model_dump_json(), policy_id))
    return PolicyOut(id=saved.id, name=saved.name, terms=terms)


@app.post("/api/simulate", response_model=Simulation)
def simulate_claim(body: SimulateIn, pool: ConnectionPool = Depends(get_pool)) -> Simulation:
    return simulate(_load(pool, body.policy_id).terms, body.estimate)


@app.get("/api/sample-estimate", response_model=Estimate)
def sample_estimate() -> Estimate:
    return Estimate.model_validate_json((SAMPLE / "estimate.json").read_text(encoding="utf-8"))


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
