"""Provider factory. Pipelines get providers from here so tests and mock mode can swap them.

Two engines, chosen per Live session or Studio job (`engine`):
  cloud  the hosted services, exactly as before (the default)
  gpu    speech-to-text and translation on our own GPU machine beside the voice engines, with the hosted ones
         behind them as the fallback (SPEC.md section 21)
`AI_MODE` only sets which one a caller gets when it does not say. An engine that is asked for but not set up
(`gpu` without `GPU_STT_URL` / `GPU_LLM_URL`, or in mock mode) resolves to `cloud`.
"""
from functools import lru_cache
from typing import Any

from app.config import get_settings


def engine_of(engine: str | None = None) -> str:
    s = get_settings()
    want = engine or s.ai_mode
    return "gpu" if want == "gpu" and s.gpu_mode_ready and not s.mock_providers else "cloud"


def _router() -> Any:
    """v1: the config-driven router when `V1_ROUTER` is on, else None and the fixed table below is used."""
    if not get_settings().v1_router:
        return None
    from app.v1.router import active
    return active()


def get_stt(engine: str | None = None, mode: str = "live") -> Any:
    r = _router()
    return r.stt(mode, engine_of(engine)) if r else _stt(engine_of(engine))


def get_tts(engine: str | None = None, mode: str = "live") -> Any:
    r = _router()
    return r.tts(mode, engine_of(engine)) if r else _tts(engine_of(engine))


def get_gpu_voice(engine: str | None = None, mode: str = "live") -> Any:
    r = _router()
    return r.gpu_voice(mode, engine_of(engine)) if r else _gpu_voice(engine_of(engine))


def get_llm(engine: str | None = None, mode: str = "live") -> Any:
    r = _router()
    return r.llm(mode, engine_of(engine)) if r else _llm(engine_of(engine))


@lru_cache
def _stt(engine: str) -> Any:
    if get_settings().mock_providers:
        from app.providers.mock import MockSTT
        return MockSTT()
    from app.providers.stt_gnani import GnaniSTT
    s = get_settings()
    if engine == "gpu":
        from app.providers.stt_gpu import GpuSTT
        hosted = GnaniSTT() if s.gnani_api_key.get_secret_value() else None
        if hosted is not None and s.gpu_stt_first == "hosted":
            from app.providers.fallback import FallbackSTT
            return FallbackSTT(hosted, GpuSTT(s, backup=None))   # the hosted service hears better; ours is behind it
        return GpuSTT(s, backup=hosted)
    return GnaniSTT()


@lru_cache
def _tts(engine: str) -> Any:
    if get_settings().mock_providers:
        from app.providers.mock import MockTTS
        return MockTTS(get_settings().tts_sample_rate)
    from app.providers.tts_gnani import GnaniTTS
    s = get_settings()
    if engine == "gpu" and (s.gpu_voice_url or (s.gpu_voice_model == "mio" and s.gpu_mio_url)):
        from app.providers.tts_gpu_studio import GpuStudioTTS
        return GpuStudioTTS(_gpu_voice("gpu"), _stt("gpu"), s,
                            backup=GnaniTTS() if s.gnani_api_key.get_secret_value() else None)
    return GnaniTTS()


@lru_cache
def _gpu_voice(engine: str) -> Any:
    """The voice engines are the same machines for both; each engine has its own client, because only the GPU
    speech-to-text writes Hindi in Latin letters and needs the sample's text rewritten in Devanagari."""
    from app.providers.tts_gpu import GpuVoice
    s = get_settings()
    if engine == "gpu" and s.gpu_voice_model == "mio" and s.gpu_mio_url and not s.mock_providers:
        from app.providers.tts_gpu_mio import MioVoice
        return MioVoice(s)      # takes the speaker from the sound alone: no sample text to rewrite
    gpu = GpuVoice(s.model_copy(update={"gpu_voice_url": ""}) if s.mock_providers else s)
    if engine == "gpu":
        gpu.ref_text_fix = _local_llm().to_devanagari
        if s.gpu_voice_guard and gpu.enabled:
            from app.providers.tts_gpu_guard import GuardedVoice
            from app.providers.tts_gpu_mio import MioVoice
            return GuardedVoice(gpu, MioVoice(s) if s.gpu_mio_url else None, s)
    return gpu


def _local_llm() -> Any:
    from pydantic import SecretStr

    from app.providers.llm_local import LocalLLM
    s = get_settings()
    return LocalLLM(s.model_copy(update={
        "llm_base_url": s.gpu_llm_url, "llm_model": s.gpu_llm_model, "llm_model_fast": "",
        "llm_api_key": SecretStr("local"), "llm_reasoning_effort": "", "llm_reasoning_effort_fast": ""}))


@lru_cache
def _llm(engine: str) -> Any:
    if get_settings().mock_providers:
        from app.providers.mock import MockLLM
        return MockLLM()
    from app.providers.llm_openai import OpenAILLM
    s = get_settings()
    if engine == "gpu":
        from app.providers.fallback import FallbackLLM
        return FallbackLLM(_local_llm(), OpenAILLM() if s.llm_base_url and s.llm_model else None)
    return OpenAILLM()
