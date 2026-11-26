"""v1.1 Live, dense speech: the dub must not be longer than the time the speaker took.

Measured 24 Nov 2026 on real videos: when the speaker talks 76% of the time instead of 62%, phrases that start
within 0.25 s of their video moment fall from 95% to 76%, and a longer viewer hold does not help. The dubbed line
is longer than its source slot, so every line starts later than the one before. The parts here are free of I/O:

  letters()         the length of a line as the voice sees it (letters, vowel signs and digits; no spaces)
  ExpansionModel    per language and kind of voice: ms of dubbed speech per target letter, per target word and
                    per source word, as a running average over the lines spoken (seeded from stored history).
                    It turns a slot (ms) into a length (words and letters), and a text into an expected duration.
  RateController    a PI controller on the backlog (how far the dub queue is behind the video) that scales the
                    budget of the next phrases (1.0 down to `min_scale`) and lets go again. Since v1.2 it has no
                    switch of its own: it runs only inside the auto budget.
  SpeakingShare     share of the last 30 s the speaker was talking; over 70% is "dense" (until it falls under 60%).
  WordRate          v1.2: source words a second over the last 30 s, the second sign of dense speech.
  AutoGate          v1.2 auto mode: per language, whether the budget applies now (behind, long lines, or dense).
  MeaningRate       v1.2 auto mode: per language, the share of judged lines that lost meaning and the budget
                    steps that follow from it (the judging itself is app/v1/meaning.py).

Where v0 already had a word limit (`live_length_budget`: words = source words x speaker pace x 1.15 / dub pace per
word), `V1_LIVE_BUDGET` replaces it for the phrases it can plan: the slot is the phrase's own measured span, the
aim is 1.0x and not 1.15x, the limit is given in letters as well as words, and the answer is checked.
"""
import json
import math
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SEED_FILE = Path(__file__).resolve().parents[2] / "config" / "live_expansion.json"
KINDS = ("gpu", "clone", "stock")   # our engine's copied voice, the hosted copy, a stock voice


def letters(text: str) -> int:
    """Letters, vowel signs and digits of a line: what the voice has to say, the same measure in every script."""
    return sum(1 for ch in text if unicodedata.category(ch)[0] in "LMN")


@dataclass
class Rate:
    ms_per_char: float
    ms_per_word: float
    ms_per_src_word: float | None = None
    n: int = 0          # lines behind the numbers (seed lines count once the session adds its own)
    seeded: bool = False


class ExpansionModel:
    def __init__(self, seed: dict[str, dict[str, Any]] | None = None, alpha: float = 0.3) -> None:
        self.alpha = alpha
        self.rates: dict[tuple[str, str], Rate] = {}
        for key, r in (seed or {}).items():
            lang, _, kind = key.partition("|")
            if r.get("ms_per_char") and r.get("ms_per_word"):
                self.rates[(lang, kind)] = Rate(float(r["ms_per_char"]), float(r["ms_per_word"]),
                                                float(r["ms_per_src_word"]) if r.get("ms_per_src_word") else None,
                                                0, True)

    @classmethod
    def load(cls, path: Path | None = None, alpha: float = 0.3) -> "ExpansionModel":
        """The model with the stored seed, or an empty one when the file is missing or unreadable."""
        try:
            data = json.loads((path or SEED_FILE).read_text(encoding="utf-8"))
            return cls(data.get("rates") or {}, alpha)
        except (OSError, ValueError):
            return cls(None, alpha)

    def get(self, lang: str, kind: str) -> Rate | None:
        """This language in this kind of voice; failing that, the same language in another voice (a first guess
        that the session's own lines replace quickly)."""
        r = self.rates.get((lang, kind))
        if r is not None:
            return r
        return next((self.rates[(lang, k)] for k in KINDS if (lang, k) in self.rates), None)

    def note(self, lang: str, kind: str, src_words: int, tgt_words: int, tgt_chars: int, natural_ms: float) -> None:
        """One spoken line: `natural_ms` of speech at the voice's own pace (before any squeeze). Lines under four
        words are left out: the engine gives them extra time and they would read as a slow voice."""
        if tgt_words < 4 or tgt_chars < 8 or natural_ms < 300:
            return
        per_char, per_word = natural_ms / tgt_chars, natural_ms / tgt_words
        if not (20 <= per_char <= 400):   # not speech: a swallowed line, or silence
            return
        per_src = natural_ms / src_words if src_words >= 3 else None
        r = self.rates.get((lang, kind))
        if r is None:
            self.rates[(lang, kind)] = Rate(per_char, per_word, per_src, 1)
            return
        # The first lines of a session count for more than the seed: a copied voice has its sample's pace.
        a = max(self.alpha, 1.0 / (r.n + 2))
        r.ms_per_char += a * (per_char - r.ms_per_char)
        r.ms_per_word += a * (per_word - r.ms_per_word)
        if per_src is not None:
            r.ms_per_src_word = per_src if r.ms_per_src_word is None else r.ms_per_src_word + a * (per_src - r.ms_per_src_word)
        r.n += 1

    def estimate_ms(self, lang: str, kind: str, text: str) -> float | None:
        """How long this line takes to say at the voice's own pace."""
        r = self.get(lang, kind)
        return letters(text) * r.ms_per_char if r is not None else None

    def budget(self, lang: str, kind: str, target_ms: float) -> tuple[int, int] | None:
        """(words, letters) that fit `target_ms` of speech, or None when nothing is known of this language."""
        r = self.get(lang, kind)
        if r is None:
            return None
        return max(2, int(target_ms / r.ms_per_word)), max(8, int(target_ms / r.ms_per_char))

    def state(self) -> dict[str, dict[str, Any]]:
        return {f"{lang}|{kind}": {"ms_per_char": round(r.ms_per_char, 1), "ms_per_word": round(r.ms_per_word, 1),
                                   "ms_per_src_word": round(r.ms_per_src_word, 1) if r.ms_per_src_word else None,
                                   "n": r.n, "seeded": r.seeded}
                for (lang, kind), r in sorted(self.rates.items())}


