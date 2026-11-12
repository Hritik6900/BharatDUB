"""Provider factory. Pipelines get providers from here so tests can swap them."""
from functools import lru_cache

from app.providers.llm_openai import OpenAILLM
from app.providers.stt_gnani import GnaniSTT
from app.providers.tts_gnani import GnaniTTS


@lru_cache
def get_stt() -> GnaniSTT:
    return GnaniSTT()


@lru_cache
def get_tts() -> GnaniTTS:
    return GnaniTTS()


@lru_cache
def get_llm() -> OpenAILLM:
    return OpenAILLM()
