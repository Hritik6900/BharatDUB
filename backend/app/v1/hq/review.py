"""Studio HQ: the rubric review (`V1_HQ_REVIEW`; since 26 Nov 2026 part of every HQ job whatever the flag says,
see `required`).

The hosted model (the `gemini` provider of `providers/`; when it is not configured, the `review` list of the
routing file) reads every translated line of a video against a written rubric and may replace a line. It must
name the check that failed. Nothing is changed for a line that passes.

Every edit is logged twice:
  * trace (`<DATA_DIR>/trace`, copied to `logs/`): kind `hq_review_edit` with the job, language, line number,
    the check that failed, words and letters before and after, whether the edit was taken, the model. No text.
  * `<DATA_DIR>/hq_review/<job>.jsonl`: the same with the source line, the line before and after and the
    model's note. This file never leaves the data folder.

The flag also guards the transcript (`keeps_source`): a merged or cleaned line that changed script or lost the
English terms of the first hearing is put back, and the reviewer sees the first hearing beside the cleaned line.
"""
import json
import unicodedata
from datetime import datetime, timezone
from typing import Any

from app.config import LANG_NAMES, get_settings
from app.providers.llm_openai import strip_thinking
from app.v1 import trace
from app.v1.hq import text as hqtext

REASONS = ("meaning", "numbers_names", "register", "length")


def required(settings: Any) -> bool:
    """Is the review part of an HQ job? Always, when HQ is on: HQ never runs without it, whatever `V1_HQ_REVIEW`
    says (decided 26 Nov 2026). Without the review HQ's merge and clean steps dubbed two of three test videos from
    a damaged transcript (25 of 38 lines no longer the line heard, 0 with it), and heard-back cannot see that.
    Every place that used to read the flag asks here; the flag alone still answers for code outside an HQ job."""
    return bool(settings.v1_studio_hq or settings.v1_hq_review)
RUBRIC = """Check every line against these four rules, in this order. A line passes only when all four hold.

1. MEANING KEPT. The dub says what the source says: nothing added, nothing left out, nothing changed. A statement
   stays a statement, a question a question, an instruction an instruction. Who does what to whom is the same.
2. NUMBERS AND NAMES KEPT. Every number, amount, time, date and unit of the source is in the dub with the same
   value. Every person, place, brand, product, game and subject term of the source is in the dub, and is spelled
   the same way every time it comes up in this video.
3. NATURAL SPOKEN REGISTER. It is how a creator says this aloud in the target language: everyday words, the word
   order of speech, the tone of the source (casual stays casual, respectful stays respectful). Not a written or
   word-for-word translation.
4. FITS THE SLOT. It has at most `max_words` words. A line over the limit is shortened: the main point and every
   number and name stay, filler goes.

Edit only a line that fails a rule, and change only what the rule needs. Do not polish a line that passes."""


