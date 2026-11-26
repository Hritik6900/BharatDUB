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

How long it stays (ADR-0034): a recording is deleted by itself `V1_RECORD_KEEP_DAYS` days (30) after it ended
(`sweep`, run when the backend starts and every half hour while it runs; 0 = never by itself), and anyone who can
reach the console can delete one at any time (`DELETE /api/v1/recordings/<session>`, the list on `/live`).
Listing, deleting and the sweep work whether or not the flag is on now: what was kept earlier must still go.
"""
import json
import logging
import re
import shutil
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import Settings, get_settings
from app.v1 import mode as v1mode

log = logging.getLogger("v1.record")
router = APIRouter()
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")     # a folder name of ours, never a path


def folder(s: Settings | None = None) -> Path:
    """Where recordings go. Only names the place: nothing is created here."""
    s = s or get_settings()
    return Path(s.v1_record_dir) if s.v1_record_dir else s.data_path / "recordings"


def wanted(row: dict[str, Any], s: Settings | None = None) -> bool:
    """Both switches: the flag and the session's own ask."""
    return bool(v1mode.on("live_record", s or get_settings()) and row.get("record"))


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


# ---------- what is kept, for how long, and deleting it ----------
def _when(d: Path, meta: dict[str, Any]) -> datetime:
    """When a recording ended: what its own file says, else when it began, else the newest file in it."""
    for key in ("ended_at", "started_at"):
        try:
            got = datetime.fromisoformat(str(meta[key]))
            return got if got.tzinfo else got.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
    newest = max((f.stat().st_mtime for f in d.iterdir() if f.is_file()), default=d.stat().st_mtime)
    return datetime.fromtimestamp(newest, timezone.utc)


def _describe(d: Path, keep_days: int) -> dict[str, Any]:
    try:
        meta = json.loads((d / "session.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    files = [f for f in d.iterdir() if f.is_file()]
    ended = _when(d, meta)
    return {"session": d.name, "started_at": meta.get("started_at"), "ended_at": meta.get("ended_at"),
            "langs": meta.get("langs") or sorted(f.stem[4:] for f in files if f.name.startswith("dub_")),
            "engine": meta.get("engine"), "phrases": meta.get("rows"), "files": len(files),
            "bytes": sum(f.stat().st_size for f in files), "kept_since": ended.isoformat(timespec="seconds"),
            "deleted_after": (ended + timedelta(days=keep_days)).isoformat(timespec="seconds") if keep_days > 0 else None}


def listing(s: Settings | None = None) -> list[dict[str, Any]]:
    """Every recording on this server, newest first. No caption text, no audio: names, sizes and dates."""
    s = s or get_settings()
    root = folder(s)
    if not root.is_dir():
        return []
    rows = [_describe(d, int(s.v1_record_keep_days)) for d in root.iterdir() if d.is_dir() and SESSION_ID.match(d.name)]
    return sorted(rows, key=lambda r: r["kept_since"], reverse=True)


def delete(session_id: str, s: Settings | None = None) -> bool:
    """Remove one recording (its whole folder). False = there is none by that name."""
    if not SESSION_ID.match(session_id or ""):
        return False
    d = folder(s) / session_id
    if not d.is_dir():
        return False
    shutil.rmtree(d)
    return True


def sweep(s: Settings | None = None, now: datetime | None = None, skip: set[str] | None = None) -> list[str]:
    """Delete every recording that ended more than `v1_record_keep_days` days ago; returns the sessions removed.
    0 days = nothing is deleted by itself. `skip`: sessions being recorded right now."""
    s = s or get_settings()
    days = int(s.v1_record_keep_days)
    root = folder(s)
    if days <= 0 or not root.is_dir():
        return []
    limit = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    gone = []
    for d in root.iterdir():
        if not d.is_dir() or not SESSION_ID.match(d.name) or d.name in (skip or ()):
            continue
        try:
            meta = json.loads((d / "session.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        try:
            if _when(d, meta) < limit:
                shutil.rmtree(d)
                gone.append(d.name)
        except OSError as e:
            log.warning("recording %s could not be deleted: %s", d.name[:8], e)
    if gone:
        log.info("recordings older than %d days deleted: %d", days, len(gone))
    return gone


def _open_now() -> set[str]:
    """Sessions whose recording is being written at this moment."""
    from app.live.session import sessions      # here, not at the top: live.session imports this module
    return {sid for sid, sess in sessions._sessions.items()
            if sess.pipeline is not None and getattr(sess.pipeline, "_rec", None) is not None and sess.pipeline.running}


def sweep_now() -> list[str]:
    return sweep(skip=_open_now())


@router.get("/api/v1/recordings")
async def list_recordings() -> dict[str, Any]:
    s = get_settings()
    return {"keep_days": int(s.v1_record_keep_days), "recording_allowed": bool(v1mode.on("live_record", s)), "recordings": listing(s)}


@router.delete("/api/v1/recordings/{session_id}")
async def delete_recording(session_id: str) -> dict[str, bool]:
    if not SESSION_ID.match(session_id):
        raise HTTPException(404, "no such recording")
    if session_id in _open_now():
        raise HTTPException(409, "This session is still being recorded. Stop it first.")
    if not delete(session_id):
        raise HTTPException(404, "no such recording")
    log.info("recording %s deleted on request", session_id[:8])
    return {"deleted": True}
