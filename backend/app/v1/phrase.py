"""Live phrase logic of v1, each part behind its own flag and free of I/O so it can be tested alone.

  DynamicPhraser   `V1_PHRASE_DYNAMIC`: the session's first phrase is short (4-6 words) so the first dubbed audio
                   comes early; later phrases are longer (8-12 words), which the voice speaks better.
  ShortLineMerger  `V1_PHRASE_DYNAMIC`: a line of fewer than 3 words waits for the next line and goes out as part
                   of it (the voice engine swallows very short lines); it goes out alone when nothing follows.
  SpecTracker      `V1_SPEC_TRANSLATE`: when the words not yet dubbed have stood still in the partials for a
                   moment, they are translated ahead of the final transcript; the result is used when the final
                   says the same words, and dropped when it does not.
"""
from dataclasses import dataclass, field
from typing import Any

from app.live.assembler import Chunk, Phraser, _bare


class DynamicPhraser(Phraser):
    def __init__(self, first: tuple[int, int] = (4, 6), later: tuple[int, int] = (8, 12)) -> None:
        super().__init__(*first)
        self.first_bounds, self.later_bounds = first, later
        self.given = 0   # phrases cut so far in this session

    def partial(self, uid: str | None, stable: str, full: str, now_ms: int,
                t0: int | None = None) -> tuple[str, int, int] | None:
        self.min_words, self.max_words = self.first_bounds if self.given == 0 else self.later_bounds
        cut = super().partial(uid, stable, full, now_ms, t0)
        if cut:
            self.given += 1
        return cut

    def rest(self, uid: str | None, full: str) -> str:
        """The words of the utterance so far that no phrase has taken yet."""
        return rest_of(self, uid, full)


def rest_of(phraser: Phraser, uid: str | None, full: str) -> str:
    return " ".join(full.split()[phraser._done.get(uid or "", 0):])


def n_words(text: str) -> int:
    return len([w for w in text.split() if any(ch.isalnum() for ch in w)])


@dataclass
class ShortLineMerger:
    """Holds one short line back until the next line arrives or `wait_ms` has passed."""

    under_words: int = 3
    wait_ms: int = 1500
    held: Chunk | None = None
    deadline: int = 0
    merged: int = 0     # short lines that went out as part of the next line
    alone: int = 0      # short lines that went out alone (nothing followed in time)

    def push(self, chunk: Chunk, now_ms: int) -> list[Chunk]:
        """Give a new line; get back the lines that go out now (none when it is held)."""
        if self.held is not None:
            first, self.held = self.held, None
            chunk = Chunk(chunk.seq, f"{first.text} {chunk.text}".strip(), min(first.t_speech_ms, chunk.t_speech_ms),
                          chunk.t_speech_end_ms, chunk.t_stt_final_ms)
            self.merged += 1
            return [chunk]          # a joined line goes out even if it is still short: nothing waits twice
        if n_words(chunk.text) < self.under_words:
            self.held, self.deadline = chunk, now_ms + self.wait_ms
            return []
        return [chunk]

    def poll(self, now_ms: int) -> Chunk | None:
        """The held line, once it has waited long enough."""
        if self.held is not None and now_ms >= self.deadline:
            out, self.held = self.held, None
            self.alone += 1
            return out
        return None

    def flush(self) -> Chunk | None:
        out, self.held = self.held, None
        return out


def same_words(a: str, b: str) -> bool:
    """Two transcripts of the same speech: equal once case and punctuation are set aside."""
    wa, wb = [_bare(w) for w in a.split()], [_bare(w) for w in b.split()]
    return [w for w in wa if w] == [w for w in wb if w]


@dataclass
class SpecTracker:
    """Decides when the undubbed rest of an utterance is worth translating ahead, and whether a final matches."""

    stable_ms: int = 300
    min_words: int = 2
    text: str = ""
    since: int = 0
    tasks: dict[str, Any] | None = None     # lang -> running translation of `text`
    started: int = 0
    used: int = 0
    dropped: int = 0
    gap_ms: float = 0.0                     # how far apart partials arrive while someone speaks (running average)
    _seen: str = field(default="", repr=False)
    _last: int = field(default=0, repr=False)

    def wait_ms(self) -> float:
        """How long the words must stand still. A speaker who is still talking brings a new partial every
        `gap_ms`, so anything shorter than a gap and a half would fire between two ordinary partials."""
        return max(float(self.stable_ms), 1.5 * self.gap_ms)

    def due(self, now_ms: int) -> bool:
        """Call between partials too: a speaker who has stopped sends no further partial, and that pause is
        exactly when the words stand still. True = start translating `self.text` now."""
        return (self.tasks is None and bool(self.text) and n_words(self.text) >= self.min_words
                and now_ms - self.since >= self.wait_ms())

    def observe(self, rest: str, now_ms: int) -> bool:
        """Call with the undubbed rest at every partial. True = start translating `self.text` now."""
        if self._last and 0 < now_ms - self._last < 2000:
            gap = float(now_ms - self._last)
            self.gap_ms = gap if not self.gap_ms else 0.8 * self.gap_ms + 0.2 * gap
        self._last = now_ms
        rest = rest.strip()
        if not rest or not same_words(rest, self._seen):
            self.cancel()
            self._seen, self.text, self.since = rest, rest, now_ms
            return False
        self.text = rest
        return self.due(now_ms)

    def begin(self, tasks: dict[str, Any]) -> None:
        self.tasks = tasks
        self.started += 1

    def take(self, final_text: str) -> dict[str, Any] | None:
        """The running translations if the line that is going out says the same words; else they are dropped."""
        tasks, self.tasks = self.tasks, None
        text, self._seen, self.text = self.text, "", ""
        if tasks is None:
            return None
        if same_words(final_text, text):
            self.used += 1
            return tasks
        self.dropped += 1
        for t in tasks.values():
            t.cancel()
        return None

    def cancel(self) -> None:
        if self.tasks is not None:
            self.dropped += 1
            for t in self.tasks.values():
                t.cancel()
            self.tasks = None
