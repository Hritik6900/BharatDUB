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

    def make(self, text: str, *, t_start_ms: int, t_end_ms: int, t_final_ms: int) -> Chunk:
        """A ready-made chunk (a phrase cut from partials) in the same sequence."""
        self._seq += 1
        return Chunk(self._seq, text, t_start_ms, t_end_ms, t_final_ms)

    def flush(self) -> Chunk | None:
        return self._flush() if self._parts else None

    def _flush(self) -> Chunk:
        self._seq += 1
        c = Chunk(self._seq, " ".join(self._parts), self._start or 0, min(self._end, self._final), self._final)
        self._parts, self._start, self._speech_ms = [], None, 0
        return c


# Words after which a Hindi/Hinglish clause usually ends, and words that usually open the next one.
CLAUSE_END = frozenset("है हैं था थे थी हूँ हूं हो होगा होगी होंगे गया गई गए दिया दिए लिया करो करें चाहिए ना "
                       "नहीं यार भाई bro ok okay".split())
CLAUSE_START = frozenset("और लेकिन पर मगर तो कि क्योंकि फिर जो जब अगर या but and so because then".split())
# The same words as the GPU speech-to-text writes them (Hindi in Latin letters). "to", "par", "the" and "ho" are left
# out: in Hinglish they are as often English words.
CLAUSE_END |= frozenset("hai hain tha thi hoon hun hoga hogi honge gaya gayi gaye diya diye liya karo karen karein "
                        "chahiye na nahin nahi yaar bhai".split())
CLAUSE_START |= frozenset("aur lekin magar ki kyonki kyunki phir fir jo jab agar ya".split())


def _word(w: str) -> str:
    return w.lower().strip(".,?!।\"'…")
PARTIAL_LAG_MS = 600   # estimate: a word shows up in a partial about this long after it was spoken
PACE_MS = (120, 700)   # ms a word: outside this, the utterance's start is not believed


def _bare(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalnum() or ch in "\u093c\u094d" or "\u0900" <= ch <= "\u097f")


