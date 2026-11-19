"""Text embeddings: Gemini in production, a deterministic hash embedder in tests."""

import hashlib
import math
import re
from typing import Literal, Protocol

import httpx

DIM = 768
BATCH = 100
Task = Literal["doc", "query"]


class Embedder(Protocol):
    def embed(self, texts: list[str], task: Task) -> list[list[float]]: ...


class GeminiEmbedder:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None):
        self.api_key, self.model = api_key, model
        self.client = client or httpx.Client(timeout=60)

    def embed(self, texts: list[str], task: Task) -> list[list[float]]:
        task_type = "RETRIEVAL_DOCUMENT" if task == "doc" else "RETRIEVAL_QUERY"
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            body = {"requests": [{"model": f"models/{self.model}",
                                  "content": {"parts": [{"text": t}]},
                                  "taskType": task_type, "outputDimensionality": DIM}
                                 for t in texts[i:i + BATCH]]}
            r = self.client.post(self.URL.format(model=self.model), json=body,
                                 headers={"x-goog-api-key": self.api_key})
            r.raise_for_status()
            out += [e["values"] for e in r.json()["embeddings"]]
        return out


class FakeEmbedder:
    """Hashed bag of words: texts sharing words land close together. Tests only."""

    def embed(self, texts: list[str], task: Task) -> list[list[float]]:
        return [self._one(t) for t in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        v = [0.0] * DIM
        for word in re.findall(r"[a-z]+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]