@dataclass
class RateController:
    """PI on the backlog in seconds. `scale` multiplies the next phrases' budget: 1.0 with no backlog, down to
    `min_scale` while it grows; once the backlog is back under the setpoint the integral drains within seconds."""

    kp: float = 0.15          # scale taken off per second of backlog now
    ki: float = 0.03          # ... and per second of backlog held for a second
    setpoint_s: float = 0.25  # a backlog this small is "in step"
    relax_s: float = 4.0      # in step again: what was held back is let go with this time constant
    min_scale: float = 0.6
    scale: float = 1.0
    integral: float = 0.0
    backlog_s: float = 0.0
    _last: float | None = field(default=None, repr=False)

    def update(self, backlog_s: float, now_s: float) -> float:
        dt = 0.0 if self._last is None else min(5.0, max(0.0, now_s - self._last))
        self._last = now_s
        self.backlog_s = backlog_s
        err = backlog_s - self.setpoint_s
        top = (1.0 - self.min_scale) / self.ki if self.ki > 0 else 0.0   # no wind-up beyond what the scale can use
        if err > 0:
            self.integral = min(top, self.integral + err * dt)
        else:   # the backlog is gone: a budget that stayed tight would drop words for nothing
            self.integral = max(0.0, self.integral * math.exp(-dt / self.relax_s) + err * dt)
        self.scale = min(1.0, max(self.min_scale, 1.0 - self.kp * max(0.0, err) - self.ki * self.integral))
        return self.scale


class SpeakingShare:
    """Share of the last `window_ms` the speaker was talking, from the spans of the phrases cut so far."""

    def __init__(self, window_ms: int = 30000, on: float = 0.70, off: float = 0.60, min_ms: int = 15000) -> None:
        self.window_ms, self.on, self.off, self.min_ms = window_ms, on, off, min_ms
        self._spans: deque[tuple[int, int]] = deque()
        self._first: int | None = None
        self._dense = False

    def add(self, start_ms: int, end_ms: int) -> None:
        if end_ms > start_ms:
            self._spans.append((start_ms, end_ms))
            self._first = start_ms if self._first is None else min(self._first, start_ms)

    def share(self, now_ms: int) -> float | None:
        """0-1, or None until `min_ms` of the session has been seen."""
        if self._first is None or now_ms - self._first < self.min_ms:
            return None
        lo = max(self._first, now_ms - self.window_ms)
        while self._spans and self._spans[0][1] <= lo:
            self._spans.popleft()
        talk = sum(max(0, min(b, now_ms) - max(a, lo)) for a, b in self._spans)
        return min(1.0, talk / max(1, now_ms - lo))

    def dense(self, now_ms: int) -> bool:
        s = self.share(now_ms)
        if s is None:
            return False
        if s > self.on:
            self._dense = True
        elif s < self.off:
            self._dense = False
        return self._dense


