"""JSON-mode LLM clients (Gemini first, Groq as fallback) on free tiers."""

import json
import re
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
    def json(self, prompt: str, schema: dict | None = None) -> dict: ...


def _retry_after(r: httpx.Response) -> float | None:
    """Seconds the server asked us to wait: Retry-After header, or Gemini's RetryInfo body."""
    after = r.headers.get("Retry-After", "")
    if after.isdigit():
        return float(after)
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', r.text)
    return float(m.group(1)) if m else None


def post_json(client: httpx.Client, url: str, body: dict, headers: dict,
              sleep: Callable[[float], None], tries: int = TRIES,
              max_wait: float = MAX_WAIT_S) -> dict:
    """Retry 429/5xx and network errors (honouring the server's wait, capped); other 4xx fail
    fast. Every failure surfaces as LLMError."""
    for attempt in range(1, tries + 1):
        try:
            r = client.post(url, json=body, headers=headers)
        except httpx.TransportError as exc:
            if attempt == tries:
                raise LLMError(f"network: {exc}") from exc
            sleep(2 ** attempt)
            continue
        if r.status_code < 400:
            return r.json()
        if r.status_code not in RETRYABLE or attempt == tries:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        sleep(min(_retry_after(r) or 2 ** attempt, max_wait))
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

    def json(self, prompt: str, schema: dict | None = None) -> dict:
        config: dict = {"responseMimeType": "application/json", "temperature": 0}
        if schema:
            config["responseJsonSchema"] = schema
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}
        data = post_json(self.client, self.URL.format(model=self.model), body,
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

    def json(self, prompt: str, schema: dict | None = None) -> dict:
        fmt = ({"type": "json_schema", "json_schema": {"name": "reply", "schema": schema}}
               if schema else {"type": "json_object"})
        body = {"model": self.model, "temperature": 0, "response_format": fmt,
                "messages": [{"role": "user", "content": prompt}]}
        data = post_json(self.client, self.URL, body,
                     {"Authorization": f"Bearer {self.api_key}"}, self.sleep)
        try:
            return _parse(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected Groq reply: {str(data)[:200]}") from exc


class FallbackLLM:
    def __init__(self, primary: LLM, secondary: LLM | None):
        self.primary, self.secondary = primary, secondary

    def json(self, prompt: str, schema: dict | None = None) -> dict:
        try:
            return self.primary.json(prompt, schema)
        except LLMError:
            if self.secondary is None:
                raise
            return self.secondary.json(prompt, schema)
