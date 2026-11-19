"""Settings from the environment, with a local .env file as a fallback."""

import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _dotenv() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    pairs = (line.split("=", 1) for line in ENV_FILE.read_text().splitlines()
             if "=" in line and not line.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name) or _dotenv().get(name) or default


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _get(
        "DATABASE_URL", "postgresql://claimlens:claimlens@localhost:5434/claimlens"))
    test_database_url: str = field(default_factory=lambda: _get(
        "TEST_DATABASE_URL", "postgresql://claimlens:claimlens@localhost:5434/claimlens_test"))
    gemini_api_key: str = field(default_factory=lambda: _get("GEMINI_API_KEY"))
    groq_api_key: str = field(default_factory=lambda: _get("GROQ_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _get("GEMINI_MODEL",
                                                           "gemini-3.5-flash-lite"))
    groq_model: str = field(default_factory=lambda: _get("GROQ_MODEL", "openai/gpt-oss-120b"))
    embed_model: str = field(default_factory=lambda: _get("EMBED_MODEL",
                                                          "gemini-embedding-001"))
