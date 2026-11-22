"""v1 router: the shipped routing file gives the providers v0's fixed table gives; fallbacks, timeouts, stickiness."""
import asyncio

import pytest
from pydantic import SecretStr

from app import providers
from app.config import BACKEND_DIR, get_settings
from app.providers.base import ProviderError
from app.v1.router import Router, RoutingError, load_config, validate
from app.v1.stages import StageFailed, Stages


def shape(obj) -> object:
    """A provider and what stands behind it, as nested class names."""
    if obj is None:
        return None
    name = type(obj).__name__
    if name in ("FallbackSTT", "FallbackLLM"):
        return (name, shape(obj.first), shape(obj.second))
    if name == "GpuSTT":
        return (name, shape(obj.backup))
    if name == "GuardedVoice":
        return (name, shape(obj.main), shape(obj.second))
    if name == "GpuStudioTTS":
        return (name, shape(obj.gpu), shape(obj.stt), shape(obj.backup))
    return name


SETUPS = {
    "nothing configured": {},
    "hosted only": {"gnani_api_key": SecretStr("k"), "llm_base_url": "http://llm", "llm_model": "m"},
    "hosted + voice engine": {"gnani_api_key": SecretStr("k"), "llm_base_url": "http://llm", "llm_model": "m",
                              "gpu_voice_url": "http://v1,http://v2"},
    "everything": {"gnani_api_key": SecretStr("k"), "llm_base_url": "http://llm", "llm_model": "m",
                   "gpu_voice_url": "http://v1", "gpu_stt_url": "http://stt", "gpu_llm_url": "http://gemma/v1",
                   "gpu_separate_url": "http://sep"},
    "gpu machine without hosted keys": {"gpu_voice_url": "http://v1", "gpu_stt_url": "http://stt",
                                        "gpu_llm_url": "http://gemma/v1"},
}


@pytest.fixture
def setup(monkeypatch):
    def use(values: dict) -> None:
        s = get_settings()
        for k in {k for v in SETUPS.values() for k in v}:
            monkeypatch.setattr(s, k, SecretStr("") if k == "gnani_api_key" else "")
        for k, v in values.items():
            monkeypatch.setattr(s, k, v)
        for f in (providers._stt, providers._tts, providers._gpu_voice, providers._llm):
            f.cache_clear()
    yield use
    for f in (providers._stt, providers._tts, providers._gpu_voice, providers._llm):
        f.cache_clear()


@pytest.mark.parametrize("name", list(SETUPS))
@pytest.mark.parametrize("mode", ["live", "studio"])
def test_shipped_file_reproduces_v0(setup, name, mode):
    setup(SETUPS[name])
    r = Router(load_config(BACKEND_DIR / "config" / "routing.yaml"))
    for engine in ("cloud", "gpu"):
        eng = providers.engine_of(engine)   # `gpu` without its servers resolves to `cloud`, in v0 and here
        assert shape(r.stt(mode, eng)) == shape(providers._stt(eng)), (name, engine, "stt")
        assert shape(r.llm(mode, eng)) == shape(providers._llm(eng)), (name, engine, "llm")
        assert shape(r.gpu_voice(mode, eng)) == shape(providers._gpu_voice(eng)), (name, engine, "voice")
        assert shape(r.tts(mode, eng)) == shape(providers._tts(eng)), (name, engine, "tts")
        assert r.gpu_voice(mode, eng).enabled == providers._gpu_voice(eng).enabled


def test_router_is_used_only_when_switched_on(setup, monkeypatch):
    setup(SETUPS["everything"])
    s = get_settings()
    assert providers._router() is None
    assert providers.get_stt("gpu") is providers._stt("gpu")
    monkeypatch.setattr(s, "v1_router", True)
    from app.v1 import router as rt
    rt.get_router.cache_clear()
    assert providers.get_stt("gpu") is rt.get_router().stt("live", "gpu")
    assert shape(providers.get_llm("gpu", mode="studio")) == ("FallbackLLM", "LocalLLM", "OpenAILLM")
    monkeypatch.setattr(s, "mock_providers", True)       # mocks never go through the router
    assert providers._router() is None
    rt.get_router.cache_clear()


def test_unconfigured_providers_are_left_out(setup, monkeypatch):
    setup(SETUPS["everything"])
    r = Router(load_config(BACKEND_DIR / "config" / "routing.yaml"))
    assert r.chain("studio_hq", "cloud", "translate") == ["gemma", "gemini"]       # no big model server yet
    assert r.chain("studio_hq", "cloud", "transcribe") == ["prisma", "whisper_gpu"]
    assert r.chain("studio_hq", "cloud", "score") == ["prisma"]
    assert r.chain("studio_hq", "cloud", "diarize") == ["none"]
    s = get_settings()
    monkeypatch.setattr(s, "v1_big_llm_url", "http://big/v1")
    monkeypatch.setattr(s, "v1_qa_url", "http://qa")
    monkeypatch.setattr(s, "v1_transcribe_url", "http://tr")
    assert r.chain("studio_hq", "gpu", "translate") == ["big_llm", "gemma", "gemini"]
    assert r.chain("studio_hq", "gpu", "score") == ["qa_server", "prisma"]
    assert r.chain("studio_hq", "gpu", "transcribe") == ["prisma", "indic_transcribe", "whisper_gpu"]
    assert shape(r.llm("studio_hq", "gpu")) == ("FallbackLLM", "LocalLLM", ("FallbackLLM", "LocalLLM", "OpenAILLM"))
    assert "indic_transcribe" not in str(shape(r.stt("live", "gpu")))    # never in a live chain: it does not stream


