"""Builds the real embedder and LLM from settings (the API overrides these in tests)."""

from app.config import Settings
from app.embed import Embedder, GeminiEmbedder
from app.llm import LLM, FallbackLLM, GeminiLLM, GroqLLM


def live_reading_enabled(s: Settings) -> bool:
    return bool(s.gemini_api_key)


def build_embedder(s: Settings) -> Embedder:
    return GeminiEmbedder(s.gemini_api_key, s.embed_model)


def build_llm(s: Settings) -> LLM:
    groq = GroqLLM(s.groq_api_key, s.groq_model) if s.groq_api_key else None
    return FallbackLLM(GeminiLLM(s.gemini_api_key, s.gemini_model), groq)
