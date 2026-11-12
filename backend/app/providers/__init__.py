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
    return GnaniSTT()


@lru_cache
def get_tts() -> Any:
    if get_settings().mock_providers:
        from app.providers.mock import MockTTS
        return MockTTS(get_settings().tts_sample_rate)
    from app.providers.tts_gnani import GnaniTTS
    return GnaniTTS()


@lru_cache
def get_llm() -> Any:
    if get_settings().mock_providers:
        from app.providers.mock import MockLLM
        return MockLLM()
    from app.providers.llm_openai import OpenAILLM
    return OpenAILLM()
