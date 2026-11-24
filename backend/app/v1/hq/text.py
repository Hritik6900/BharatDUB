"""Studio HQ, phase B: the text work, done by the translation model chain of the `studio_hq` mode.

Every step takes the lines of the whole video at once (the model sees the full transcript, so names and tone stay
the same from line to line) and must return a JSON array of the same length. A step whose answer cannot be used
(bad JSON, wrong count, a wrong script) leaves the lines as they were: a failed polish never loses a line.

  merge_hearings   two transcripts of the same clip that differ -> the more plausible one, word by word
  cleanup          names as in the glossary, punctuation, fillers and stammered repeats removed
  translate_timed  translation with a word limit per line, from the line's time slot and the voice's pace
  review           the same model as a reviewer: meaning, names, naturalness, length; fixes what is wrong
  normalise        numbers, dates, symbols and short forms written as the words to be spoken
"""
import json
import re
from typing import Any

from app.config import LANG_NAMES
from app.providers.llm_local import SPELLED, has_latin
from app.providers.llm_openai import SCRIPTS, parse_json_array, wrong_script
from app.v1.stages import Stages

PROMPT_VERSION = "hq-1"
# What a voice cannot read as written: digits, currency and maths signs, a few symbols.
UNSPOKEN = re.compile(r"[0-9०-९০-৯੦-੯૦-૯௦-௯౦-౯೦-೯൦-൯%₹$€£@&+=/#]")


async def _array(st: Stages, system: str, items: list[Any], *, stage: str = "translate", n: int | None = None,
                 max_tokens: int = 4000) -> list[str] | None:
    """Ask for a JSON array of `n` strings. None when two tries give nothing usable."""
    n = len(items) if n is None else n
    user = json.dumps(items, ensure_ascii=False)
    for _ in range(2):
        try:
            out = parse_json_array(await st.chat(system, user, stage=stage, max_tokens=max_tokens, temperature=0.2))
        except ValueError:
            continue
        if len(out) == n:
            return out
    return None


def script_rule(target: str, native: bool, glossary: list[str]) -> str:
    script = SCRIPTS.get(target)
    if not script:
        return "Write natural spoken English in Latin letters. Leave no Hindi words."
    if native:   # our voice engine reads only the language's own letters
        return (f"Write every word in {script} letters, English words and names too, spelled the way they sound "
                f"(game, chat -> {SPELLED.get(target, '')}). No Latin letters; numbers as words.")
    keep = ", ".join(glossary) or "none"
    return f"Write in {script} letters, never romanised. Only these words stay in English letters: {keep}."


def acceptable(text: str, target: str, native: bool) -> bool:
    return bool(text.strip()) and not wrong_script(text, target) and not (native and target in SCRIPTS and has_latin(text))


async def merge_hearings(st: Stages, hearings: list[dict[str, str]], primary: list[str], glossary: list[str]) -> list[str]:
    """`hearings[i]`: provider -> transcript of clip i. Where they agree nothing is asked; where they differ the
    model picks, word by word, what was most likely said, with the lines around it and the glossary as context."""
    from app.v1.phrase import same_words
    differ = [i for i, h in enumerate(hearings)
              if len({t for t in h.values() if t}) > 1 and not all(same_words(t, primary[i]) for t in h.values() if t)]
    if not differ:
        return primary
    items = [{"i": i, "before": primary[i - 1] if i else "", "heard": [t for t in hearings[i].values() if t],
              "after": primary[i + 1] if i + 1 < len(primary) else ""} for i in differ]
    system = ("Each item is one line of a Hindi or Hinglish video heard by several speech recognisers (`heard`), with "
              "the line before and after it. The recognisers disagree. For each item write the line as it was most "
              "likely spoken: choose word by word between the versions, never invent words that none of them heard, "
              f"keep the script of the first version. Known names and terms: {', '.join(glossary) or 'none'}. "
              "Return ONLY a JSON array of strings, one per item, in order.")
    out = await _array(st, system, items)
    if out is None:
        return primary
    merged = list(primary)
    for i, text in zip(differ, out):
        if text.strip():
            merged[i] = text.strip()
    return merged


