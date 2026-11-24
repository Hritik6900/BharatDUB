"""v1.1: circuit breakers on our GPU endpoints, the link-stall detector, and Live's degradation ladder.
Fake providers only: one that hangs, one that refuses, one that answers."""
import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import providers
from app.config import Settings, get_settings
from app.db import LocalStore
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession
from app.providers.base import ProviderError
from app.providers.fallback import FallbackLLM
from app.providers.llm_local import LocalLLM
from app.providers.mock import MockLLM, MockTTS
from app.providers.stt_gpu import GpuSTT
from app.providers.tts_gpu import GpuVoice
from app.v1 import breaker
from app.v1.breaker import Breaker, CircuitOpen, LinkWatch
from app.v1.degrade import Ladder
from tests.test_live import FakeGpu, SilentSTT


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(autouse=True)
def clean():
    breaker.reset()
    yield
    breaker.reset()


# ---------- the breaker itself ----------
def test_two_failures_within_ten_seconds_open_the_circuit_and_one_does_not():
    c = Clock()
    b = Breaker("x", clock=c)
    b.fail("refused")
    assert b.state == "closed" and b.allow()
    c.t += 11                      # the first failure is too old to count with the next one
    b.fail("refused")
    assert b.state == "closed"
    c.t += 3
    b.fail("refused")
    assert b.state == "open" and b.blocked() and not b.allow()
    assert [e["event"] for e in breaker.events()] == ["open"]


def test_a_timeout_opens_at_once_and_a_success_forgets_an_old_failure():
    b = Breaker("x", clock=Clock())
    b.fail("refused")
    b.ok()
    b.fail("refused")              # one failure, an answer, one failure: never two in a row
    assert b.state == "closed"
    b.fail("no answer", timed_out=True)
    assert b.state == "open"


def test_half_open_lets_one_call_through_and_its_result_decides():
    c = Clock()
    b = Breaker("x", clock=c)
    b.fail("t", timed_out=True)
    c.t += 29.9
    assert b.state == "open" and not b.allow()
    c.t += 0.2
    assert b.state == "half_open"
    assert b.allow() and not b.allow()        # one turn only
    b.fail("still dead")                      # the retry failed: open for another 30 s, counted quietly
    assert b.state == "open" and b.retries == 1 and b.opens == 1
    c.t += 30.1
    assert b.allow()
    b.ok()
    assert b.state == "closed" and b.allow() and b.allow()
    kinds = [e["event"] for e in breaker.events()]
    assert kinds == ["open", "reopen", "close"]
    assert breaker.events()[-1]["down_s"] == pytest.approx(60.2, abs=0.2)


def test_a_cancelled_retry_gives_its_turn_back():
    c = Clock()
    b = Breaker("x", clock=c)
    b.trip("link stall")
    c.t += 31
    assert b.allow() and not b.allow()
    b.release()
    assert b.allow()


async def test_call_passes_through_without_a_breaker_and_fails_fast_with_an_open_one():
    async def fine() -> str:
        return "ok"

    async def hangs() -> str:
        await asyncio.sleep(30)
        return "never"

    assert await breaker.call(None, fine) == "ok"
    b = Breaker("gpu")
    t0 = time.perf_counter()
    with pytest.raises(ProviderError, match="no answer"):
        await breaker.call(b, hangs, 0.1)
    assert time.perf_counter() - t0 < 1.0 and b.state == "open"
    t0 = time.perf_counter()
    with pytest.raises(CircuitOpen):
        await breaker.call(b, fine)
    assert time.perf_counter() - t0 < 0.05     # no waiting at all: the caller's fallback answers at once


async def test_an_answer_with_a_client_error_does_not_count_against_the_endpoint():
    b = Breaker("gpu")

    async def bad_request() -> str:
        raise ProviderError("gpu_voice.tts: HTTP 400 unknown session", status=400)

    for _ in range(3):
        with pytest.raises(ProviderError):
            await breaker.call(b, bad_request)
    assert b.state == "closed"

    async def server_error() -> str:
        raise ProviderError("gpu_voice.tts: HTTP 502", status=502, retryable=True)

    for _ in range(2):
        with pytest.raises(ProviderError):
            await breaker.call(b, server_error)
    assert b.state == "open"