def keeps_source(first: str, cleaned: str) -> bool:
    """A cleaned transcript line still is the line that was heard. Seen on real HQ jobs: a Devanagari transcript
    came back in Latin letters, "oxygen ki kami se ..." came out of the merge without "oxygen", and once every
    line of a video came back holding the line before it. Heard-back cannot see any of that: the dub says what
    its text says. So a cleaned line is kept only when
      * every English term of the first hearing (a word of four or more Latin letters) is still there, and
      * the words in the transcript's own script are still there, in that script (one may go when there are four
        or more: a filler; of fewer, three quarters), and
      * it has not lost more than four words in ten.
    A line that fails is put back as it was first heard; a wrong name in it is the reviewer's to correct."""
    if not cleaned.strip():
        return False
    was, now = _words(first), _words(cleaned)
    have = {w.lower()[:4] for w in now}
    terms = [w for w in was if w.isascii() and len(w) >= 4]
    if any(w.lower()[:4] not in have for w in terms):
        return False
    own = [w for w in was if not w.isascii()]
    own_now = {w[:3] for w in now if not w.isascii()}
    gone = sum(1 for w in own if w[:3] not in own_now)
    if gone > (1 if len(own) >= 4 else len(own) // 4):
        return False
    return len(now) >= max(1, int(len(was) * 0.6))


def _words(text: str) -> list[str]:
    """Words of any script, in one spelling of every letter; marks stay with their word."""
    text = unicodedata.normalize("NFC", text)
    return "".join(c if unicodedata.category(c)[0] in "LMN" else " " for c in text).split()


def _parse(text: str, n: int) -> list[dict[str, Any]] | None:
    text = strip_thinking(text)
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    if not isinstance(data, list) or len(data) != n or not all(isinstance(x, dict) for x in data):
        return None
    return data


def system_prompt(target: str, glossary: list[str], native: bool) -> str:
    lang = LANG_NAMES.get(target, target)
    return (f"You are the reviewer of the {lang} dub of an Indian video. The items are its lines in order. Each has "
            "`source` (the transcript line), sometimes `heard` (the same line as the speech recogniser first wrote "
            "it: when the two differ in content, `heard` is what was said), `dub` (the line to review) and "
            "`max_words`.\n\n" + RUBRIC + "\n\n"
            f"Names and terms of this video: {', '.join(glossary) or 'none listed'}.\n"
            + hqtext.script_rule(target, native, glossary) + "\n\n"
            "Return ONLY a JSON array with one object per item, in order: "
            '{"ok": true} for a line that passes, or {"ok": false, "rule": "meaning" | "numbers_names" | "register" | '
            '"length", "text": "<the corrected dub line>", "note": "<what was wrong, in a few words of English>"} '
            "for a line that fails. Name the first rule that fails.")


async def review(st: Any, src: list[str], out: list[str], limits: list[int], target: str, glossary: list[str],
                 native: bool, *, heard: list[str] | None = None, job_id: str = "") -> tuple[list[str], dict[str, Any]]:
    """Returns the lines and what happened: {model, asked, edited, rejected, by_rule}. Lines stay as they were
    when the model's answer cannot be used."""
    items = []
    for i, (s, o, m) in enumerate(zip(src, out, limits)):
        item: dict[str, Any] = {"source": s, "dub": o, "max_words": m}
        if heard and heard[i] and heard[i] != s:
            item["heard"] = heard[i]
        items.append(item)
    names = ["gemini"] if st.r.available("gemini") else (st.names("review") or st.names("translate"))
    system = system_prompt(target, glossary, native)
    user = json.dumps(items, ensure_ascii=False)
    stats: dict[str, Any] = {"model": "", "asked": len(items), "edited": 0, "rejected": 0, "by_rule": {}}

    async def call(name: str) -> list[dict[str, Any]]:
        llm = st.r.provider("llm", name)
        for _ in range(2):
            got = _parse(await llm._chat(system, user, temperature=0.1, max_tokens=6000), len(items))
            if got is not None:
                return got
        raise ValueError("no usable answer")
    try:
        answers = await st._run("review", names, call, timeout=st.r.timeout("review"))
    except Exception as e:  # noqa: BLE001 - a review that cannot be had changes nothing
        stats["error"] = str(e)[:160]
        return out, stats
    stats["model"] = st.used.get("review", "")
    # A line the reviewer failed without writing the corrected line (seen on the first real job: a wrong verb was
    # named and no text came with it) is asked for once more, alone with what was said to be wrong.
    missing = [i for i, ans in enumerate(answers) if ans.get("ok") is False and not str(ans.get("text") or "").strip()]
    if missing:
        ask = [{**items[i], "failed_rule": answers[i].get("rule"), "what_is_wrong": answers[i].get("note")} for i in missing]
        fix_system = (system.split("Return ONLY")[0] + "Each item failed the rule in `failed_rule`; `what_is_wrong` says "
                      "why. Write the corrected dub line for each. Return ONLY a JSON array of strings, one per item, in order.")

        async def again(name: str) -> list[str]:
            from app.providers.llm_openai import parse_json_array
            got = parse_json_array(await st.r.provider("llm", name)._chat(
                fix_system, json.dumps(ask, ensure_ascii=False), temperature=0.1, max_tokens=3000))
            if len(got) != len(ask):
                raise ValueError("wrong count")
            return got
        try:
            for i, text in zip(missing, await st._run("review", [stats["model"] or names[0]], again, timeout=st.r.timeout("review"))):
                answers[i] = {**answers[i], "text": text}
            stats["asked_again"] = len(missing)
        except Exception:  # noqa: BLE001 - those lines stay as they were and are logged as refused
            pass
    final = list(out)
    for i, (old, ans, limit) in enumerate(zip(out, answers, limits)):
        if ans.get("ok") is not False:
            continue
        new = str(ans.get("text") or "").strip()
        rule = ans.get("rule") if ans.get("rule") in REASONS else "other"
        why = ""
        if not new or new == old:
            why = "no new text"
        elif not hqtext.acceptable(new, target, native):
            why = "wrong script"
        elif len(new.split()) > max(limit + 2, int(limit * 1.3)):
            why = "over the word limit"
        taken = not why
        if taken:
            final[i] = new
            stats["edited"] += 1
            stats["by_rule"][rule] = stats["by_rule"].get(rule, 0) + 1
        else:
            stats["rejected"] += 1
        log_edit(job_id, target, i, src[i], old, new, rule, str(ans.get("note") or ""), stats["model"], taken, why)
    return final, stats


def log_edit(job_id: str, lang: str, idx: int, source: str, before: str, after: str, rule: str, note: str,
             model: str, taken: bool, rejected_why: str = "") -> None:
    """Measurements to the trace, the words to the data folder only. Never raises."""
    sizes = {"job": job_id, "lang": lang, "line": idx, "rule": rule, "taken": taken, "model": model,
             "before_words": len(before.split()), "after_words": len(after.split()),
             "before_chars": len(before), "after_chars": len(after), "rejected_why": rejected_why or None}
    if trace.enabled():
        trace.event("hq_review_edit", **sizes)
    try:
        d = get_settings().data_path / "hq_review"
        d.mkdir(parents=True, exist_ok=True)
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **sizes, "source": source,
               "before": before, "after": after, "note": note}
        with open(d / f"{job_id or 'no-job'}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass
