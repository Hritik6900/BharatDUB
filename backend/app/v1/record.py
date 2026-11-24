"""A Live session's dub kept on disk (`V1_LIVE_RECORD`), for the pitch renderer (app/v1/pitch.py).

Live audio is never stored (SPEC section 10). This is the one exception and it is asked for twice: the flag
must be on AND the session must have been made with `record=true` (a tick on the console that says what is
kept). With either one missing no Recorder exists and not one byte is written.

What is kept, under `<DATA_DIR>/recordings/<session>/` (never in the repository, never in `logs/`):
  session.json     what the session was: languages, source language, sample rate, engine, when it began
  dub_<lang>.wav   one continuous mono track per language on the session's clock: a phrase's sound lies at the
                   moment a viewer's player starts it (`track_ms`), silence between phrases
  phrases.jsonl    one line per spoken or skipped phrase and language: seq, lang, t_speech_ms (when it was said,
                   session clock), media_s (the video's time at that moment, sync mode only), start_ms and
                   track_ms (where its dub starts), dur_ms, late_ms (start after its moment, sync mode only),
                   hold_ms (how far a viewer's video is held back), first_audio_ms (end of the phrase to its first
                   dubbed sound), voice (copied | stock), tempo, the caption text the renderer burns in, or
                   `skipped` with the reason
The original sound is not kept: the renderer takes it from the source video.
"""
import json
import logging
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings

log = logging.getLogger("v1.record")


def folder(s: Settings | None = None) -> Path:
    """Where recordings go. Only names the place: nothing is created here."""
    s = s or get_settings()
    return Path(s.v1_record_dir) if s.v1_record_dir else s.data_path / "recordings"


def wanted(row: dict[str, Any], s: Settings | None = None) -> bool:
    """Both switches: the flag and the session's own ask."""
    return bool((s or get_settings()).v1_live_record and row.get("record"))


class Recorder:
    def __init__(self, session_id: str, langs: list[str], sample_rate: int, *, engine: str = "cloud",
                 src_lang: str = "", root: Path | None = None) -> None:
        self.dir = (root or folder()) / session_id
        self.session_id, self.langs, self.sr, self.engine = session_id, list(langs), sample_rate, engine
        self.src_lang = src_lang
        self._wav: dict[str, wave.Wave_write] = {}
        self._frames: dict[str, int] = {}   # per language: samples written so far
        self._open = False
        self.phrases = 0

    def start(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "session.json").write_text(json.dumps({
            "session": self.session_id, "langs": self.langs, "src_lang": self.src_lang, "sample_rate": self.sr, "engine": self.engine,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": "Kept because the session was made with record=true while V1_LIVE_RECORD was on."}, indent=1),
            encoding="utf-8")
        self._open = True

    def _track(self, lang: str) -> wave.Wave_write:
        w = self._wav.get(lang)
        if w is None:
            w = wave.open(str(self.dir / f"dub_{lang}.wav"), "wb")
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            self._wav[lang], self._frames[lang] = w, 0
        return w

    def _row(self, row: dict[str, Any]) -> None:
        with (self.dir / "phrases.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.phrases += 1

    def add(self, lang: str, seq: int, pcm: bytes, *, start_ms: int, **meta: Any) -> None:
        """One spoken phrase: `pcm` (PCM16 mono at the session's rate) lies at `start_ms` on the track."""
        if not self._open or not pcm:
            return
        try:
            w = self._track(lang)
            at = max(0, round(start_ms * self.sr / 1000))
            have = self._frames[lang]
            if at > have:
                w.writeframesraw(b"\x00\x00" * (at - have))
                have = at
            w.writeframesraw(pcm[: len(pcm) // 2 * 2])
            self._frames[lang] = have + len(pcm) // 2
            self._row({"seq": seq, "lang": lang, "start_ms": int(start_ms), "track_ms": round(have * 1000 / self.sr),
                       "dur_ms": round(len(pcm) / 2 * 1000 / self.sr), **{k: v for k, v in meta.items() if v is not None}})
        except (OSError, wave.Error) as e:    # a full disk must not stop the stream
            log.warning("recording %s: %s", self.session_id[:8], e)

    def skip(self, lang: str, seq: int, why: str, **meta: Any) -> None:
        """A phrase that got a caption and no sound."""
        if not self._open:
            return
        try:
            self._row({"seq": seq, "lang": lang, "skipped": why, **{k: v for k, v in meta.items() if v is not None}})
        except OSError as e:
            log.warning("recording %s: %s", self.session_id[:8], e)

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        for w in self._wav.values():
            try:
                w.close()     # writes the sizes into the header
            except (OSError, wave.Error) as e:
                log.warning("recording %s: %s", self.session_id[:8], e)
        try:
            meta = json.loads((self.dir / "session.json").read_text(encoding="utf-8"))
            meta |= {"ended_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": self.phrases,
                     "track_s": {lg: round(n / self.sr, 2) for lg, n in self._frames.items()}}
            (self.dir / "session.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        except (OSError, ValueError) as e:
            log.warning("recording %s: %s", self.session_id[:8], e)