# ---------- the providers behind a breaker ----------
def hanging_or(answer):
    """An httpx transport: hosts in `dead` never answer, the others get `answer(request)`."""
    dead: set[str] = set()
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host in dead:
            await asyncio.sleep(30)
        return answer(request)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), dead, calls


def chat_reply(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": "வணக்கம்"}}]})


class QuickLLM:
    async def translate_chunk(self, text, target, glossary, context, **kw):
        return f"{target} {text}"


async def test_a_dead_gpu_translation_model_costs_one_short_wait_then_nothing():
    client, dead, calls = hanging_or(chat_reply)
    s = Settings(llm_base_url="http://gpu:9020/v1", llm_model="local", v1_breaker_translate_timeout_s=0.2)
    gemma = LocalLLM(s, client)
    gemma.breaker = Breaker("gemma gpu:9020")
    llm = FallbackLLM(gemma, QuickLLM())
    assert await llm.translate_chunk("namaste doston", "ta-IN", [], []) == "வணக்கம்"   # our model answers
    dead.add("gpu")
    t0 = time.perf_counter()
    out = await llm.translate_chunk("namaste doston", "ta-IN", [], [])
    first = time.perf_counter() - t0
    assert out and llm.fell_back == 1 and 0.15 < first < 1.5     # one limit's wait, then the next provider
    assert gemma.breaker.state == "open"
    n = len(calls)
    t0 = time.perf_counter()
    for _ in range(5):
        assert await llm.translate_chunk("namaste doston", "ta-IN", [], [])
    assert time.perf_counter() - t0 < 0.2 and len(calls) == n    # five phrases, no wait, the dead model not called
    assert llm.fell_back == 6


async def test_without_a_breaker_the_translation_call_is_the_old_one():
    client, dead, calls = hanging_or(chat_reply)
    gemma = LocalLLM(Settings(llm_base_url="http://gpu:9020/v1", llm_model="local"), client)
    assert gemma.breaker is None
    assert await gemma.translate_chunk("namaste", "ta-IN", [], []) == "வணக்கம்"
    dead.add("gpu")
    with pytest.raises(TimeoutError):      # nothing but the caller's own limit ends the wait, as before
        await asyncio.wait_for(gemma.translate_chunk("namaste", "ta-IN", [], []), 0.5)
    assert not breaker.snapshot()


def pcm_reply(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"\x10\x20" * 2400, headers={"x-sample-rate": "24000", "x-format": "pcm"})


async def test_a_dead_voice_engine_is_left_out_and_the_others_keep_speaking():
    client, dead, calls = hanging_or(pcm_reply)
    s = Settings(gpu_voice_url="http://e1:9001,http://e2:9002", v1_breaker_voice_timeout_s=0.2, gpu_voice_format="pcm")
    gpu = GpuVoice(s, client)
    gpu.breakers = [Breaker("indicf5 e1:9001"), Breaker("indicf5 e2:9002")]
    dead.add("e1")
    with pytest.raises(ProviderError):                 # the line that found the dead engine
        await gpu.synth("s", "வணக்கம்", "ta-IN")
    assert gpu.breakers[0].state == "open"
    calls.clear()
    for _ in range(4):
        pcm, rate = await gpu.synth("s", "வணக்கம்", "ta-IN")
        assert pcm and rate == 24000
    assert calls == ["e2"] * 4                         # only the engine that answers is asked
    dead.add("e2")
    with pytest.raises(ProviderError):
        await gpu.synth("s", "வணக்கம்", "ta-IN")
    t0 = time.perf_counter()
    with pytest.raises(CircuitOpen):                   # both open: the stock voice is asked without any wait
        await gpu.synth("s", "வணக்கம்", "ta-IN")
    assert time.perf_counter() - t0 < 0.05


async def test_gpu_speech_to_text_with_an_open_circuit_goes_straight_to_the_hosted_one(tmp_path, monkeypatch):
    class Hosted:
        def __init__(self) -> None:
            self.streams = 0

        async def transcribe(self, wav_path, lang="indic-auto", **kw):
            from app.providers.base import STTResult
            return STTResult(text="hosted heard it", detected_lang="hi-IN")

        async def stream(self, frames, lang="indic-auto", **kw):
            self.streams += 1
            return
            yield  # pragma: no cover

    async def no_socket(*a, **kw):
        raise AssertionError("an open circuit must not be dialled")

    monkeypatch.setattr("app.providers.stt_gpu.websockets.connect", no_socket)
    hosted = Hosted()
    stt = GpuSTT(Settings(gpu_stt_url="http://gpu:9030"), httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: (_ for _ in ()).throw(AssertionError("an open circuit must not be called")))), backup=hosted)
    stt.breaker = Breaker("whisper_gpu gpu:9030")
    stt.breaker.trip("link stall")
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    assert (await stt.transcribe(str(wav), "hi-IN")).text == "hosted heard it"

    async def frames():
        return
        yield  # pragma: no cover

    assert [ev async for ev in stt.stream(frames(), "hi-IN")] == [] and hosted.streams == 1


