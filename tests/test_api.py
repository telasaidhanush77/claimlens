import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF

from app.config import Settings
from app.embed import FakeEmbedder
from app.llm import LLMError
from app.main import app, get_embedder, get_llm, get_pool, get_settings

SAMPLE = Path(__file__).resolve().parent.parent / "app" / "sample"


class ScriptedLLM:
    def __init__(self, reply=None, error=False):
        self.reply, self.error, self.calls = reply or {}, error, 0

    def json(self, prompt, schema=None):
        self.calls += 1
        if self.error:
            raise LLMError("quota")
        return self.reply


@pytest.fixture
def make_client(pool):
    def make(llm=None, live=True):
        llm = llm or ScriptedLLM()
        app.dependency_overrides.update({
            get_pool: lambda: pool,
            get_embedder: lambda: FakeEmbedder(),
            get_llm: lambda: llm,
            get_settings: lambda: Settings(gemini_api_key="x" if live else ""),
        })
        return TestClient(app), llm
    yield make
    app.dependency_overrides.clear()


def text_pdf() -> bytes:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=11)
    pdf.add_page()
    pdf.multi_cell(0, 6, "A co-payment of 10% shall apply to every admissible claim. " * 8)
    return bytes(pdf.output())


def blank_pdf() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    return bytes(pdf.output())


def sample_estimate() -> dict:
    return json.loads((SAMPLE / "estimate.json").read_text())


def test_healthz(make_client):
    client, _ = make_client()
    assert client.get("/healthz").json() == {"ok": True}


def test_sample_then_simulate_roundtrip(make_client):
    client, llm = make_client()
    policy = client.post("/api/policies/sample").json()
    assert policy["terms"]["room_limit"]["verified"] is True
    sim = client.post("/api/simulate", json={"policy_id": policy["id"],
                                             "estimate": sample_estimate()})
    assert sim.status_code == 200
    assert sim.json()["insurer_pays"] == 187988
    assert llm.calls == 0


def test_upload_reads_policy(make_client):
    llm = ScriptedLLM({"copay_pct": {"found": True, "amount": 10, "page": 1,
                                     "quote": "A co-payment of 10% shall apply"}})
    client, _ = make_client(llm)
    r = client.post("/api/policies", files={"file": ("p.pdf", text_pdf(), "application/pdf")})
    assert r.status_code == 200
    assert r.json()["terms"]["copay_pct"]["value"] == "10"


def test_upload_scanned_pdf_422_and_no_llm_call(make_client):
    client, llm = make_client()
    r = client.post("/api/policies", files={"file": ("p.pdf", blank_pdf(), "application/pdf")})
    assert r.status_code == 422
    assert "no text layer" in r.json()["detail"]
    assert llm.calls == 0


def test_upload_not_a_pdf_422(make_client):
    client, _ = make_client()
    r = client.post("/api/policies", files={"file": ("p.pdf", b"hello", "application/pdf")})
    assert r.status_code == 422


def test_upload_llm_down_502(make_client):
    client, _ = make_client(ScriptedLLM(error=True))
    r = client.post("/api/policies", files={"file": ("p.pdf", text_pdf(), "application/pdf")})
    assert r.status_code == 502
    assert "try again" in r.json()["detail"]


def test_upload_without_keys_503(make_client):
    client, _ = make_client(live=False)
    r = client.post("/api/policies", files={"file": ("p.pdf", text_pdf(), "application/pdf")})
    assert r.status_code == 503


def test_upload_too_large_413(make_client):
    client, _ = make_client()
    big = b"%PDF-1.4\n" + b"0" * (15 * 1024 * 1024 + 1)
    r = client.post("/api/policies", files={"file": ("p.pdf", big, "application/pdf")})
    assert r.status_code == 413


def test_put_terms_then_simulate_uses_them(make_client):
    client, _ = make_client()
    policy = client.post("/api/policies/sample").json()
    terms = policy["terms"]
    terms["copay_pct"] = {"value": "0", "page": None, "quote": None, "verified": False}
    assert client.put(f"/api/policies/{policy['id']}/terms", json=terms).status_code == 200
    again = client.get(f"/api/policies/{policy['id']}").json()
    assert again["terms"]["copay_pct"]["value"] == "0"
    sim = client.post("/api/simulate", json={"policy_id": policy["id"],
                                             "estimate": sample_estimate()}).json()
    assert sim["insurer_pays"] == 208875


def test_put_terms_cannot_forge_verified(make_client):
    client, _ = make_client()
    policy = client.post("/api/policies/sample").json()
    terms = policy["terms"]
    terms["copay_pct"] = {"value": "0", "page": 4, "quote": "made up", "verified": True}
    client.put(f"/api/policies/{policy['id']}/terms", json=terms)
    saved = client.get(f"/api/policies/{policy['id']}").json()["terms"]["copay_pct"]
    assert saved["verified"] is False and saved["quote"] is None
    assert client.get(f"/api/policies/{policy['id']}").json()["terms"]["room_limit"]["verified"]


def test_unknown_policy_404(make_client):
    client, _ = make_client()
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/policies/{missing}").status_code == 404
    r = client.post("/api/simulate", json={"policy_id": missing, "estimate": sample_estimate()})
    assert r.status_code == 404


def test_negative_amount_422(make_client):
    client, _ = make_client()
    policy = client.post("/api/policies/sample").json()
    est = sample_estimate()
    est["items"][1]["amount"] = -5
    r = client.post("/api/simulate", json={"policy_id": policy["id"], "estimate": est})
    assert r.status_code == 422


def test_sample_estimate_endpoint(make_client):
    client, _ = make_client()
    assert client.get("/api/sample-estimate").json()["procedure"] == "Knee replacement"


class DownEmbedder:
    def embed(self, texts, task):
        from app.llm import LLMError
        raise LLMError("embedding quota")


def test_upload_embedding_quota_502(make_client):
    client, _ = make_client()
    app.dependency_overrides[get_embedder] = lambda: DownEmbedder()
    r = client.post("/api/policies", files={"file": ("p.pdf", text_pdf(), "application/pdf")})
    assert r.status_code == 502
