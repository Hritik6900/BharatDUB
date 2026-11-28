"""All-GPU mode (`AI_MODE=gpu`): our own speech-to-text and translation, with the hosted ones behind them."""
import json

import httpx
import pytest

from app.config import Settings
from app.providers.base import ProviderError, STTResult, TranscriptEvent
from app.providers.fallback import FallbackLLM
from app.providers.llm_local import LocalLLM, has_latin
from app.providers.stt_gpu import GpuSTT
from app.providers.tts_gnani import ConsentRequired
from app.providers.tts_gpu_studio import GpuStudioTTS


class Hosted:
    """Stands in for the hosted speech-to-text."""

    def __init__(self):
        self.calls: list[str] = []

    async def transcribe(self, wav_path, lang="indic-auto", *, fmt=None, keyterms=None):
        self.calls.append(lang)
        return STTResult(text="hosted")

    async def stream(self, pcm_frames, lang, *, sample_rate=16000, pace=False, extra_headers=None):
        self.calls.append("stream")
        yield TranscriptEvent(kind="connected")


def gpu_stt(handler, backup=None) -> GpuSTT:
    s = Settings(ai_mode="gpu", gpu_stt_url="http://127.0.0.1:1")
    return GpuSTT(s, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), backup=backup)


async def test_gpu_stt_answers_hindi_and_hands_other_languages_to_the_hosted_service(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    hosted = Hosted()
    stt = gpu_stt(lambda req: httpx.Response(200, json={"text": " namaste doston ", "ms": 90}), hosted)
    assert (await stt.transcribe(str(wav), "hi-IN")).text == "namaste doston"
    assert (await stt.transcribe(str(wav), "ta-IN")).text == "hosted" and hosted.calls == ["ta-IN"]
    with pytest.raises(ProviderError):   # without a hosted service there is nobody to hear Tamil
        await gpu_stt(lambda req: httpx.Response(200, json={"text": "x"})).transcribe(str(wav), "ta-IN")


async def test_gpu_stt_falls_back_when_the_engine_is_down(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    hosted = Hosted()
    stt = gpu_stt(lambda req: httpx.Response(500, text="down"), hosted)
    assert (await stt.transcribe(str(wav), "hi-IN")).text == "hosted"

    async def frames():
        yield b"\x00" * 1024

    # Nothing listens on the engine's port: the hosted stream takes over.
    got = [ev.kind async for ev in stt.stream(frames(), "hi-IN")]
    assert got == ["connected"] and "stream" in hosted.calls and stt.fell_back == 2


def local_llm(replies: list[str], seen: list[dict]) -> LocalLLM:
    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": replies.pop(0)}}]})
    s = Settings(llm_base_url="http://gpu/v1", llm_model="local")
    return LocalLLM(s, client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))


async def test_local_llm_asks_again_when_a_line_for_the_voice_engine_has_latin_letters():
    seen: list[dict] = []
    llm = local_llm(["இந்த green chicken ஸ்பெஷல்", "இந்த கிரீன் சிக்கன் ஸ்பெஷல்"], seen)
    out = await llm.translate_chunk("Is green chicken ki khaas baat", "ta-IN", [], [], native=True, max_words=5)
    assert out == "இந்த கிரீன் சிக்கன் ஸ்பெஷல்" and not has_latin(out) and len(seen) == 2
    assert "at most 5 words" in seen[0]["messages"][0]["content"]


async def test_a_long_studio_line_asked_for_on_its_own_gets_room_for_its_whole_translation():
    # 28 Nov 2026: a 113-word line (a reel without a pause is one line) came back cut inside a word at 200 tokens.
    seen: list[dict] = []
    llm = local_llm(["ਗੇਮ"], seen)
    long_line = " ".join(["shabd"] * 113)
    await llm.translate_chunk(long_line, "pa-IN", [], [], native=True, max_words=147)
    assert seen[0]["max_tokens"] >= 113 * 10
    seen.clear()
    llm = local_llm(["ਗੇਮ"], seen)
    await llm.translate_chunk("aaj ham ek naya game khelenge", "pa-IN", [], [], native=True)
    assert seen[0]["max_tokens"] == 200   # a live phrase is as before


async def test_sample_text_goes_to_devanagari_and_a_bad_answer_is_not_used():
    llm = local_llm(["आज हम एक नया गेम खेलेंगे"], [])
    assert await llm.to_devanagari("aaj ham ek naya game khelenge") == "आज हम एक नया गेम खेलेंगे"
    llm = local_llm(["आज हम"], [])   # words went missing: keep what we had
    assert await llm.to_devanagari("aaj ham ek naya game khelenge aur maze karenge") == "aaj ham ek naya game khelenge aur maze karenge"
    assert await local_llm([], []).to_devanagari("आज हम") == "आज हम"   # already Devanagari: no call


async def test_fallback_llm_uses_the_hosted_model_when_ours_fails():
    class Down:
        async def translate_chunk(self, *a, **k):
            raise ProviderError("gpu model down")

    class Up:
        async def translate_chunk(self, text, target, glossary, context, **k):
            return "hosted says " + text

    llm = FallbackLLM(Down(), Up())
    assert await llm.translate_chunk("hi", "ta-IN", [], []) == "hosted says hi" and llm.fell_back == 1
    with pytest.raises(ProviderError):
        await FallbackLLM(Down(), None).translate_chunk("hi", "ta-IN", [], [])


async def test_studio_gpu_voice_needs_consent_and_has_no_stock_voice_of_its_own(tmp_path):
    class Engine:
        enabled = True

        def speaks(self, lang):
            return lang != "en-IN"

    tts = GpuStudioTTS(Engine(), Hosted(), Settings(ai_mode="gpu"), backup=None)
    with pytest.raises(ConsentRequired):   # golden rule 4: no copy without recorded consent
        await tts.clone_embedding(str(tmp_path / "x.wav"), consent_at=None)
    with pytest.raises(ProviderError):     # a stock voice exists only at the hosted service
        await tts.synth("வணக்கம்", "ta-IN", {"kind": "stock", "voice": "Asmita"})


async def test_the_models_word_for_noise_is_not_a_transcript(tmp_path):
    from app.providers.stt_gpu import not_speech
    from app.providers.stt_gpu import without_noise
    assert without_noise("nan everyone, welcome back") == "everyone, welcome back" and without_noise("Nan. nan") == ""
    assert without_noise("nanha baccha") == "nanha baccha"
    assert not_speech("nan") and not_speech("Nan.") and not not_speech("nan khao") and not not_speech("naan")
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    stt = gpu_stt(lambda req: httpx.Response(200, json={"text": "nan", "ms": 90}))
    assert (await stt.transcribe(str(wav), "hi-IN")).text == ""


def test_the_engine_is_chosen_per_call_and_the_default_stays_hosted(monkeypatch):
    """`cloud` unless a session or job asks for `gpu`, and `gpu` only when its servers are configured."""
    from app import providers
    from app.providers.stt_gnani import GnaniSTT
    ready = Settings(gpu_stt_url="http://127.0.0.1:9030", gpu_llm_url="http://127.0.0.1:9020/v1", gpu_voice_url="http://127.0.0.1:9001")
    monkeypatch.setattr(providers, "get_settings", lambda: ready)
    for f in (providers._stt, providers._llm, providers._tts, providers._gpu_voice):
        f.cache_clear()
    try:
        assert providers.engine_of(None) == "cloud" and providers.engine_of("cloud") == "cloud" and providers.engine_of("gpu") == "gpu"
        assert isinstance(providers.get_stt(), GnaniSTT) and isinstance(providers.get_stt("gpu"), GpuSTT)
        assert isinstance(providers.get_llm("gpu"), FallbackLLM) and not isinstance(providers.get_llm(), FallbackLLM)
        assert isinstance(providers.get_tts("gpu"), GpuStudioTTS) and not isinstance(providers.get_tts(), GpuStudioTTS)
        # The hosted path's voice client never rewrites a sample's text; the GPU path's does.
        assert providers.get_gpu_voice().ref_text_fix is None and providers.get_gpu_voice("gpu").ref_text_fix is not None
        monkeypatch.setattr(providers, "get_settings", lambda: Settings())   # the GPU servers are not set up
        assert providers.engine_of("gpu") == "cloud"
    finally:
        for f in (providers._stt, providers._llm, providers._tts, providers._gpu_voice):
            f.cache_clear()


def test_a_session_or_a_job_cannot_ask_for_the_gpu_engine_when_it_is_not_set_up():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "engine": "gpu"})
        assert r.status_code == 400 and "GPU engine" in r.json()["detail"]
        assert c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "engine": "x"}).status_code == 400
        r = c.post("/api/live/sessions", json={"target_langs": ["ta-IN"]})
        assert r.status_code == 201 and r.json()["engine"] == "cloud"
        assert c.get("/api/streamers/health").json()["gpu_mode"] is False


