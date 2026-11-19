"""Chunk the policy, store embeddings in pgvector, and find the passages for a question."""

from uuid import UUID

from psycopg_pool import ConnectionPool

from app.embed import Embedder

CHUNK = 2000
OVERLAP = 250


def chunk(pages: list[str]) -> list[tuple[int, int, str]]:
    """(page, ord, text) chunks that never cross a page boundary."""
    out: list[tuple[int, int, str]] = []
    for page_no, text in enumerate(pages, start=1):
        start = 0
        while start < len(text):
            piece = text[start:start + CHUNK]
            if piece.strip():
                out.append((page_no, len(out), piece))
            if start + CHUNK >= len(text):
                break
            start += CHUNK - OVERLAP
    return out


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def store(pool: ConnectionPool, policy_id: UUID, pages: list[str], embedder: Embedder) -> None:
    chunks = chunk(pages)
    vectors = embedder.embed([t for _, _, t in chunks], "doc")
    with pool.connection() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO chunks (policy_id, page, ord, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s::vector)",
            [(policy_id, p, o, t, _vec(v)) for (p, o, t), v in zip(chunks, vectors,
                                                                    strict=True)])


def search(pool: ConnectionPool, policy_id: UUID, query: str, embedder: Embedder,
           k: int = 4) -> list[tuple[int, str]]:
    return search_many(pool, policy_id, [query], embedder, k)[0]


def search_many(pool: ConnectionPool, policy_id: UUID, queries: list[str],
                embedder: Embedder, k: int = 4) -> list[list[tuple[int, str]]]:
    """Top-k (page, text) per query, with one embedding call for all queries."""
    out = []
    with pool.connection() as conn:
        for v in embedder.embed(queries, "query"):
            rows = conn.execute(
                "SELECT page, text FROM chunks WHERE policy_id = %s "
                "ORDER BY embedding <=> %s::vector LIMIT %s",
                (policy_id, _vec(v), k)).fetchall()
            out.append([(page, text) for page, text in rows])
    return out
