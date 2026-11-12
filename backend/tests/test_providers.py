"""Provider unit tests with mocked HTTP (httpx.MockTransport). No network, no credits."""
import base64
import json

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.providers.base import ProviderError
from app.providers.llm_openai import OpenAILLM, parse_json_array, strip_thinking
from app.providers.stt_gnani import GnaniSTT, parse_ws_message
from app.providers.tts_gnani import ConsentRequired, GnaniTTS, iter_sse, parse_embedding

KEY = "test-key-123"


def settings() -> Settings:
    return Settings(_env_file=None, gnani_api_key=SecretStr(KEY), llm_base_url="https://llm.test/v1",
                    llm_api_key=SecretStr("llm-key"), llm_model="m", gnani_max_concurrency=1)


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_s: float) -> None:
        return None
    monkeypatch.setattr("app.providers.http.asyncio.sleep", instant)


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "clip.wav"
    p.write_bytes(b"RIFF....WAVEfmt fake")
    return p


# ---------- STT ----------
async def test_stt_transcribe_sends_expected_request(wav):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["key"] = req.headers.get("X-API-Key-ID")
        seen["body"] = req.content
        return httpx.Response(200, json={"success": True, "request_id": "r1", "transcript": " namaste ",
                                         "model": "prisma-v3.0", "detected_language_code": "hi-IN",
                                         "processing_time": 0.4})

    res = await GnaniSTT(settings(), client(handler)).transcribe(str(wav))
    assert seen["url"] == "https://api.vachana.ai/stt/v3"
    assert seen["key"] == KEY
    assert b'name="audio_file"; filename="clip.wav"' in seen["body"]
    assert b"prisma-v3.0" in seen["body"] and b"indic-auto" in seen["body"]
    assert res.text == "namaste" and res.detected_lang == "hi-IN" and res.latency_s is not None


async def test_stt_retries_once_on_500_then_succeeds(wav):
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "down"})
        return httpx.Response(200, json={"success": True, "transcript": "ok"})

    res = await GnaniSTT(settings(), client(handler)).transcribe(str(wav))
    assert res.text == "ok" and len(calls) == 2


async def test_stt_gives_up_after_one_retry(wav):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500, json={"success": False})

    with pytest.raises(ProviderError) as e:
        await GnaniSTT(settings(), client(handler)).transcribe(str(wav))
    assert len(calls) == 2 and e.value.status == 500


async def test_stt_backs_off_on_429(wav):
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, json={"detail": {"error_code": "RATE_LIMITED", "message": "1 active"}})
        return httpx.Response(200, json={"success": True, "transcript": "ok"})

    assert (await GnaniSTT(settings(), client(handler)).transcribe(str(wav))).text == "ok"
    assert len(calls) == 3


async def test_stt_auth_error_not_retried_and_key_not_leaked(wav):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401, json={"detail": {"error_code": "INVALID_API_KEY", "message": "bad key"}})

    with pytest.raises(ProviderError) as e:
        await GnaniSTT(settings(), client(handler)).transcribe(str(wav))
    assert len(calls) == 1 and KEY not in str(e.value)


async def test_stt_success_false_raises(wav):
    def handler(req):
        return httpx.Response(200, json={"success": False, "error": {"type": "EMPTY_AUDIO", "message": "empty"}})

    with pytest.raises(ProviderError, match="empty"):
        await GnaniSTT(settings(), client(handler)).transcribe(str(wav))


def test_stt_ws_message_parsing():
    ev = parse_ws_message(json.dumps({"type": "transcript", "text": " hello ", "segment_id": "r-seg-0",
                                      "is_final": True, "latency": 0.3, "detected_language_code": "hi-IN"}))
    assert ev and ev.kind == "final" and ev.text == "hello" and ev.detected_lang == "hi-IN"
    assert parse_ws_message('{"type":"processing"}').kind == "processing"
    assert parse_ws_message('{"type":"error","message":"x"}').message == "x"
    assert parse_ws_message('{"type":"settings_updated"}') is None
    assert parse_ws_message("not json") is None


def test_missing_key_raises(wav):
    s = settings()
    s.gnani_api_key = SecretStr("")
    with pytest.raises(ProviderError, match="GNANI_API_KEY"):
        GnaniSTT(s, client(lambda r: httpx.Response(200)))._key()


# ---------- TTS ----------
async def test_tts_stock_body_and_audio():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, content=b"RIFFaudio", headers={"content-type": "audio/wav"})

    audio = await GnaniTTS(settings(), client(handler)).synth("hello", "ta-IN", {"kind": "stock", "voice": "Asmita"})
    assert audio == b"RIFFaudio"
    assert seen["model"] == "timbre-v2.5" and seen["voice"] == "Asmita" and seen["language"] == "ta-IN"
    assert seen["audio_config"]["sample_rate"] == 44100


async def test_tts_clone_body_has_no_voice_or_language():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, content=b"RIFF", headers={"content-type": "audio/wav"})

    emb = {"embedding": "abc", "shape": [1, 768], "dtype": "torch.bfloat16"}
    await GnaniTTS(settings(), client(handler)).synth("hi", "ta-IN", {"kind": "clone", "embedding": emb})
    assert seen["model"] == "vachana-vc-v1" and seen["speaker_embedding"] == emb
    assert "voice" not in seen and "language" not in seen


