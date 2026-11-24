"""Live phrase logic of v1, each part behind its own flag and free of I/O so it can be tested alone.

  DynamicPhraser   `V1_PHRASE_DYNAMIC`: the session's first phrase is short (4-6 words) so the first dubbed audio
                   comes early; later phrases are longer (8-12 words), which the voice speaks better.
  ShortLineMerger  `V1_PHRASE_DYNAMIC`: a line of fewer than 3 words waits for the next line and goes out as part
                   of it (the voice engine swallows very short lines); it goes out alone when nothing follows.
"""
from dataclasses import dataclass

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
