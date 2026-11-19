"""Connection pool and migrations (plain SQL files, applied in name order, idempotent)."""

from pathlib import Path

from psycopg_pool import ConnectionPool

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def make_pool(url: str) -> ConnectionPool:
    return ConnectionPool(url, min_size=1, max_size=5, open=True,
                          kwargs={"autocommit": True})


def migrate(pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        for path in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(path.read_text())