def test_voice_server_flag_swaps_the_copied_voice(setup, monkeypatch):
    setup(SETUPS["everything"])
    s = get_settings()
    monkeypatch.setattr(s, "v1_tts_server_url", "http://tts41")
    r = Router(load_config(BACKEND_DIR / "config" / "routing.yaml"))
    assert r.chain("live", "gpu", "copied_voice") == ["indicf5"]           # flag off: the three engines, as v0
    monkeypatch.setattr(s, "v1_tts_server", True)
    assert r.chain("live", "gpu", "copied_voice") == ["indicf5_v1"]
    assert shape(r.gpu_voice("live", "gpu")) == ("GuardedVoice", "IndicF5V1Voice", None)
    assert r.gpu_voice("live", "gpu").urls == ["http://tts41"]


def test_bad_files_are_refused():
    for cfg in ({}, {"modes": {"radio": {}}}, {"modes": {"live": {"cloud": {"translate": ["gpt"]}}}},
                {"modes": {"live": {"cloud": {"translate": []}}}}, {"modes": {"live": {"mars": {}}}},
                {"modes": {"live": {"cloud": {"dance": ["prisma"]}}}},
                {"modes": {"live": {}}, "timeouts_s": {"translate": 0}}):
        with pytest.raises(RoutingError):
            validate(cfg)


class FakeRouter:
    """Three named providers for one step; `fail` and `slow` decide how each behaves."""

    def __init__(self, names, fail=(), slow=()):
        self._names, self._fail, self._slow, self.calls = list(names), set(fail), set(slow), []
        self.s = get_settings()

    def chain(self, mode, engine, stage):
        return list(self._names)

    def timeout(self, stage):
        return 0.05

    def provider(self, kind, name):
        outer = self

        class P:
            async def translate_batch(self, lines, target, glossary):
                outer.calls.append(name)
                if name in outer._slow:
                    await asyncio.sleep(1)
                if name in outer._fail:
                    raise ProviderError(f"{name} is down")
                return [f"{name}:{x}" for x in lines]

            async def synth(self, text, lang, voice, **kw):
                outer.calls.append(name)
                if name in outer._fail:
                    raise ProviderError(f"{name} is down")
                return name.encode()
        return P()


async def test_fallback_on_error_and_timeout_with_reason():
    r = FakeRouter(["a", "b", "c"], fail={"a"}, slow={"b"})
    st = Stages("studio_hq", "cloud", router=r)
    out = await asyncio.wait_for(st._run("translate", r.chain("", "", ""), lambda n: r.provider("llm", n).translate_batch(["x"], "ta-IN", [])), 5)
    assert out == ["c:x"] and r.calls == ["a", "b", "c"] and st.used["translate"] == "c"
    assert [f["provider"] for f in st.fallbacks] == ["a", "b"]
    assert "a is down" in st.fallbacks[0]["reason"] and "timed out" in st.fallbacks[1]["reason"]
    assert st.fallbacks[0]["next"] == "b" and st.fallbacks[1]["next"] == "c"


async def test_all_fail_raises_with_every_reason():
    r = FakeRouter(["a", "b"], fail={"a", "b"})
    st = Stages("studio_hq", "cloud", router=r)
    with pytest.raises(StageFailed) as e:
        await st._run("translate", ["a", "b"], lambda n: r.provider("llm", n).translate_batch(["x"], "ta-IN", []))
    assert "a is down" in str(e.value) and "b is down" in str(e.value) and len(e.value.reasons) == 2
    with pytest.raises(StageFailed):
        await st._run("translate", [], lambda n: r.provider("llm", n).translate_batch(["x"], "ta-IN", []))


async def test_voice_stays_with_the_provider_that_spoke_first():
    r = FakeRouter(["timbre", "other"], fail={"timbre"})
    st = Stages("studio_hq", "cloud", router=r)
    st._speaker = lambda name: r.provider("tts", name)          # no real clients in this test
    voice = {"kind": "stock", "voice": "Asmita"}
    assert await st.speak("one", "ta-IN", voice) == b"other"     # the first provider failed, the second spoke
    r._fail.clear()
    r.calls.clear()
    assert await st.speak("two", "ta-IN", voice) == b"other"     # ... and keeps speaking although the first is back
    assert r.calls == ["other"]


async def test_the_first_voice_is_tried_twice_before_another_one_speaks():
    class Flaky(FakeRouter):
        def __init__(self):
            super().__init__(["main", "other"])
            self.left = 1                       # the main voice fails once, then works

        def timeout(self, stage):
            return 5.0                          # room for the second try (the real limit is 20 s)

        def provider(self, kind, name):
            outer = self

            class P:
                async def synth(self, text, lang, voice, **kw):
                    outer.calls.append(name)
                    if name == "main" and outer.left:
                        outer.left -= 1
                        raise ProviderError("dropped request")
                    return name.encode()
            return P()
    r = Flaky()
    st = Stages("studio_hq", "cloud", router=r)
    st._speaker = lambda name: r.provider("tts", name)
    voice = {"kind": "stock", "voice": "Asmita"}
    assert await st.speak("one", "ta-IN", voice) == b"main"       # one dropped request does not hand the job over
    assert r.calls == ["main", "main"] and st.fallbacks == []
    assert await st.speak("two", "ta-IN", voice) == b"main"
