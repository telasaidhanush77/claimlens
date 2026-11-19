import json
import uuid

from app.embed import FakeEmbedder
from app.retrieve import CHUNK, chunk, search, store

PAGES = [
    "Definitions of hospital, insured person and policy period. " * 20,
    "Room rent limit: room rent is payable up to 1% of the sum insured per day. " * 10,
    "Exclusions: cosmetic surgery, dental treatment and spectacles are excluded. " * 15,
]


def _policy(pool) -> uuid.UUID:
    with pool.connection() as conn:
        return conn.execute(
            "INSERT INTO policies (name, pages, terms) VALUES ('p', %s, '{}') RETURNING id",
            (json.dumps(PAGES),)).fetchone()[0]


def test_chunks_stay_within_page():
    chunks = chunk(PAGES)
    assert {p for p, _, _ in chunks} == {1, 2, 3}
    for page, _, text in chunks:
        assert text in PAGES[page - 1]
        assert len(text) <= CHUNK
    assert [o for _, o, _ in chunks] == list(range(len(chunks)))


def test_search_returns_room_rent_chunk_first(pool):
    pid = _policy(pool)
    store(pool, pid, PAGES, FakeEmbedder())
    hits = search(pool, pid, "room rent limit per day", FakeEmbedder(), k=2)
    assert hits[0][0] == 2
    assert "Room rent" in hits[0][1]


def test_delete_policy_cascades_chunks(pool):
    pid = _policy(pool)
    store(pool, pid, PAGES, FakeEmbedder())
    with pool.connection() as conn:
        conn.execute("DELETE FROM policies WHERE id = %s", (pid,))
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
