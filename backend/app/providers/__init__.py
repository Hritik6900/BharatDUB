"""Provider factory. Pipelines get providers from here so tests and mock mode can swap them."""
from functools import lru_cache
from typing import Any

from app.config import get_settings


@lru_cache
def get_stt() -> Any:
    if get_settings().mock_providers:
        from app.providers.mock import MockSTT
        return MockSTT()
    from app.providers.stt_gnani import GnaniSTT
    s = get_settings()
    if s.gpu_stt_on:
        from app.providers.stt_gpu import GpuSTT
        return GpuSTT(s, backup=GnaniSTT() if s.gnani_api_key.get_secret_value() else None)
    return GnaniSTT()


@lru_cache
def get_tts() -> Any:
    if get_settings().mock_providers:
        from app.providers.mock import MockTTS
        return MockTTS(get_settings().tts_sample_rate)
    from app.providers.tts_gnani import GnaniTTS
    s = get_settings()
    if s.ai_mode == "gpu" and s.gpu_voice_url:
        from app.providers.tts_gpu_studio import GpuStudioTTS
        return GpuStudioTTS(get_gpu_voice(), get_stt(), s,
                            backup=GnaniTTS() if s.gnani_api_key.get_secret_value() else None)
    return GnaniTTS()


@lru_cache
def get_gpu_voice() -> Any:
    from app.providers.tts_gpu import GpuVoice
    s = get_settings()
    gpu = GpuVoice(s.model_copy(update={"gpu_voice_url": ""}) if s.mock_providers else s)
    if s.gpu_llm_on and s.gpu_stt_on and not s.mock_providers:
        gpu.ref_text_fix = _local_llm().to_devanagari   # the GPU speech-to-text writes Hindi in Latin letters
    return gpu


def _local_llm() -> Any:
    from pydantic import SecretStr

    from app.providers.llm_local import LocalLLM
    s = get_settings()
    return LocalLLM(s.model_copy(update={
        "llm_base_url": s.gpu_llm_url, "llm_model": s.gpu_llm_model, "llm_model_fast": "",
        "llm_api_key": SecretStr("local"), "llm_reasoning_effort": "", "llm_reasoning_effort_fast": ""}))


@lru_cache
def get_llm() -> Any:
    if get_settings().mock_providers:
        from app.providers.mock import MockLLM
        return MockLLM()
    from app.providers.llm_openai import OpenAILLM
    s = get_settings()
    if s.gpu_llm_on:
        from app.providers.fallback import FallbackLLM
        return FallbackLLM(_local_llm(), OpenAILLM() if s.llm_base_url and s.llm_model else None)
    return OpenAILLM()