def plan(model: ExpansionModel, lang: str, kind: str, slot_ms: float, scale: float, share: float = 1.0) -> dict[str, Any] | None:
    """What the translator is asked for: the slot times `share` times the controller's `scale`, as words and letters."""
    target = max(400.0, slot_ms * share * scale)
    got = model.budget(lang, kind, target)
    if got is None:
        return None
    return {"target_ms": int(target), "max_words": got[0], "max_chars": got[1], "scale": round(scale, 2)}


def shorter_words(words: int, est_ms: float, target_ms: float) -> int:
    """How many words to ask for when a line of `words` words would take `est_ms` and has `target_ms`."""
    return max(2, min(words - 1, round(words * target_ms / max(est_ms, 1.0))))


def dur_ratio(dub_ms: float, slot_ms: float) -> float:
    return round(dub_ms / max(300.0, slot_ms), 3)


# ---------- v1.2 auto budget ----------
class WordRate:
    """Source words a second over the last `window_ms`, pauses included; "fast" over `on`, until under `off`."""

    def __init__(self, window_ms: int = 30000, on: float = 4.0, off: float = 3.2, min_ms: int = 15000) -> None:
        self.window_ms, self.on, self.off, self.min_ms = window_ms, on, off, min_ms
        self._lines: deque[tuple[int, int]] = deque()   # (end of the phrase, its words)
        self._first: int | None = None
        self._fast = False

    def add(self, start_ms: int, end_ms: int, words: int) -> None:
        self._lines.append((end_ms, words))
        self._first = start_ms if self._first is None else min(self._first, start_ms)

    def rate(self, now_ms: int) -> float | None:
        if self._first is None or now_ms - self._first < self.min_ms:
            return None
        lo = max(self._first, now_ms - self.window_ms)
        while self._lines and self._lines[0][0] <= lo:
            self._lines.popleft()
        return sum(w for _, w in self._lines) / max(1.0, (now_ms - lo) / 1000)

    def fast(self, now_ms: int) -> bool:
        r = self.rate(now_ms)
        if r is None:
            return False
        if r > self.on:
            self._fast = True
        elif r < self.off:
            self._fast = False
        return self._fast


@dataclass
class AutoGate:
    """One language's answer to "does the budget apply now?" (v1.2 auto mode).

    On when the dub is behind (running mean of the backlog at its last lines over `behind_on_ms`), when its lines
    come out longer than their slots (running mean of dur_ratio over `ratio_on`), or when speech is dense (the
    session's speaking share or word rate, each with its own two thresholds). Off again only when none of the
    three holds any more, by the lower thresholds, for `calm_lines` lines in a row, and not before `min_on_ms`:
    two thresholds, a count and a minimum time, so it does not flap. While off the translator is asked for the
    full line."""

    behind_on_ms: float = 500.0
    behind_off_ms: float = 200.0
    ratio_on: float = 1.15
    ratio_off: float = 1.05
    min_on_ms: int = 15000
    calm_lines: int = 4
    alpha: float = 0.4
    on: bool = False
    why: str = ""
    backlog: float | None = None     # running means
    ratio: float | None = None
    since_ms: int = 0
    _calm: int = field(default=0, repr=False)

    def update(self, now_ms: int, *, backlog_ms: float | None = None, dur_ratio: float | None = None,
               dense: bool = False) -> tuple[bool, str] | None:
        """Called after every line of the language (with its backlog and, when it was spoken, its dur_ratio) and
        with every phrase of the session (`dense` only). Returns (on, why) when the answer changed."""
        if backlog_ms is not None:
            self.backlog = backlog_ms if self.backlog is None else self.backlog + self.alpha * (backlog_ms - self.backlog)
        if dur_ratio is not None:
            self.ratio = dur_ratio if self.ratio is None else self.ratio + self.alpha * (dur_ratio - self.ratio)
        want = ("behind" if self.backlog is not None and self.backlog >= self.behind_on_ms else
                "long" if self.ratio is not None and self.ratio >= self.ratio_on else
                "dense" if dense else "")
        if not self.on:
            if want:
                self.on, self.why, self.since_ms, self._calm = True, want, now_ms, 0
                return True, want
            return None
        still = bool(want or dense or (self.backlog is not None and self.backlog > self.behind_off_ms)
                     or (self.ratio is not None and self.ratio > self.ratio_off))
        if still:
            self._calm = 0
            return None
        if backlog_ms is not None:      # only a line of this language counts towards "calm"
            self._calm += 1
        if self._calm >= self.calm_lines and now_ms - self.since_ms >= self.min_on_ms:
            self.on, self.why, self._calm = False, "", 0
            return False, "in step"
        return None