class Phraser:
    """Cuts phrases out of an utterance while it is still being spoken.

    Prisma partials carry `stable_text`, a prefix it no longer rewrites. Once enough new stable words are
    there, a phrase is cut at a clause boundary (or at `max_words`), so translation and voice start seconds
    before the speaker pauses. `final()` returns whatever the phrases have not covered.

    State is kept per utterance id: when Prisma cuts a long utterance, the next one's first events arrive
    before the previous one's final transcript.
    """

    def __init__(self, min_words: int = 6, max_words: int = 12) -> None:
        self.min_words, self.max_words = min_words, max_words
        self._done: dict[str, int] = {}        # words of the utterance already given out
        self._seen: dict[str, list[int]] = {}  # when word i first showed up in a partial (session clock)
        self._last: dict[str, list[str]] = {}  # last two words given out, to find the tail in the final
        self._t0: dict[str, int] = {}          # when the utterance began, if the caller knows (session clock)

    def reset(self) -> None:
        self._done.clear()
        self._seen.clear()
        self._last.clear()
        self._t0.clear()

    def start_of(self, uid: str | None) -> int | None:
        """When this utterance began, as given with its first partial. Ask before `final()`."""
        return self._t0.get(uid or "")

    def covered(self, uid: str | None) -> bool:
        """True when phrases of this utterance have already gone out."""
        return self._done.get(uid or "", 0) > 0

    def partial(self, uid: str | None, stable: str, full: str, now_ms: int,
                t0: int | None = None) -> tuple[str, int, int] | None:
        """Returns (text, t_start_ms, t_end_ms) for a phrase that is ready, else None.

        `t0`: when the utterance began (the speech start before its first partial). With it, a phrase's time is
        its share of the utterance so far at an even pace. Without it, when its words first showed up, which
        comes in bursts: a first partial brings six words at once and stamps them all with the same moment.
        """
        uid = uid or ""
        seen = self._seen.setdefault(uid, [])
        if t0 is not None and not seen and uid not in self._t0:
            self._t0[uid] = t0
        seen += [now_ms] * max(0, len(full.split()) - len(seen))
        done = self._done.get(uid, 0)
        avail = stable.split()[done:]
        k = self._cut(avail, full.split()[done:])
        if not k:
            return None
        self._done[uid] = done + k
        self._last[uid] = [_bare(w) for w in avail[:k][-2:]]
        while len(self._seen) > 8:  # utterances whose final never came
            old = next(iter(self._seen))
            self._seen.pop(old, None)
            self._done.pop(old, None)
            self._last.pop(old, None)
            self._t0.pop(old, None)
        return " ".join(avail[:k]), *self._span(uid, done, done + k, now_ms)

    def _span(self, uid: str, a: int, b: int, now_ms: int) -> tuple[int, int]:
        """When words [a, b) of the utterance were spoken."""
        seen, t0 = self._seen.get(uid, []), self._t0.get(uid)
        if t0 is not None and seen:
            per = (now_ms - PARTIAL_LAG_MS - t0) / len(seen)   # the words heard so far, spread evenly
            if PACE_MS[0] <= per <= PACE_MS[1]:
                return int(t0 + a * per), int(t0 + b * per)
        return self._when(seen, a), self._when(seen, b - 1)

    def tail_start(self, uid: str | None) -> int | None:
        """When the first word not yet given out was spoken, if a partial ever showed it. Ask before `final()`."""
        uid = uid or ""
        seen, done = self._seen.get(uid, []), self._done.get(uid, 0)
        return self._when(seen, done) if done < len(seen) else None

    def final(self, uid: str | None, text: str) -> str:
        """The part of the final transcript not yet given out.

        The final is a fresh decode: it adds punctuation and can differ from the partials by a word or two, so
        the tail starts after the last two words given out when they can be found near where they should be.
        """
        uid = uid or ""
        done = self._done.pop(uid, 0)
        last = self._last.pop(uid, [])
        self._seen.pop(uid, None)
        self._t0.pop(uid, None)
        words = text.split()
        bare = [_bare(w) for w in words]
        if done and len(last) == 2:
            near = [i + 2 for i in range(len(bare) - 1) if bare[i:i + 2] == last and abs(i + 2 - done) <= 3]
            if near:
                done = min(near, key=lambda i: abs(i - done))
        rest = " ".join(words[done:])
        return rest if any(ch.isalnum() for ch in rest) else ""

    @staticmethod
    def _when(seen: list[int], i: int) -> int:
        at = seen[i] if i < len(seen) else (seen[-1] if seen else 0)
        return max(0, at - PARTIAL_LAG_MS)

    def _cut(self, avail: list[str], ahead: list[str] | None = None) -> int:
        """`ahead`: the same words plus the ones the recogniser has not settled yet. They may still change, but
        they show when a sentence is one word from its end: cutting there left that word as a line of its own
        (seen 2026-11-21 on a real stream: "... milta nahin" and then "hai?", 19 of 490 phrases)."""
        ahead = ahead if ahead and len(ahead) > len(avail) else avail
        for k in range(self.min_words, min(len(avail), self.max_words) + 1):
            # Punctuation comes only from a recogniser that writes it (the GPU one); a full stop ends a clause.
            if avail[k - 1].endswith(SENTENCE_END) or _word(avail[k - 1]) in CLAUSE_END \
                    or (k < len(avail) and _word(avail[k]) in CLAUSE_START):
                nxt = ahead[k] if k < len(ahead) else ""
                if k < self.max_words and not avail[k - 1].endswith(SENTENCE_END) and nxt \
                        and (nxt.endswith(SENTENCE_END) or _word(nxt) in CLAUSE_END):
                    continue   # the next word closes the sentence: it belongs to this phrase
                return k
        return self.max_words if len(avail) >= self.max_words else 0
