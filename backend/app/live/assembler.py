"""Turns Prisma final utterances into dub chunks (SPEC.md section 9).

Prisma realtime has no partials: each `transcript` event is a final utterance that already ended in
~500 ms of silence. A chunk closes when the text ends a sentence, OR 1.2 s of silence has passed since
speech ended (we wait the remaining ~0.7 s for a continuation), OR 6 s of speech has accumulated.
"""
from dataclasses import dataclass, field

SENTENCE_END = ("।", "॥", ".", "?", "!", "؟", "…")
SILENCE_MS = 1200
STT_SILENCE_MS = 500   # x-min-silence-ms we send to Prisma
MAX_SPEECH_MS = 6000


@dataclass
class Chunk:
    seq: int
    text: str
    t_speech_ms: int       # when the first utterance started (session clock)
    t_speech_end_ms: int   # when the last utterance's speech ended
    t_stt_final_ms: int    # when the last final transcript arrived
    timings: dict[str, int] = field(default_factory=dict)


class Assembler:
    def __init__(self, silence_ms: int = SILENCE_MS, max_speech_ms: int = MAX_SPEECH_MS) -> None:
        self.silence_ms, self.max_speech_ms = silence_ms, max_speech_ms
        self._seq = 0
        self._parts: list[str] = []
        self._start: int | None = None
        self._end = 0
        self._final = 0
        self._speech_ms = 0

    @property
    def pending(self) -> bool:
        return bool(self._parts)

    def add(self, text: str, *, t_start_ms: int, t_end_ms: int, t_final_ms: int) -> Chunk | None:
        text = text.strip()
        if not text:
            return None
        if self._start is None:
            self._start = t_start_ms
        self._parts.append(text)
        self._end, self._final = t_end_ms, t_final_ms
        self._speech_ms += max(0, t_end_ms - t_start_ms)
        if text.endswith(SENTENCE_END) or self._speech_ms >= self.max_speech_ms:
            return self._flush()
        return None

    def poll(self, now_ms: int) -> Chunk | None:
        """Call periodically: closes the chunk after `silence_ms` without new speech."""
        if self._parts and now_ms - self._end >= self.silence_ms:
            return self._flush()
        return None

    def speech_started(self) -> None:
        """New speech began: push the silence deadline forward."""
        if self._parts:
            self._end = 10**15  # never flush on silence while someone is talking

    def flush(self) -> Chunk | None:
        return self._flush() if self._parts else None

    def _flush(self) -> Chunk:
        self._seq += 1
        c = Chunk(self._seq, " ".join(self._parts), self._start or 0, min(self._end, self._final), self._final)
        self._parts, self._start, self._speech_ms = [], None, 0
        return c