def test_second_voice_is_only_for_the_gpu_engine(monkeypatch):
    """`GPU_VOICE_MODEL=mio` changes the GPU engine's voice and nothing in the hosted engine."""
    import app.providers as prov
    from app.providers.tts_gpu import GpuVoice
    from app.providers.tts_gpu_mio import MioVoice

    s = Settings(gpu_stt_url="http://127.0.0.1:1", gpu_llm_url="http://127.0.0.1:2/v1", gpu_voice_url="http://127.0.0.1:3",
                 gpu_voice_model="mio", gpu_mio_url="http://127.0.0.1:4", mock_providers=False)
    monkeypatch.setattr(prov, "get_settings", lambda: s)
    prov._gpu_voice.cache_clear()
    try:
        mio, f5 = prov.get_gpu_voice("gpu"), prov.get_gpu_voice("cloud")
        assert isinstance(mio, MioVoice) and mio.urls == ["http://127.0.0.1:4"] and mio.capacity == 3
        assert mio.speaks("en-IN") and mio.speaks("ta-IN") and mio.ref_text_fix is None
        assert type(f5) is GpuVoice and f5.urls == ["http://127.0.0.1:3"] and not f5.speaks("en-IN")
    finally:
        prov._gpu_voice.cache_clear()


async def test_second_voice_refuses_without_consent(tmp_path):
    from app.providers.tts_gpu_mio import MioVoice

    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    mio = MioVoice(Settings(gpu_mio_url="http://127.0.0.1:4"))
    with pytest.raises(ConsentRequired):
        await mio.set_ref("s", str(wav), "", consent_at=None)