class MeaningRate:
    """One language's share of judged lines that lost meaning, and the budget steps that follow from it.

    Only lines that were translated under the budget count towards the rate (the others say nothing about it).
    Over `max_rate` on at least `min_samples` judged lines: one step looser (`steps` + 1, each step gives the
    budget more of the slot; at `max_steps` the language is translated in full). After a step the rate is
    measured afresh. At or under `low_rate` on `min_samples` new lines, with the dub behind, and not sooner than
    `tighten_after_s` after the last step: one step tighter. At `max_steps` nothing is budgeted, so nothing can be
    judged: after `tighten_after_s` with the dub behind it goes back one step on trial."""

    def __init__(self, window: int = 12, min_samples: int = 6, max_rate: float = 0.25, low_rate: float = 0.10,
                 max_steps: int = 3, tighten_after_s: float = 120.0) -> None:
        self.window, self.min_samples = max(1, window), max(1, min_samples)
        self.max_rate, self.low_rate, self.max_steps, self.tighten_after_s = max_rate, low_rate, max_steps, tighten_after_s
        self.steps = 0
        self.judged = self.lost = self.shifted = 0          # the whole session, every judged line
        self.judged_budgeted = self.lost_budgeted = 0
        self._recent: deque[bool] = deque(maxlen=self.window)   # budgeted lines since the last step: lost?
        self._last_step_s = 0.0

    def rate(self) -> float | None:
        """Share of the last judged budgeted lines that lost meaning; None before `min_samples`."""
        return sum(self._recent) / len(self._recent) if len(self._recent) >= self.min_samples else None

    def add(self, *, budgeted: bool, lost: bool, shift: bool, now_s: float, behind: bool) -> dict[str, Any] | None:
        """One judged line. Returns the adjustment it caused, if any: {was, steps, why, rate, n}."""
        self.judged += 1
        self.lost += int(lost)
        self.shifted += int(shift)
        if budgeted:
            self.judged_budgeted += 1
            self.lost_budgeted += int(lost)
            if self.steps < self.max_steps:   # at the last step nothing is budgeted: a late verdict is of an older line
                self._recent.append(bool(lost))
        return self._adjust(now_s, behind)

    def tick(self, now_s: float, behind: bool) -> dict[str, Any] | None:
        """Without a new judged line: the trial step back from "translated in full"."""
        return self._adjust(now_s, behind) if self.steps >= self.max_steps else None

    def _adjust(self, now_s: float, behind: bool) -> dict[str, Any] | None:
        rate, n, was = self.rate(), len(self._recent), self.steps
        why = ""
        if rate is not None and rate > self.max_rate and self.steps < self.max_steps:
            self.steps += 1
            why = f"{rate:.0%} of {n} judged lines lost meaning (limit {self.max_rate:.0%}): looser"
        elif self.steps > 0 and behind and now_s - self._last_step_s >= self.tighten_after_s:
            if self.steps >= self.max_steps and not n:
                self.steps -= 1
                why = "translated in full and still behind: one step back on trial"
            elif rate is not None and rate <= self.low_rate:
                self.steps -= 1
                why = f"{rate:.0%} of {n} judged lines lost meaning (low: {self.low_rate:.0%}) and the dub is behind: tighter"
        if not why:
            return None
        self._recent.clear()
        self._last_step_s = now_s
        return {"was": was, "steps": self.steps, "why": why, "rate": round(rate, 3) if rate is not None else None, "n": n}

    def state(self) -> dict[str, Any]:
        rate = self.rate()
        return {"steps": self.steps, "rate": round(rate, 3) if rate is not None else None, "recent": len(self._recent),
                "judged": self.judged, "lost": self.lost, "shifted": self.shifted,
                "judged_budgeted": self.judged_budgeted, "lost_budgeted": self.lost_budgeted,
                "loss_rate_session": round(self.lost_budgeted / self.judged_budgeted, 3) if self.judged_budgeted else None,
                "shift_rate_session": round(self.shifted / self.judged, 3) if self.judged else None}