async def test_tts_json_response_is_error():
    def handler(req):
        return httpx.Response(200, json={"oops": 1})

    with pytest.raises(ProviderError):
        await GnaniTTS(settings(), client(handler)).synth("x", "hi-IN", {"kind": "stock", "voice": "Nalini"})


async def test_tts_stream_decodes_sse_chunks():
    pcm1, pcm2 = b"\x01\x02" * 10, b"\x03\x04" * 10
    sse = (
        'event: start\ndata: {"status":"streaming_started"}\n\n'
        f'event: chunk\ndata: {{"chunk_index":0,"audio":"{base64.b64encode(pcm1).decode()}","is_final":false}}\n\n'
        f'event: chunk\ndata: {{"chunk_index":1,"audio":"{base64.b64encode(pcm2).decode()}","is_final":false}}\n\n'
        'event: complete\ndata: {"chunk_index":2,"audio":"","is_final":true}\n\n'
    )
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})

    tts = GnaniTTS(settings(), client(handler))
    out = [c async for c in tts.synth_stream("x", "hi-IN", {"kind": "stock", "voice": "Nalini"})]
    assert out == [pcm1, pcm2]
    assert seen["url"].endswith("/api/v1/tts/sse") and seen["body"]["audio_config"]["container"] == "raw"
    assert tts.last_first_chunk_s is not None


async def test_clone_refused_without_consent(wav):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={})

    with pytest.raises(ConsentRequired) as e:
        await GnaniTTS(settings(), client(handler)).clone_embedding(str(wav), consent_at=None)
    assert e.value.status == 403 and calls == []


async def test_clone_embedding_parses_nested_response(wav):
    def handler(req):
        assert req.url.path == "/api/v1/tts/voice-clone/embeddings"
        return httpx.Response(200, json={"success": True, "message": "ok", "data": {"voice_clone_embedding": {
            "embedding": "b64", "shape": [1, 768], "dtype": "torch.bfloat16"}}})

    emb = await GnaniTTS(settings(), client(handler)).clone_embedding(str(wav), consent_at="2026-11-13T00:00:00Z")
    assert emb == {"embedding": "b64", "shape": [1, 768], "dtype": "torch.bfloat16"}


def test_parse_embedding_flat_and_bad():
    assert parse_embedding({"embedding": "e", "shape": [1, 768], "dtype": "d"})["embedding"] == "e"
    with pytest.raises(ProviderError):
        parse_embedding({"success": True, "data": {}})


async def test_iter_sse_handles_multiline_data():
    async def lines():
        for line in ["event: chunk", "data: a", "data: b", "", "data: c"]:
            yield line
    assert [x async for x in iter_sse(lines())] == [("chunk", "a\nb"), ("message", "c")]


# ---------- LLM ----------
def llm_handler(contents: list[str], seen: list[dict]):
    def handler(req):
        seen.append(json.loads(req.content))
        text = contents[min(len(seen) - 1, len(contents) - 1)]
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})
    return handler


async def test_translate_batch_strips_reasoning():
    seen: list[dict] = []
    out = await OpenAILLM(settings(), client(llm_handler(
        ['<think>hmm ["no"]</think>Sure: ["ஒன்று", "இரண்டு"] done'], seen))).translate_batch(["a", "b"], "ta-IN", ["GG"])
    assert out == ["ஒன்று", "இரண்டு"]
    assert "Tamil" in seen[0]["messages"][0]["content"] and "GG" in seen[0]["messages"][0]["content"]


async def test_translate_batch_retries_then_falls_back_per_line():
    seen: list[dict] = []
    contents = ['["only one"]', '["still one"]', "line A", "line B"]
    out = await OpenAILLM(settings(), client(llm_handler(contents, seen))).translate_batch(["a", "b"], "bn-IN", [])
    assert len(seen) == 4 and out == ["line A", "line B"]


async def test_translate_chunk_uses_fast_model_and_context():
    s = settings()
    s.llm_model_fast = "fast"
    seen: list[dict] = []
    out = await OpenAILLM(s, client(llm_handler(['"Translation: hello"'], seen))).translate_chunk(
        "namaste", "en-IN", [], ["c1", "c2", "c3", "c4"])
    assert out == "hello" and seen[0]["model"] == "fast"
    user = seen[0]["messages"][1]["content"]
    assert "c1" not in user and "c4" in user and "CURRENT: namaste" in user


async def test_llm_not_configured():
    s = settings()
    s.llm_base_url = ""
    with pytest.raises(ProviderError):
        await OpenAILLM(s, client(lambda r: httpx.Response(200))).shorten("x", "ta-IN", 2.0)


def test_parse_helpers():
    assert strip_thinking("reasoning...</think> answer") == "answer"
    assert parse_json_array('x ["a", 1] y') == ["a", "1"]
    with pytest.raises(ValueError):
        parse_json_array("no array")
