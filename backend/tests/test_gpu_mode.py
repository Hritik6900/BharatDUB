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
