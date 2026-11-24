"""API call log: one record per attempt, nothing of the request's content, nothing when the flag is off."""
import json

import httpx
import pytest

from app.config import get_settings
from app.providers.base import ProviderError
from app.providers.http import request_with_retry
from app.v1 import apilog


@pytest.fixture
def logs(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "v1_log_dir", str(tmp_path))
    monkeypatch.setattr(s, "v1_api_log", True)
    return tmp_path


def records(root) -> list[dict]:
    return [json.loads(line) for f in sorted(root.rglob("*.jsonl")) for line in f.read_text().splitlines()]


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_a_call_is_recorded_without_its_content(logs):
    apilog.set_test("live", "abcdef1234567890")
    c = client(lambda req: httpx.Response(200, content=b"x" * 40))
    await request_with_retry(lambda: c.post("http://127.0.0.1:9020/v1/chat/completions?key=SECRET",
                                            headers={"X-API-Key-ID": "SECRET"}, json={"text": "a private line"}),
                             what="llm.chat")
    (r,) = records(logs)
    assert (r["test"], r["api"], r["method"], r["host"], r["path"]) == ("live_abcdef12", "llm.chat", "POST",
                                                                       "127.0.0.1:9020", "/v1/chat/completions")
    assert r["status"] == 200 and r["ok"] and r["attempt"] == 0 and r["bytes_in"] == 40 and r["bytes_out"] > 0
    assert r["ms"] >= 0 and r["error"] is None
    text = next(logs.rglob("*.jsonl")).read_text()
    assert "SECRET" not in text and "private" not in text
    assert next(logs.rglob("*.jsonl")).name == "live_abcdef12.jsonl"


async def test_every_attempt_is_recorded(logs):
    apilog.set_test("job", "0011223344")
    answers = iter([httpx.Response(503, json={"error": "busy"}), httpx.Response(200, json={})])
    c = client(lambda req: next(answers))
    await request_with_retry(lambda: c.get("http://voice/tts"), what="gpu_voice.tts", backoff_s=0)
    a, b = records(logs)
    assert (a["status"], a["ok"], a["attempt"]) == (503, False, 0) and (b["status"], b["ok"], b["attempt"]) == (200, True, 1)


async def test_no_answer_is_recorded_with_its_kind(logs):
    def boom(req):
        raise httpx.ConnectError("refused")
    c = client(boom)
    with pytest.raises(ProviderError):
        await request_with_retry(lambda: c.get("http://voice/tts"), what="gpu_voice.tts", retries=0)
    (r,) = records(logs)
    assert r["status"] is None and r["error"] == "ConnectError" and not r["ok"]


async def test_nothing_is_written_with_the_flag_off(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "v1_log_dir", str(tmp_path))
    c = client(lambda req: httpx.Response(200))
    await request_with_retry(lambda: c.get("http://voice/tts"), what="gpu_voice.tts")
    assert not list(tmp_path.rglob("*"))
