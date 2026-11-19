import httpx
import pytest

from app.embed import GeminiEmbedder
from app.llm import LLMError


def _client(responses):
    seq = iter(responses)
    return httpx.Client(transport=httpx.MockTransport(lambda req: next(seq)))


OK = httpx.Response(200, json={"embeddings": [{"values": [0.1] * 768}]})


def test_embed_retries_after_429():
    waits = []
    emb = GeminiEmbedder("k", "m", client=_client([
        httpx.Response(429, headers={"Retry-After": "3"}), OK]), sleep=waits.append)
    assert len(emb.embed(["x"], "doc")[0]) == 768
    assert waits == [3]


def test_embed_gives_up_with_llm_error():
    emb = GeminiEmbedder("k", "m", client=_client([httpx.Response(429)] * 5),
                         sleep=lambda s: None)
    with pytest.raises(LLMError):
        emb.embed(["x"], "doc")


def test_embed_bad_key_fails_fast():
    emb = GeminiEmbedder("k", "m", client=_client([httpx.Response(400), OK]),
                         sleep=lambda s: None)
    with pytest.raises(LLMError):
        emb.embed(["x"], "doc")
