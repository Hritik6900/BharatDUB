"""v1.2 guards on every dubbed line: the script it is written in, and whether it still says what its source says.

  script guard    `script_ok`: every letter is Latin or of the target language's script (`wrong_script`, the rule
                  the translators already use). Checked on EVERY translated line, Live and Studio, and on a
                  transcript when the session or job names its source language. It sees letters, not words: a
                  Hindi word written in Tamil letters passes.
  content shift   a judge (a language model, through `providers/`) reads a dub line beside its own source line
                  and says whether it says something different (`shift`) and whether something that matters is
                  missing (`lost`). Studio: every line, before the voice; a line that fails is translated once
                  more and judged again, and flagged if it fails again. Live: a SAMPLE of lines, after they were
                  spoken (a phrase is never held up for it): counted and logged, nothing is regenerated.
                  The judge is a model: it can be wrong both ways, and where the judge is the model that wrote the
                  line it is a weak check. A line it could not judge is counted as not checked, never as passed.

Nothing here does I/O but `judge`, which calls the provider it is given.
"""
import asyncio
import json
import logging
from typing import Any

from app.config import LANG_NAMES
from app.providers.llm_openai import SCRIPTS, strip_thinking, wrong_script

log = logging.getLogger("bharatdub.guards")


def script_ok(text: str, lang: str) -> bool:
    return not wrong_script(text, lang)


def transcript_script_ok(text: str, src_lang: str | None) -> bool | None:
    """A transcript line against the script of the language it was said to be in. None = no script is expected
    (the source language is not pinned, or is written in Latin letters)."""
    if not src_lang or src_lang not in SCRIPTS:
        return None
    return not wrong_script(text, src_lang)


def judge_system(target: str) -> str:
    lang = LANG_NAMES.get(target, target)
    return (
        f"You check lines of a {lang} dub against the lines they were made from. Each item has `source` (what the "
        f"speaker said, Hindi or Hinglish in any script) and `dub` (the {lang} line that is spoken for it). "
        "Answer two questions per item.\n"
        "shift: does the dub say something DIFFERENT from its source? A different statement, a question turned "
        "into a statement, a wrong number, a wrong name, who does what changed, the content of another line, or "
        "something the source does not say. A dub that is simply the source left untranslated is a shift too.\n"
        "lost: is something that MATTERS in the source missing from the dub? A point, a number, a name, a "
        "condition. Dropped filler words, repetitions and address words, a shorter wording, and a sentence that "
        "is cut off because the source is cut off are NOT a loss.\n"
        'Return ONLY a JSON array with one object per item, in order: {"shift": true|false, "lost": true|false}.')


def judge_user(pairs: list[tuple[str, str]]) -> str:
    return json.dumps([{"source": s, "dub": d} for s, d in pairs], ensure_ascii=False)


def parse_verdicts(text: str, n: int) -> list[dict[str, bool]] | None:
    """The judge's answer as n verdicts, or None when it cannot be used."""
    text = strip_thinking(text or "")
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    if not isinstance(data, list) or len(data) != n or not all(isinstance(x, dict) for x in data):
        return None
    return [{"shift": x.get("shift") is True, "lost": x.get("lost") is True} for x in data]


async def judge(llm: Any, pairs: list[tuple[str, str]], target: str, timeout: float = 20.0) -> list[dict[str, bool]] | None:
    """Verdicts for (source, dub) pairs from the provider's `judge_lines`, or None: no such provider, a failed
    call, an answer that cannot be read. Never raises (but for a cancellation)."""
    ask = getattr(llm, "judge_lines", None)
    if ask is None or not pairs:
        return None
    try:
        got = await asyncio.wait_for(ask(pairs, target), timeout)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 - no verdict
        log.info("judge: no verdict (%s: %s)", type(e).__name__, str(e)[:120])
        return None
    if not isinstance(got, list) or len(got) != len(pairs):
        return None
    return got
