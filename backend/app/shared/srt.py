"""SRT writing. First cue is the AI label (SPEC.md section 15)."""
from pathlib import Path

AI_LABEL = "AI-dubbed by Bharat Dub"


def srt_time(sec: float) -> str:
    ms = max(0, int(round(sec * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def build_srt(cues: list[tuple[float, float, str]], *, label: bool = True) -> str:
    items: list[tuple[float, float, str]] = []
    if label:
        items.append((0.0, 2.0, AI_LABEL))
    items += [(s, e, t) for s, e, t in cues if t.strip()]
    return "".join(f"{i}\n{srt_time(s)} --> {srt_time(e)}\n{t.strip()}\n\n" for i, (s, e, t) in enumerate(items, 1))


def write_srt(path: str | Path, cues: list[tuple[float, float, str]], *, label: bool = True) -> None:
    Path(path).write_text(build_srt(cues, label=label), encoding="utf-8")
