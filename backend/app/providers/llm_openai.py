"""OpenAI-compatible chat LLM (hosted Evon, or a backup). See SPEC.md section 7 for prompt rules."""
import asyncio
import json
import re
import time
from typing import Any

import httpx

from app.config import LANG_NAMES, Settings, get_settings
from app.providers.base import ProviderError
from app.providers.http import request_with_retry

SCRIPTS = {
    "hi-IN": "Devanagari", "mr-IN": "Devanagari", "ta-IN": "Tamil", "bn-IN": "Bengali", "te-IN": "Telugu",
    "kn-IN": "Kannada", "ml-IN": "Malayalam", "gu-IN": "Gujarati", "pa-IN": "Gurmukhi",
}


def script_rule(target: str) -> str:
    """Hinglish input in Latin letters tempts models to answer in romanised Tamil/Bengali; the voice needs native script."""
    script = SCRIPTS.get(target)
    if not script:
        return "The source may be Hindi or Hinglish in any script; translate all of it. "
    return (f"Write in {script} script, never romanised; only the kept English words stay in Latin letters. "
            "The source may be Hindi or Hinglish in any script; translate all of it and leave no Hindi words. ")


THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class OpenAILLM:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.s = settings or get_settings()
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        self.last_latency_s: float | None = None

    async def _chat(self, system: str, user: str, *, model: str | None = None, temperature: float = 0.3,
                    max_tokens: int | None = None, timeout: float | None = None) -> str:
        if not (self.s.llm_base_url and self.s.llm_model):
            raise ProviderError("LLM_BASE_URL / LLM_MODEL are not set")
        body: dict[str, Any] = {"model": model or self.s.llm_model, "temperature": temperature,
                                "messages": [{"role": "system", "content": system},
                                             {"role": "user", "content": user}]}
        if max_tokens:
            body["max_tokens"] = max_tokens
        if self.s.llm_reasoning_effort:
            body["reasoning_effort"] = self.s.llm_reasoning_effort
        headers = {"Authorization": f"Bearer {self.s.llm_api_key.get_secret_value()}"}
        url = f"{self.s.llm_base_url.rstrip('/')}/chat/completions"

        async def send() -> httpx.Response:
            return await self._client.post(url, headers=headers, json=body, timeout=timeout)

        t0 = time.perf_counter()
        resp = await request_with_retry(send, what="llm.chat")
        self.last_latency_s = time.perf_counter() - t0
        try:
            content = resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"llm.chat: unexpected response shape {resp.text[:200]}") from e
        return strip_thinking(content)

    async def translate_batch(self, lines: list[str], target: str, glossary: list[str]) -> list[str]:
        if not lines:
            return []
        system = batch_system_prompt(target, glossary)
        user = json.dumps(lines, ensure_ascii=False)
        for _ in range(2):  # first try + one retry on count mismatch / bad JSON
            try:
                out = parse_json_array(await self._chat(system, user))
            except ValueError:
                continue
            if len(out) == len(lines):
                return out
        # Fallback: per-line calls (same order).
        return list(await asyncio.gather(*(self.translate_chunk(line, target, glossary, []) for line in lines)))

    async def translate_chunk(self, text: str, target: str, glossary: list[str], context: list[str]) -> str:
        lang = LANG_NAMES.get(target, target)
        system = (
            f"You are a live interpreter for an Indian streamer. Translate the CURRENT line into natural spoken {lang}, "
            "the way a streamer talks, short and punchy. It is spoken aloud in real time, so it must take no longer to say "
            "than the original: keep every point, drop filler words and repetition. "
            + script_rule(target) +
            f"Keep these words in English exactly: {', '.join(glossary) or 'none'}. Keep brand and game names in English. "
            "Use the previous lines only for context; do not translate them. Reply with the translation only."
        )
        user = ""
        if context:
            user += "Previous lines:\n" + "\n".join(context[-3:]) + "\n\n"
        user += f"CURRENT: {text}"
        out = await self._chat(system, user, model=self.s.llm_fast, max_tokens=400, timeout=20.0)
        return clean_line(out)

    async def shorten(self, text: str, target: str, max_seconds: float) -> str:
        lang = LANG_NAMES.get(target, target)
        system = (
            f"Rewrite this {lang} line so it can be spoken naturally in at most {max_seconds:.1f} seconds. "
            "Keep the meaning, the tone and any English words. " + script_rule(target) + "Reply with the rewritten line only."
        )
        return clean_line(await self._chat(system, text, max_tokens=300))


def batch_system_prompt(target: str, glossary: list[str]) -> str:
    lang = LANG_NAMES.get(target, target)
    return (
        f"You dub short Indian social-media videos. Translate each line into natural, spoken {lang}, "
        "the way a creator talks on camera, not textbook style. "
        + script_rule(target) +
        f"Keep these words in English as-is: {', '.join(glossary) or 'none'}. Keep brand names in English. "
        "Keep each line about the same spoken length as the source so it fits the same time slot. "
        "Return ONLY a JSON array of strings, same length and order as the input. No commentary."
    )


def strip_thinking(text: str) -> str:
    text = THINK_RE.sub("", text)
    if "</think>" in text:  # unopened think block
        text = text.split("</think>", 1)[1]
    return text.strip()


def parse_json_array(text: str) -> list[str]:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("no JSON array in LLM output")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("LLM output is not a list")
    return [str(x).strip() for x in data]


def clean_line(text: str) -> str:
    text = text.strip().strip('"').strip()
    for prefix in ("CURRENT:", "Translation:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text
