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
                    max_tokens: int | None = None, timeout: float | None = None,
                    effort: str | None = None) -> str:
        if not (self.s.llm_base_url and self.s.llm_model):
            raise ProviderError("LLM_BASE_URL / LLM_MODEL are not set")
        body: dict[str, Any] = {"model": model or self.s.llm_model, "temperature": temperature,
                                "messages": [{"role": "system", "content": system},
                                             {"role": "user", "content": user}]}
        if max_tokens:
            body["max_tokens"] = max_tokens
        if effort or self.s.llm_reasoning_effort:
            body["reasoning_effort"] = effort or self.s.llm_reasoning_effort
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

    async def translate_chunk(self, text: str, target: str, glossary: list[str], context: list[str],
                              brief: bool = False, native: bool = False, max_words: int | None = None) -> str:
        """`brief`: the dub is behind the speaker, so condense like an interpreter would (main point only)."""
        lang = LANG_NAMES.get(target, target)
        system = (
            f"You are a live interpreter for an Indian streamer. Translate the CURRENT line into natural spoken {lang}, "
            "the way a streamer talks, short and punchy. It is spoken aloud in real time, so it must take no longer to say "
            "than the original: keep every point, drop filler words and repetition. "
            + script_rule(target) +
            f"Keep these words in English exactly: {', '.join(glossary) or 'none'}. Keep brand and game names in English. "
            "The speaker is still talking: CURRENT may be only a piece of a sentence, without punctuation. Translate just "
            "that piece so it carries on from the previous lines; never finish the sentence yourself, repeat what came before, or add words the speaker did not say. "
            "Use the previous lines only for context; do not translate them. Reply with the translation only."
        )
        user = ""
        if context:
            user += "Previous lines:\n" + "\n".join(context[-3:]) + "\n\n"
        user += f"CURRENT: {text}"
        system += (f" CURRENT has {len(text.split())} words: your {lang} must not take longer to say than that, "
                   "so prefer the shortest natural wording and do not add address words like bro.")
        if native and target in SCRIPTS:
            # Our GPU voice reads only the language's own letters (measured: "green chicken" in Latin letters came
            # out as noise, in Tamil letters word for word). This overrides the rule about English letters.
            system += (f" IMPORTANT, this overrides the earlier rule: write EVERY word in {SCRIPTS[target]} letters, "
                       "including English words, brand and game names, spelled the way they are pronounced. "
                       "No Latin letters at all; write numbers as words.")
        # `max_words`: how many words of this language fit the time the speaker took (from the measured pace of
        # the dubbing voice). Without it a dub that is behind is cut to about 60% of the words.
        if brief:
            system += (" The dub is running behind the speaker, so condense: say only the main point, in at most "
                       f"{max_words or max(3, round(len(text.split()) * 0.6))} words, and leave out everything else.")
        elif max_words:
            system += (f" Time limit: the speaker took the time of about {max_words} {lang} words. Use at most "
                       f"{max_words} words; if the full meaning does not fit, keep the main point.")
        fast = bool(self.s.llm_model_fast) and self.s.llm_model_fast != self.s.llm_model
        out = clean_line(await self._chat(system, user, model=self.s.llm_fast, max_tokens=400, timeout=20.0,
                                          effort=(self.s.llm_reasoning_effort_fast or None) if fast else None))
        if wrong_script(out, target):
            # About 1 reply in 20 carries a word in the wrong script (measured, scripts/live_llm_bench.py): the
            # voice would misread it. The main model gets that line once more, with the rule spelled out.
            only = f" Write every word in {SCRIPTS[target]} letters (English words in Latin letters); no other script."\
                if target in SCRIPTS else " Write in English only, in Latin letters."
            again = clean_line(await self._chat(system + only, user, max_tokens=400, timeout=20.0))
            if not wrong_script(again, target):
                out = again
        return out

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


# Unicode blocks of the scripts we write (first, last code point).
SCRIPT_RANGES = {
    "Devanagari": (0x0900, 0x097F), "Bengali": (0x0980, 0x09FF), "Gurmukhi": (0x0A00, 0x0A7F),
    "Gujarati": (0x0A80, 0x0AFF), "Tamil": (0x0B80, 0x0BFF), "Telugu": (0x0C00, 0x0C7F),
    "Kannada": (0x0C80, 0x0CFF), "Malayalam": (0x0D00, 0x0D7F),
}


def wrong_script(out: str, target: str) -> bool:
    """True when a reply has letters that are neither Latin nor in the target language's script.

    Small models sometimes leave a Hindi word in Devanagari inside a Tamil line, or slip in a word in a
    third script; the voice then reads it wrongly or skips it. An empty reply counts as wrong too.
    """
    if not out.strip():
        return True
    lo, hi = SCRIPT_RANGES.get(SCRIPTS.get(target, ""), (0, -1))
    for ch in out:
        cp = ord(ch)
        if cp < 0x0250 or lo <= cp <= hi:      # ASCII, Latin-1 and Latin Extended; or the target script
            continue
        if 0x2000 <= cp <= 0x206F or cp in (0x0964, 0x0965, 0x200C, 0x200D):  # punctuation, danda, joiners
            continue
        if ch.isalpha() or 0x0900 <= cp <= 0x0D7F:
            return True
    return False


def looks_untranslated(out: str, src: str, target: str) -> bool:
    """Kept for callers and tests: a reply that still carries the source script, or any other wrong script."""
    return wrong_script(out, target)


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