async def cleanup(st: Stages, lines: list[str], glossary: list[str]) -> list[str]:
    system = ("These are the lines of one video's transcript (Hindi or Hinglish), in order. Clean each line for "
              "dubbing: fix punctuation, spell names and terms as in this list when they are meant: "
              f"{', '.join(glossary) or 'none'}; remove filler sounds and stammered repeats (um, matlab matlab). "
              "Do not translate, do not merge or split lines, do not change the meaning or the script, do not add "
              "anything. A line that is fine stays as it is. Return ONLY a JSON array of strings, same length and order.")
    out = await _array(st, system, lines)
    if out is None:
        return lines
    # A cleaned line may lose fillers, never most of its words: then the original stays.
    return [c.strip() if c.strip() and len(c.split()) >= max(1, len(o.split()) // 2) else o for o, c in zip(lines, out)]


def word_limit(slot_s: float, speech_s: float, src_words: int, pace_ms: float, share: float = 1.0) -> int:
    """Words of the target language that fit a line's time: its slot (to the next line), but not more than a
    quarter over the time the speaker took, at the dubbing voice's pace."""
    room = min(slot_s, speech_s * 1.25) if speech_s > 0 else slot_s
    return max(2, int(room * 1000 * share / max(200.0, pace_ms)))


async def translate_timed(st: Stages, lines: list[str], limits: list[int], target: str, glossary: list[str],
                          native: bool, terms: list[str] | None = None) -> list[str] | None:
    lang = LANG_NAMES.get(target, target)
    items = [{"line": t, "max_words": m} for t, m in zip(lines, limits)]
    system = (f"You dub an Indian video into {lang}. The items are its lines in order, each with `max_words`: how many "
              f"{lang} words fit the time that line has. Translate every line into natural spoken {lang}, the way a "
              "creator talks on camera, keeping the tone and the same words for the same things across lines. Use at "
              "most `max_words` words; when the full meaning does not fit, keep the main point. "
              + script_rule(target, native, glossary)
              + (f" Names and terms of this video (keep every one that a line has, and write each the same way "
                 f"every time): {', '.join(terms)}." if terms else "") +
              " Return ONLY a JSON array of strings, same length and order.")
    out = await _array(st, system, items)
    if out is None:
        return None
    return [t.strip() for t in out]


async def review(st: Stages, src: list[str], out: list[str], limits: list[int], target: str, glossary: list[str],
                 native: bool) -> tuple[list[str], int]:
    """A second look by the review chain. Returns the lines and how many it changed."""
    lang = LANG_NAMES.get(target, target)
    items = [{"source": s, "dub": o, "max_words": m} for s, o, m in zip(src, out, limits)]
    system = (f"You review the {lang} dub of an Indian video. Each item has the `source` line, its `dub` and `max_words`. "
              "For each item check: is the meaning right, are names and numbers right, does it sound like natural "
              f"spoken {lang}, is it within `max_words`? Return the dub line unchanged when it is fine, or a corrected "
              "line when it is not. " + script_rule(target, native, glossary) +
              " Return ONLY a JSON array of strings (the final dub lines), same length and order.")
    got = await _array(st, system, items, stage="review")
    if got is None:
        return out, 0
    final, changed = [], 0
    for old, new, limit in zip(out, got, limits):
        new = new.strip()
        ok = acceptable(new, target, native) and len(new.split()) <= max(limit + 2, int(limit * 1.3))
        if ok and new != old:
            changed += 1
        final.append(new if ok else old)
    return final, changed


async def normalise(st: Stages, lines: list[str], target: str, native: bool) -> tuple[list[str], int]:
    """Lines with digits or symbols are rewritten with those spoken out. Returns the lines and how many changed."""
    todo = [i for i, t in enumerate(lines) if UNSPOKEN.search(t)]
    if not todo:
        return lines, 0
    lang = LANG_NAMES.get(target, target)
    system = (f"These {lang} lines will be read aloud by a voice that cannot read digits or symbols. Rewrite each line "
              f"with every number, date, time, amount, percentage and symbol written as {lang} words the way a person "
              "says them (9:30 as half past nine, 2.5 lakh as two and a half lakh). Change nothing else. "
              + script_rule(target, native, []) + " Return ONLY a JSON array of strings, same length and order.")
    got = await _array(st, system, [lines[i] for i in todo])
    if got is None:
        return lines, 0
    out, changed = list(lines), 0
    for i, new in zip(todo, got):
        new = new.strip()
        if new and not UNSPOKEN.search(new) and acceptable(new, target, native):
            out[i], changed = new, changed + 1
    return out, changed