# ---------- the link-stall detector ----------
async def test_every_gpu_endpoint_failing_at_once_is_a_link_stall_and_opens_all_circuits():
    answers = {"a": "", "b": "", "c": ""}

    async def probe(url: str) -> str:
        return answers[url]

    watch = LinkWatch(probe, [("indicf5 e1", "a"), ("gemma g", "b"), ("whisper_gpu w", "c")], Settings())
    await watch.round()
    assert all(c["state"] == "closed" for c in breaker.snapshot())
    answers["b"] = "ConnectError"                      # one model down is not the link
    await watch.round()
    assert watch.stalled_since is None and breaker.get("gemma g").state == "closed"
    await watch.round()                                # refused twice within ten seconds: that one opens
    assert breaker.get("gemma g").state == "open" and breaker.get("indicf5 e1").state == "closed"
    answers.update(a="timeout", c="ConnectError")
    await watch.round()
    assert watch.stalled_since is not None
    assert {c["name"]: c["state"] for c in breaker.snapshot()} == {
        "indicf5 e1": "open", "gemma g": "open", "whisper_gpu w": "open"}
    kinds = [e["event"] for e in breaker.events()]
    assert kinds.count("link_stall") == 1 and kinds.count("open") == 3
    await watch.round()
    assert [e["event"] for e in breaker.events()].count("link_stall") == 1    # said once, not every round

    # The link is back. A circuit stays open for its 30 s, then the detector's own probe closes it.
    answers.update(a="", b="", c="")
    await watch.round()
    assert breaker.events()[-1]["event"] == "link_back" and breaker.get("indicf5 e1").state == "open"
    for b in (breaker.get(n) for n in ("indicf5 e1", "gemma g", "whisper_gpu w")):
        b._opened_at -= 31
    await watch.round()
    assert all(c["state"] == "closed" for c in breaker.snapshot())


async def test_while_the_detector_runs_the_retry_is_its_probe_and_no_call_is_spent_on_it():
    answers = {"a": "timeout", "b": "timeout"}

    async def probe(url: str) -> str:
        return answers[url]

    watch = LinkWatch(probe, [("indicf5 e1", "a"), ("gemma g", "b")], Settings(v1_link_probe_every_s=3600))
    watch.start()
    try:
        await asyncio.sleep(0.05)                      # its first round: both dead, a link stall
        b = breaker.get("gemma g")
        assert b.state == "open" and b.watched
        b._opened_at -= 31
        assert b.state == "half_open" and b.blocked() and not b.allow()   # a phrase's call is still refused
        await watch.round()                            # the probe fails: it is simply tried again next round
        assert b.state == "half_open" and b.retries == 1 and not b.allow()
        answers.update(a="", b="")
        breaker.get("indicf5 e1")._opened_at -= 31
        await watch.round()                            # the detector's probe is the retry
        assert b.state == "closed" and b.allow()
    finally:
        watch.stop()
    assert not b.watched
    b.trip("again")
    b._opened_at -= 31
    assert b.allow()                                   # no detector running: the first call is the retry


