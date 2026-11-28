"""Between stages 5 and 6: a long line is cut into several, so the dub follows the video to its end.

A speaker who never pauses gives one speech segment of up to 25 s, and so one line. Its dub starts at the line's
start and is as long as the target language needs: on 28 Nov 2026 a 24.8 s line came out 16.7 s in Tamil and
18.6 s on another run, and the last 6-8 s of the video had no voice at all. Cut into lines of a few seconds, each
piece is spoken at its own moment.

The pieces are sentences of the transcript (then clauses, then words when a sentence is too long). Their times
are an estimate: the line's time shared out by words, each cut then moved to the quietest moment nearby.
"""
import re

import numpy as np

SR = 16000
TARGET_S = 6.0      # the length a piece aims for
MIN_PIECE_S = 2.0   # a piece is never shorter than this
SNAP_S = 0.5        # how far a cut may move to find a quiet moment
FRAME_S = 0.05

_SENTENCE = re.compile(r"(?<=[।॥.?!])\s+")
_CLAUSE = re.compile(r"(?<=[,;:،])\s+")


def _by_words(words: list[str], most: int) -> list[str]:
    """`words` in pieces of about equal size, none over `most` words."""
    n = max(1, -(-len(words) // most))
    size = -(-len(words) // n)
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def pieces(text: str, most_words: int) -> list[str]:
    """The text as sentences; a sentence over `most_words` as clauses; a clause over it as runs of words."""
    out: list[str] = []
    for sentence in (p for p in _SENTENCE.split(text.strip()) if p.strip()):
        if len(sentence.split()) <= most_words:
            out.append(sentence.strip())
            continue
        for clause in (p for p in _CLAUSE.split(sentence) if p.strip()):
            words = clause.split()
            out.extend([clause.strip()] if len(words) <= most_words else _by_words(words, most_words))
    return out


def group(parts: list[str], want_words: float, least_words: float) -> list[str]:
    """Neighbouring pieces joined until each line has about `want_words` words and none is under `least_words`."""
    lines: list[str] = []
    for p in parts:
        if lines and len(lines[-1].split()) + len(p.split()) / 2 <= want_words:
            lines[-1] += " " + p
        else:
            lines.append(p)
    i = 0
    while len(lines) > 1 and i < len(lines):
        if len(lines[i].split()) < least_words:
            j = i - 1 if i > 0 and (i == len(lines) - 1 or len(lines[i - 1].split()) <= len(lines[i + 1].split())) else i + 1
            a, b = min(i, j), max(i, j)
            lines[a:b + 1] = [lines[a] + " " + lines[b]]
            i = 0
        else:
            i += 1
    return lines


def quiet_near(audio16k: np.ndarray | None, t: float, lo: float, hi: float) -> float:
    """The quietest moment within `SNAP_S` of `t` and inside (lo, hi); `t` itself without audio."""
    if audio16k is None or not len(audio16k):
        return t
    a, b = max(lo, t - SNAP_S), min(hi, t + SNAP_S)
    n = int(FRAME_S * SR)
    first, last = int(a * SR) // n, int(b * SR) // n
    if last - first < 2:
        return t
    frames = audio16k[first * n:last * n].astype(np.float64).reshape(-1, n)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    return round((first + int(rms.argmin()) + 0.5) * FRAME_S, 3)


def split_line(start: float, end: float, text: str, longest_s: float,
               audio16k: np.ndarray | None = None) -> list[tuple[float, float, str]]:
    """One line as it is, or as several when it is longer than `longest_s` and has more than one piece."""
    dur, words = end - start, text.split()
    if longest_s <= 0 or dur <= longest_s or len(words) < 8:
        return [(start, end, text)]
    per_s = len(words) / dur
    lines = group(pieces(text, max(4, round(per_s * TARGET_S))), per_s * TARGET_S, per_s * MIN_PIECE_S)
    if len(lines) < 2:
        return [(start, end, text)]
    out: list[tuple[float, float, str]] = []
    s, said = start, 0
    for i, line in enumerate(lines):
        said += len(line.split())
        if i == len(lines) - 1:
            e = end
        else:
            e = quiet_near(audio16k, start + dur * said / len(words), s + MIN_PIECE_S / 2, end - MIN_PIECE_S / 2)
            e = min(max(e, s + MIN_PIECE_S / 2), end - MIN_PIECE_S / 2)
        out.append((round(s, 3), round(e, 3), line))
        s = e
    return out


def split_long(segs: list[tuple[float, float]], results: list[dict], longest_s: float,
               audio16k: np.ndarray | None = None) -> tuple[list[tuple[float, float]], list[dict]]:
    """Every segment and its transcript, long ones cut. A piece keeps its segment's detected language."""
    new_segs: list[tuple[float, float]] = []
    new_results: list[dict] = []
    for (s, e), r in zip(segs, results):
        for a, b, text in split_line(s, e, r.get("text") or "", longest_s, audio16k):
            new_segs.append((a, b))
            new_results.append({**r, "text": text})
    return new_segs, new_results
