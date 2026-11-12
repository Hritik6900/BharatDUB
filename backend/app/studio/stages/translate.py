"""Stage 6: batch translation per target language, cached by (lines, target, glossary, model)."""
from app.providers.base import LLM
from app.shared import audio_utils as au
from app.shared import cache

PROMPT_VERSION = 1


async def translate(llm: LLM, lines: list[str], target: str, glossary: list[str], model: str,
                    usage: dict) -> list[str]:
    key = au.cache_key(lines, target, sorted(glossary), model, PROMPT_VERSION)
    hit = cache.get_json("translate", key)
    if hit is not None and len(hit) == len(lines):
        return hit
    out = await llm.translate_batch(lines, target, glossary)
    usage["llm_calls"] = usage.get("llm_calls", 0) + 1
    cache.put_json("translate", key, out)
    return out