# ---------- flags off: nothing is attached, nothing is reported ----------
def test_with_the_flags_off_no_provider_has_a_breaker_and_the_status_answer_has_none(monkeypatch):
    s = get_settings()
    assert s.v1_breaker is False and s.v1_live_degrade is False
    ready = s.model_copy(update={"gpu_stt_url": "http://127.0.0.1:1", "gpu_llm_url": "http://127.0.0.1:1/v1",
                                 "gpu_voice_url": "http://127.0.0.1:1", "ai_mode": "gpu", "mock_providers": False})
    monkeypatch.setattr(providers, "get_settings", lambda: ready)
    caches = (providers._stt, providers._tts, providers._llm, providers._gpu_voice)
    for f in caches:
        f.cache_clear()
    try:
        llm, stt, gpu = providers.get_llm("gpu"), providers.get_stt("gpu"), providers.get_gpu_voice("gpu")
        assert llm.first.breaker is None
        assert getattr(stt, "breaker", None) is None and getattr(getattr(stt, "second", None), "breaker", None) is None
        assert gpu.breakers is None
        assert not breaker.snapshot()

        # The same setup with V1_BREAKER on: each of our endpoints has one, the hosted ones none.
        on = ready.model_copy(update={"v1_breaker": True, "llm_base_url": "http://hosted", "llm_model": "m"})
        monkeypatch.setattr(providers, "get_settings", lambda: on)
        monkeypatch.setattr(breaker, "get_settings", lambda: on)
        for f in caches:
            f.cache_clear()
        llm, gpu = providers.get_llm("gpu"), providers.get_gpu_voice("gpu")
        assert llm.first.breaker.name == "gemma 127.0.0.1:1" and llm.second.breaker is None
        assert [b.name for b in gpu.breakers] == ["indicf5 127.0.0.1:1"]
        assert providers.get_stt("gpu").breaker.name == "whisper_gpu 127.0.0.1:1"
    finally:
        for f in caches:
            f.cache_clear()
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/v1/circuits").json() == {"on": False, "circuits": [], "events": [], "last": 0}
        h = c.get("/api/v1/health").json()
        assert "circuits" not in h and h["flags"]["V1_BREAKER"] is False and h["flags"]["V1_LIVE_DEGRADE"] is False


def test_the_status_answer_never_gives_this_machines_card_as_the_gpu():
    from app.main import app
    with TestClient(app) as c:
        h = c.get("/api/v1/health").json()
    assert h["gpu"] is None and h["gpu_name"] == "A100 (VM)"     # no endpoint on the VM yet: unknown
    assert "local_card" in h                                      # whatever this machine has is named as such


async def test_the_gpu_machines_own_report_is_what_the_status_answer_shows(monkeypatch):
    from app.v1 import health

    def reply(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/gpu"
        return httpx.Response(200, json={"stub": False, "gpus": [
            {"name": "NVIDIA A100-SXM4-40GB", "used_gb": 34.7, "free_gb": 5.3, "total_gb": 40.0, "util_pct": 19.0,
             "temp_c": 51.0, "power_w": 110.0}], "processes": [{"pid": 1, "name": "python", "used_gb": 13.1}]})
    s = Settings(v1_qa_url="http://vm:9045")
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        g = await health.vm_gpu(client, s)
    assert g["total_gb"] == 40.0 and g["free_gb"] == 5.3 and g["processes"][0]["used_gb"] == 13.1
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"stub": True, "gpus": []}))) as client:
        assert await health.vm_gpu(client, s) is None             # a stub server knows no card
    async with httpx.AsyncClient() as client:
        assert await health.vm_gpu(client, Settings()) is None    # no address: unknown, and nothing is called


# ---------- the ladder ----------
def test_ladder_steps_down_after_two_failures_and_back_up_on_the_first_success():
    now = [0]
    lad = Ladder(lambda: now[0], fails=2, probe_ms=10000)
    best = {"wants_copied": True, "copied_ready": True, "copied_up": True}
    assert lad.level(**best) == (0, "")
    lad.note("copied", False)
    assert lad.level(**best)[0] == 0               # one failure is not a step
    lad.note("copied", False)
    assert lad.level(**best)[0] == 1
    lad.note("stock", False)
    lad.note("stock", False)
    assert lad.level(**best) == (2, "no voice answers")
    assert lad.may_try("stock") and not lad.may_try("stock")   # down: one try, then not before 10 s
    now[0] += 10000
    assert lad.may_try("stock")
    lad.note("translate", False)
    lad.note("translate", False)
    assert lad.level(**best)[0] == 3
    lad.note("translate", True)
    lad.note("stock", True)
    assert lad.level(**best)[0] == 1 and lad.may_try("stock") and lad.may_try("stock")
    lad.note("copied", True)
    assert lad.level(**best) == (0, "")
    assert lad.level(wants_copied=False, copied_ready=False, copied_up=True) == (1, "")   # a stock session's best
    assert lad.level(wants_copied=True, copied_ready=True, copied_up=False)[0] == 1       # the breaker says so first