class FakeVoice:
    """A voice engine that returns what a test tells it to."""

    def __init__(self, speech_ms=lambda text, speed: 80.0 * len(text.replace(" ", "")), rate=24000):
        self.enabled, self.calls, self.refs, self._ms, self.rate = True, [], [], speech_ms, rate

    def speaks(self, lang):
        return True

    async def set_ref(self, session_id, wav_path, ref_text, **kw):
        self.refs.append(session_id)
        return {"ok": True}

    async def synth(self, session_id, text, lang, speed=None):
        import numpy as np
        self.calls.append((text, speed))
        n = int(self._ms(text, speed) / 1000 * self.rate)
        return (np.full(n, 8000, dtype="<i2")).tobytes(), self.rate


async def test_guard_sends_short_lines_to_the_second_voice_and_rescues_a_swallowed_line():
    from app.providers.tts_gpu_guard import GuardedVoice

    long_line = "yah ek lambi line hai jo theek bolti hai"
    main = FakeVoice(lambda text, speed: 0.0 if "nigal" in text else 80.0 * len(text.replace(" ", "")))
    second = FakeVoice(rate=44100)
    g = GuardedVoice(main, second, Settings(gpu_voice_short_words=4, gpu_voice_short_engine="mio"))
    await g.set_ref("s", "x.wav", "text", consent_at="2026-01-01")
    assert main.refs == ["s"] and second.refs == ["s"]
    assert (await g.synth("s", "do shabd", "ta-IN"))[1] == 44100 and g.short_lines == 1 and not main.calls
    for _ in range(5):
        assert (await g.synth("s", long_line, "ta-IN", speed=1.2))[1] == 24000
    assert g.rescued == 0
    # A long line the main engine swallows is made again by the second voice.
    assert (await g.synth("s", "yah line engine nigal jaata hai poori", "ta-IN"))[1] == 44100 and g.rescued == 1
    # A session the second voice does not hold stays on the main engine, short lines too.
    assert (await g.synth("other", "do shabd", "ta-IN"))[1] == 24000


