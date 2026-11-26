"""v1.2 Studio: the two guards on the lines of a job, before the voice. Exact (every line) and blocking.

  script   every translated line: letters that are neither Latin nor of the target language's script
           (`guards.script_ok`). A line that fails is translated once more; still wrong: flagged.
  shift    every translated line is judged beside its own source line (`guards.judge`): does it say something
           different (`shift`), is something that matters missing (`lost`). A line that fails is translated once
           more and judged again; passes: the new line is used; fails again: the first line stays and is flagged.

A line the judge could not judge (no judge, a failed call, an unreadable answer) is "not_checked": it is counted
as that, never as passed. A flagged line is still dubbed; the editor shows it as "needs your ear" with the reason.
What the judge is and is not: see `guards.py`.
"""
from collections.abc import Awaitable, Callable
from typing import Any

from app.v1 import guards

BATCH = 20
JUDGE_TIMEOUT_S = 60.0
Retranslate = Callable[[list[int]], Awaitable[list[str]]]


def _fails(v: dict[str, bool]) -> str:
    return ("says something different from its source" if v["shift"] else
            "something that matters in its source is missing" if v["lost"] else "")


async def _judge_all(judge: Any, pairs: list[tuple[str, str]], lang: str) -> list[dict[str, bool] | None]:
    out: list[dict[str, bool] | None] = []
    for i in range(0, len(pairs), BATCH):
        part = pairs[i:i + BATCH]
        got = await guards.judge(judge, part, lang, JUDGE_TIMEOUT_S)
        out += got if got is not None else [None] * len(part)
    return out


async def check(src: list[str], out: list[str], lang: str, *, judge: Any, retranslate: Retranslate,
                script: bool = True, shift: bool = True) -> tuple[list[str], list[dict[str, Any]]]:
    """Returns (the lines to dub, one verdict per line). A verdict: {"script": ok | regenerated | flagged,
    "shift": ok | regenerated | flagged | not_checked, "why": the reason when flagged}; a guard that is off
    leaves its key out."""
    lines = list(out)
    verdicts: list[dict[str, Any]] = [{} for _ in lines]

    async def again(idx: list[int]) -> dict[int, str]:
        if not idx:
            return {}
        try:
            got = await retranslate(idx)
        except Exception:  # noqa: BLE001 - no second answer: the lines are flagged
            return {}
        return {i: (t or "").strip() for i, t in zip(idx, got)} if len(got) == len(idx) else {}

    if script:
        bad = [i for i, line in enumerate(lines) if not guards.script_ok(line, lang)]
        new = await again(bad)
        for i in range(len(lines)):
            verdicts[i]["script"] = "ok"
        for i in bad:
            if new.get(i) and guards.script_ok(new[i], lang):
                lines[i], verdicts[i]["script"] = new[i], "regenerated"
            else:
                verdicts[i]["script"] = "flagged"
                verdicts[i]["why"] = "letters of another script than the language's own"
    if shift:
        first = await _judge_all(judge, list(zip(src, lines)), lang)
        failing = [i for i, v in enumerate(first) if v is not None and _fails(v)]
        new = await again(failing)
        usable = [i for i in failing if new.get(i) and new[i] != lines[i] and (not script or guards.script_ok(new[i], lang))]
        second = dict(zip(usable, await _judge_all(judge, [(src[i], new[i]) for i in usable], lang))) if usable else {}
        for i, v in enumerate(first):
            if v is None:
                verdicts[i]["shift"] = "not_checked"
            elif not _fails(v):
                verdicts[i]["shift"] = "ok"
            elif second.get(i) is not None and not _fails(second[i]):   # type: ignore[arg-type]
                lines[i], verdicts[i]["shift"] = new[i], "regenerated"
            else:
                verdicts[i]["shift"] = "flagged"
                verdicts[i]["why"] = "; ".join(x for x in (verdicts[i].get("why"), _fails(v)) if x)
    return lines, verdicts


def summary(verdicts: list[dict[str, Any]]) -> dict[str, int]:
    """Counts for the job's record and the eval tables. `script_failed` and `shift_failed` include the lines a
    second translation put right."""
    def n(key: str, *values: str) -> int:
        return sum(1 for v in verdicts if v.get(key) in values)
    return {"lines": len(verdicts),
            "script_checked": n("script", "ok", "regenerated", "flagged"),
            "script_failed": n("script", "regenerated", "flagged"), "script_flagged": n("script", "flagged"),
            "shift_checked": n("shift", "ok", "regenerated", "flagged"), "shift_not_checked": n("shift", "not_checked"),
            "shift_failed": n("shift", "regenerated", "flagged"), "shift_flagged": n("shift", "flagged")}


def flag_fields(v: dict[str, Any]) -> dict[str, Any]:
    """What a translation row gets from its verdict."""
    why = str(v.get("why") or "")
    return {"guard": {k: v[k] for k in ("script", "shift", "why") if k in v}, "flagged": bool(why),
            "flag_reason": f"guard: {why}" if why else ""}
