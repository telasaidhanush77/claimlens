"""Reads the sample policy once with the live LLM and saves the result, so DEMO_MODE needs
no API calls. Run: python -m scripts.cache_sample"""

from pathlib import Path

from app.config import Settings
from app.db import make_pool, migrate
from app.deps import build_embedder, build_llm
from app.extract import read_policy

SAMPLE = Path(__file__).resolve().parent.parent / "app" / "sample"


def main() -> None:
    s = Settings()
    pool = make_pool(s.database_url)
    migrate(pool)
    pid, terms = read_policy(pool, "sample", (SAMPLE / "policy.pdf").read_bytes(),
                             build_embedder(s), build_llm(s))
    with pool.connection() as conn:
        conn.execute("DELETE FROM policies WHERE id = %s", (pid,))
    (SAMPLE / "terms.json").write_text(terms.model_dump_json(indent=2), encoding="utf-8")
    for name, term in terms:
        print(f"{name:26} verified={term.verified!s:5} p.{term.page} {term.value}")


if __name__ == "__main__":
    main()
