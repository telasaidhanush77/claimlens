"""JSON-mode LLM clients (Gemini first, Groq as fallback) on free tiers."""

import json
import time
from collections.abc import Callable
from typing import Protocol

import httpx

RETRYABLE = {429, 500, 502, 503, 504}
MAX_WAIT_S = 30
TRIES = 3


class LLMError(Exception):
    pass


class LLM(Protocol):
    def json(self, prompt: str) -> dict: ...


def _post(client: httpx.Client, url: str, body: dict, headers: dict,
          sleep: Callable[[float], None]) -> dict:
    """Retry 429/5xx and network errors (honouring Retry-After, capped); other 4xx fail fast."""
    for attempt in range(1, TRIES + 1):
        try:
            r = client.post(url, json=body, headers=headers)
        except httpx.TransportError as exc:
            if attempt == TRIES:
                raise LLMError(f"network: {exc}") from exc
            sleep(2 ** attempt)
            continue
        if r.status_code < 400:
            return r.json()
        if r.status_code not in RETRYABLE or attempt == TRIES:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        after = r.headers.get("Retry-After", "")
        sleep(min(int(after), MAX_WAIT_S) if after.isdigit() else 2 ** attempt)
    raise LLMError("unreachable")


def _parse(text: str) -> dict:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMError(f"reply is not JSON: {str(text)[:100]}") from exc
    if not isinstance(data, dict):
        raise LLMError("reply is not a JSON object")
    return data


class GeminiLLM:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.api_key, self.model, self.sleep = api_key, model, sleep
        self.client = client or httpx.Client(timeout=90)

    def json(self, prompt: str) -> dict:
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
        data = _post(self.client, self.URL.format(model=self.model), body,
                     {"x-goog-api-key": self.api_key}, self.sleep)
        try:
            return _parse(data["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected Gemini reply: {str(data)[:200]}") from exc


class GroqLLM:
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.api_key, self.model, self.sleep = api_key, model, sleep
        self.client = client or httpx.Client(timeout=90)

    def json(self, prompt: str) -> dict:
        body = {"model": self.model, "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}]}
        data = _post(self.client, self.URL, body,
                     {"Authorization": f"Bearer {self.api_key}"}, self.sleep)
        try:
            return _parse(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected Groq reply: {str(data)[:200]}") from exc


class FallbackLLM:
    def __init__(self, primary: LLM, secondary: LLM | None):
        self.primary, self.secondary = primary, secondary

    def json(self, prompt: str) -> dict:
        try:
            return self.primary.json(prompt)
        except LLMError:
            if self.secondary is None:
                raise
            return self.secondary.json(prompt)
