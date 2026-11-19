import pytest

from app.config import Settings
from app.db import make_pool, migrate


@pytest.fixture(scope="session")
def _pool():
    pool = make_pool(Settings().test_database_url)
    migrate(pool)
    yield pool
    pool.close()


@pytest.fixture
def pool(_pool):
    with _pool.connection() as conn:
        conn.execute("TRUNCATE policies CASCADE")
    return _pool