class FlakyTTS(MockTTS):
    def __init__(self) -> None:
        super().__init__(24000)
        self.dead = False
        self.asked = 0
        self.error: Exception = ProviderError("tts: ConnectError", retryable=True)

    async def synth_stream(self, text, lang, voice, *, sample_rate=None, speed=1.0):
        self.asked += 1
        if self.dead:
            raise self.error
        async for chunk in super().synth_stream(text, lang, voice, sample_rate=sample_rate):
            yield chunk


class FlakyGpu(FakeGpu):
    dead = False

    async def synth(self, session_id, text, lang, speed=None):
        if self.dead:
            raise ProviderError("gpu_voice.tts: ConnectError", retryable=True)
        return await super().synth(session_id, text, lang, speed)


class FlakyLLM(MockLLM):
    dead = False

    async def translate_chunk(self, text, target, glossary, context, **kw):
        if self.dead:
            raise ProviderError("llm.chat: ConnectError", retryable=True)
        return await super().translate_chunk(text, target, glossary, context)


def degrade_on(monkeypatch, tmp_path, **more):
    s = get_settings().model_copy(update={"v1_live_degrade": True, "live_warmup": False, "v1_degrade_probe_ms": 600000,
                                          **more})
    monkeypatch.setattr("app.live.pipeline.get_settings", lambda: s)
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    return store


async def say(p: LivePipeline, q: asyncio.Queue, text: str) -> list[dict]:
    """One phrase through the pipeline; every message of its language up to the end of its audio."""
    now = p.sess.now_ms()
    chunk = p.assembler.make(text, t_start_ms=now, t_end_ms=now, t_final_ms=now)
    p._dispatch(chunk)
    got = []
    while True:
        m = await asyncio.wait_for(q.get(), 10)
        if m.get("seq") == chunk.seq:
            got.append(m)
            if m["type"] == "audio" and m["last"]:
                return got


def has_audio(msgs: list[dict]) -> bool:
    return any(m["type"] == "audio" and m["pcm_b64"] for m in msgs)


async def test_live_steps_from_the_copied_voice_to_stock_to_captions_and_climbs_back(tmp_path, monkeypatch):
    store = degrade_on(monkeypatch, tmp_path)
    sess = LiveSession({"id": "d1", "target_langs": ["ta-IN"], "src_lang": "hi-IN",
                        "voice_from_stream": {"consent_at": "2026-11-24T10:00:00+00:00", "consent_text": "ok"}})
    gpu, tts = FlakyGpu(), FlakyTTS()
    tts.error = httpx.RemoteProtocolError("peer closed connection")   # what a dropped hosted voice really raises
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=tts, gpu=gpu)
    q = sess.bus.subscribe("ta-IN")
    await p.start()
    assert p.rung()[0] == 1 and "not ready" in p.rung()[1]      # the voice is not learned yet: a stock voice
    p.gpu_ready, p._gpu_sid = True, "d1-v1"                      # ... now it is (consent was given above)
    assert has_audio(await say(p, q, "pehli line yahan hai")) and p.rung() == (0, "")
    assert len(gpu.lines) == 1 and tts.asked == 0

    gpu.dead = True                                              # the GPU machine goes away
    for i in range(2):
        assert has_audio(await say(p, q, f"line number {i} hai"))   # every line is still spoken: the stock voice
    assert p.rung()[0] == 1 and tts.asked == 2
    assert p._rung_tick() == {"rung": "stock"}

    tts.dead = True                                              # ... and then the hosted voice too
    msgs = [await say(p, q, f"aur ek line {i}") for i in range(4)]
    assert not any(has_audio(m) for m in msgs)
    assert all(any(m["type"] == "caption" and m["text"] for m in ms) for ms in msgs)   # captions never stop
    assert p._rung_tick() == {"rung": "captions"}
    asked = tts.asked
    await say(p, q, "yeh line bina awaaz ke")                    # captions only: the dead voice is not asked ...
    assert tts.asked == asked
    p._ladder._tried.clear()                                     # (as if the time between two tries had passed)
    await say(p, q, "yeh line phir koshish karti hai")           # ... except one try now and then
    assert tts.asked == asked + 1 and p.running

    tts.dead = False                                             # the hosted voice is back
    p._ladder._tried.clear()
    assert has_audio(await say(p, q, "awaaz wapas aa gayi"))
    assert p._rung_tick() == {"rung": "stock"}
    gpu.dead = False                                             # and the GPU machine
    p._gpu_fail, p._gpu_retry_at = 0, 0
    assert has_audio(await say(p, q, "apni awaaz wapas"))
    assert p._rung_tick() == {"rung": "copied"}
    assert [r["rung"] for r in p.rungs][-4:] == ["stock", "captions", "stock", "copied"]   # (the first entry is where it began)
    changes = [m async for m in drain(sess.bus.subscribe("*"))]  # nothing queued for a new subscriber
    assert changes == []
    await p.stop()
    rows = sorted(await store.select("live_chunks", session_id="d1"), key=lambda r: r["seq"])
    used = [r["timings"].get("rung:ta-IN") for r in rows]
    assert used[0] == 0 and used[1:3] == [1, 1] and used[3:7] == [2, 2, 2, 2] and used[-2:] == [1, 0]
    assert p.degrade_stats()["rung"] == "copied" and len(p.degrade_stats()["rung_changes"]) >= 4