async def test_guard_without_a_second_voice_tries_again_slower():
    from app.providers.tts_gpu_guard import GuardedVoice

    main = FakeVoice(lambda text, speed: 0.0 if (speed or 1.0) >= 1.0 else 900.0)
    g = GuardedVoice(main, None, Settings())
    pcm, rate = await g.synth("s", "aur iska", "bn-IN")
    assert len(pcm) > 0 and g.rescued == 0 and main.calls == [("aur iska", 0.75)]   # a short line: more time at once
    await g.set_ref("s", "x.wav", "t", consent_at="2026-01-01")
    swallowed = FakeVoice(lambda text, speed: 0.0 if (speed or 1.0) >= 1.0 else 2000.0)
    g2 = GuardedVoice(swallowed, FakeVoice(rate=44100), Settings())     # a second voice exists but is not used
    await g2.set_ref("s", "x.wav", "t", consent_at="2026-01-01")
    assert (await g2.synth("s", "yah lambi line engine ne nigal li thi", "bn-IN"))[1] == 24000 and g2.rescued == 1
    assert g2.second.refs == [] and g2.second.calls == []


def test_guard_is_only_in_the_gpu_engine(monkeypatch):
    import app.providers as prov
    from app.providers.tts_gpu import GpuVoice
    from app.providers.tts_gpu_guard import GuardedVoice

    s = Settings(gpu_stt_url="http://127.0.0.1:1", gpu_llm_url="http://127.0.0.1:2/v1", gpu_voice_url="http://127.0.0.1:3",
                 gpu_mio_url="http://127.0.0.1:4", mock_providers=False)
    monkeypatch.setattr(prov, "get_settings", lambda: s)
    prov._gpu_voice.cache_clear()
    try:
        g = prov.get_gpu_voice("gpu")
        assert isinstance(g, GuardedVoice) and g.second is not None and g.enabled and g.capacity == 1
        assert type(prov.get_gpu_voice("cloud")) is GpuVoice
    finally:
        prov._gpu_voice.cache_clear()


async def test_hosted_speech_to_text_first_with_the_gpu_model_behind_it(tmp_path):
    from app.providers.fallback import FallbackSTT

    class Down:
        async def transcribe(self, wav_path, lang="indic-auto", **kw):
            raise ProviderError("down")

        async def stream(self, pcm_frames, lang, **kw):
            raise ProviderError("down")
            yield  # pragma: no cover

    async def frames():
        yield b"\x00" * 1024

    ok = Hosted()
    stt = FallbackSTT(Down(), ok)
    assert (await stt.transcribe("a.wav", "hi-IN")).text == "hosted" and stt.fell_back == 1
    assert [ev.kind async for ev in stt.stream(frames(), "hi-IN")] == ["connected"] and stt.fell_back == 2
    first = FallbackSTT(ok, Down())
    assert [ev.kind async for ev in first.stream(frames(), "hi-IN")] == ["connected"] and first.fell_back == 0
