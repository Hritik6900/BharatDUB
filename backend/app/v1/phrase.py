"""Live phrase logic of v1, free of I/O so it can be tested alone.

  ShortLineMerger  dense speech (auto budget): a line of fewer than 3 words waits for the next line and goes out
                   as part of it (the voice engine swallows very short lines); alone when nothing follows.
  same_words       two transcripts of the same speech (the HQ transcript step uses it).

(`DynamicPhraser`, the short first phrase of `V1_PHRASE_DYNAMIC`, was removed in v1.2: five points fewer phrases
on time on dense speech in its measurement.)
"""
from dataclasses import dataclass

from app.live.assembler import Chunk, _bare


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