async def drain(q: asyncio.Queue):
    while not q.empty():
        yield q.get_nowait()


async def test_live_goes_to_the_original_sound_without_translation_or_transcript_and_never_ends(tmp_path, monkeypatch):
    degrade_on(monkeypatch, tmp_path)
    sess = LiveSession({"id": "d2", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    llm = FlakyLLM()

    class DeadSTT:
        tries = 0

        async def stream(self, frames, lang, **kw):
            DeadSTT.tries += 1
            raise ProviderError("stt: every provider failed")
            yield  # pragma: no cover

    p = LivePipeline(sess, stt=DeadSTT(), llm=llm, tts=MockTTS(24000))
    q, everyone = sess.bus.subscribe("ta-IN"), sess.bus.subscribe("*")
    await p.start()
    llm.dead = True
    for i in range(2):
        msgs = await say(p, q, f"line {i} ka translation nahi")
        assert not has_audio(msgs) and any(m.get("untranslated") for m in msgs)
    assert p._ladder.down("translate") and p.rung()[0] == 3
    llm.dead = False
    assert has_audio(await say(p, q, "translation wapas aa gaya"))
    assert not p._ladder.down("translate")           # one answer and translation counts as up again
    for _ in range(40):                              # the speech-to-text stream fails again and again ...
        if DeadSTT.tries >= 2:
            break
        await asyncio.sleep(0.1)
    assert DeadSTT.tries >= 2 and p.running          # ... and the session is still live
    assert p.rung() == (3, "speech-to-text does not answer")
    p._rung_tick()
    seen = [m async for m in drain(everyone)]
    assert any(m["type"] == "degrade" and m["rung"] == "original" for m in seen)
    await asyncio.sleep(1.1)                         # the clock message tells a viewer who joins now
    clocks = [m async for m in drain(everyone) if m["type"] == "clock"]
    assert clocks and clocks[-1]["rung"] == "original"
    await p.stop()


async def test_with_the_ladder_off_nothing_about_rungs_is_sent_or_stored(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    sess = LiveSession({"id": "d3", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    tts = FlakyTTS()
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=tts)
    assert p._ladder is None
    q, everyone = sess.bus.subscribe("ta-IN"), sess.bus.subscribe("*")
    await p.start()
    assert has_audio(await say(p, q, "ek seedhi line"))
    tts.dead = True
    for i in range(4):                               # a dead voice is asked for every line, as it always was
        assert not has_audio(await say(p, q, f"line {i} bina awaaz"))
    assert tts.asked >= 5
    await asyncio.sleep(1.1)
    seen = [m async for m in drain(everyone)]
    assert not any(m["type"] == "degrade" for m in seen)
    assert all("rung" not in m for m in seen if m["type"] == "clock") and any(m["type"] == "clock" for m in seen)
    await p.stop()
    assert p.degrade_stats() == {}
    rows = await store.select("live_chunks", session_id="d3")
    assert rows and not any(k.startswith("rung") or v == "degraded" for r in rows for k, v in r["timings"].items())


async def test_a_gpu_machine_that_does_not_answer_cannot_hold_a_streamers_session_start(tmp_path, monkeypatch):
    store = degrade_on(monkeypatch, tmp_path, v1_degrade_voice_wait_s=0.2)
    from app.shared import voices
    monkeypatch.setattr(voices, "voices_dir", lambda: tmp_path)
    (tmp_path / "ref.wav").write_bytes(b"RIFF")
    profile = await store.insert("voice_profiles", {"display_name": "me", "consent_at": "2026-11-24T10:00:00+00:00",
                                                    "ref_path": "ref.wav", "ref_text": "yeh meri awaaz hai dosto",
                                                    "embedding": None})

    async def text_of(p, path, lang, stt=None):
        return p["ref_text"]

    monkeypatch.setattr("app.streamer.voice_ref.sample_text", text_of)

    class SlowGpu(FakeGpu):
        hang = True

        async def set_ref(self, session_id, wav_path, ref_text, *, consent_at, steps=None):
            if self.hang:
                await asyncio.sleep(30)
            return await super().set_ref(session_id, wav_path, ref_text, consent_at=consent_at, steps=steps)

    gpu = SlowGpu()
    sess = LiveSession({"id": "d4", "target_langs": ["ta-IN"], "src_lang": "hi-IN", "streamer_id": "st1",
                        "voice_mode": "clone", "voice_profile_id": profile["id"]})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS(24000), gpu=gpu)
    t0 = time.perf_counter()
    await p.start()
    assert time.perf_counter() - t0 < 2.0 and p.running and not p.gpu_ready
    assert p.rung()[0] == 1                           # live in a stock voice meanwhile
    gpu.hang = False                                  # the machine answers again: the voice is asked for again
    p._stored_try_at = -10**9
    p._rung_tick()
    for _ in range(50):
        if p.gpu_ready:
            break
        await asyncio.sleep(0.02)
    assert p.gpu_ready and p._gpu_stored and gpu.refs and p.rung() == (0, "")
    await p.stop()


def test_the_stream_watcher_prints_opens_and_closes_once_and_survives_an_old_backend(tmp_path, monkeypatch):
    import importlib.util
    import urllib.error
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "stream_watch", Path(__file__).resolve().parents[2] / "scripts" / "v1" / "stream-watch.py")
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    answers: list = []
    asked: list[str] = []

    def fake_get(url, timeout=10):
        asked.append(url)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(sw, "get", fake_get)
    w = sw.Watch(tmp_path, [], "http://127.0.0.1:8110/api/v1/health")
    said: list[str] = []
    monkeypatch.setattr(w, "say", said.append)
    gemma = {"name": "gemma 127.0.0.1:9020", "state": "open", "opens": 1, "down_s": 12.0, "reason": "link stall (timeout)"}
    answers.append({"on": True, "last": 4, "circuits": [gemma], "events": [{"id": 4, "name": "x", "event": "open"}]})
    w.circuits()                                   # first look: what is open now, not the history
    assert said == ["CIRCUIT OPEN gemma 127.0.0.1:9020: link stall (timeout) (already, for 12.0 s)"]
    answers.append({"on": True, "last": 6, "circuits": [], "events": [
        {"id": 5, "name": "link", "event": "link_back", "down_s": 47.8, "answering": 3, "services": 3},
        {"id": 6, "name": "gemma 127.0.0.1:9020", "event": "close", "down_s": 47.8, "retries": 2}]})
    w.circuits()
    assert asked[-1].endswith("/api/v1/circuits?after=4")
    assert said[1:] == ["CIRCUIT LINK BACK after 47.8 s: 3 of 3 GPU endpoints answer",
                        "CIRCUIT CLOSED gemma 127.0.0.1:9020 after 47.8 s (2 retries failed first)"]
    answers.append({"on": True, "last": 1, "circuits": [], "events": []})     # the backend restarted: ids began again
    w.circuits()
    answers.append({"on": True, "last": 1, "circuits": [], "events": [
        {"id": 1, "name": "indicf5 127.0.0.1:9001", "event": "open", "reason": "TimeoutError"}]})
    w.circuits()
    assert asked[-1].endswith("after=0") and said[-1] == "CIRCUIT OPEN indicf5 127.0.0.1:9001: TimeoutError"
    answers.append(urllib.error.HTTPError("u", 404, "Not Found", None, None))  # a backend from before the breakers
    w.circuits()
    n = len(asked)
    w.circuits()
    assert len(asked) == n and len(said) == 4       # asked once, then left alone
