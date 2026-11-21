"""Studio REST + SSE (SPEC.md section 11)."""
import asyncio
import json
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.config import LANG_NAMES, get_settings
from app.db import now_iso
from app.providers.base import ProviderError
from app.shared.storage import output_url
from app.studio.events import events
from app.studio.runner import runner
from app.studio.stages.extract import IngestError

router = APIRouter()
# Shown next to the checkbox on /studio; stored on the voice profile created from the video.
VIDEO_VOICE_CONSENT = ("The voice in this video is mine, or I have the speaker's permission, and I agree that "
                       "Bharat Dub may make a copy of it to dub this video.")
ALLOWED_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def parse_langs(raw: str) -> list[str]:
    langs = list(dict.fromkeys(x.strip() for x in raw.split(",") if x.strip()))
    bad = [lg for lg in langs if lg not in LANG_NAMES]
    if not langs or bad:
        raise HTTPException(400, f"target_langs must be codes from {sorted(LANG_NAMES)}; bad: {bad}")
    return langs


async def _job_or_404(job_id: str) -> dict[str, Any]:
    job = await runner.store.get("jobs", job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.post("/api/jobs", status_code=201)
async def create_job(
    file: Annotated[UploadFile, File()],
    target_langs: Annotated[str, Form()],
    owns_video: Annotated[bool, Form()] = False,
    voice_profile_id: Annotated[str | None, Form()] = None,
    voice_from_video: Annotated[bool, Form()] = False,
    voice_consent: Annotated[bool, Form()] = False,
    engine: Annotated[str, Form()] = "cloud",   # `gpu` = our own GPU machine for this job (when it is set up)
) -> dict[str, str]:
    if engine not in ("cloud", "gpu"):
        raise HTTPException(400, "engine is cloud or gpu")
    if engine == "gpu" and not get_settings().gpu_mode_ready:
        raise HTTPException(400, "The GPU engine is not set up on this server.")
    if not owns_video:
        raise HTTPException(400, "Confirm you own this video or have permission to dub it.")
    if voice_from_video and not voice_consent:
        raise HTTPException(403, "Copying the voice in this video needs the speaker's consent.")
    langs = parse_langs(target_langs)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type {ext or '(none)'}; use {sorted(ALLOWED_EXT)}")
    if voice_profile_id:
        p = await runner.store.get("voice_profiles", voice_profile_id)
        if not p or p.get("deleted_at"):
            raise HTTPException(404, "voice profile not found")
        if not p.get("consent_at"):
            raise HTTPException(403, "This voice profile has no recorded consent.")
    tmp_dir = get_settings().data_path / "incoming"
    tmp_dir.mkdir(exist_ok=True)
    tmp = tmp_dir / f"{uuid.uuid4()}{ext}"
    size = 0
    with tmp.open("wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                f.close()
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, "File too large (max 500 MB).")
            f.write(chunk)
    try:
        from_video = None
        if voice_from_video and not voice_profile_id:
            from_video = {"consent_at": now_iso(), "consent_text": VIDEO_VOICE_CONSENT}
        job = await runner.create_job(tmp, file.filename or "video", langs, voice_profile_id, from_video,
                                      engine=engine)
    except IngestError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, str(e)) from e
    runner.start(job["id"])
    return {"job_id": job["id"]}


@router.get("/api/jobs")
async def list_jobs() -> list[dict[str, Any]]:
    rows = await runner.store.select("jobs", order="created_at", desc=True, limit=30)
    return [{k: j.get(k) for k in ("id", "source_path", "duration_s", "target_langs", "status", "stage",
                                    "created_at")} for j in rows]


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    return {**(await _job_or_404(job_id)), "engine": runner.job_engine(job_id)}


@router.get("/api/jobs/{job_id}/source")
async def job_source(job_id: str) -> FileResponse:
    """The original upload, for the A/B player (deleted with the job after UPLOAD_TTL_HOURS)."""
    await _job_or_404(job_id)
    d = runner.job_dir(job_id)
    src = next(iter(sorted(d.glob("source.*"))), None) if d.exists() else None
    if not src:
        raise HTTPException(404, "source deleted")
    return FileResponse(src)


@router.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    job = await _job_or_404(job_id)

    async def stream() -> AsyncIterator[str]:
        q = events.subscribe(job_id)
        try:
            yield f"event: snapshot\ndata: {json.dumps(job, default=str)}\n\n"
            if job["status"] in ("done", "failed") and not _busy(job_id):
                yield "event: end\ndata: {}\n\n"
                return
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {ev.get('type', 'message')}\ndata: {json.dumps(ev, default=str)}\n\n"
                if ev.get("type") == "end":
                    return
        finally:
            events.unsubscribe(job_id, q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _busy(job_id: str) -> bool:
    lock = runner._locks.get(job_id)
    return bool(lock and lock.locked())


@router.get("/api/jobs/{job_id}/segments")
async def get_segments(job_id: str, lang: str | None = None) -> list[dict[str, Any]]:
    await _job_or_404(job_id)
    segs = await runner.store.select("segments", order="idx", job_id=job_id)
    trs = await runner.store.select_in("translations", "segment_id", [s["id"] for s in segs],
                                       **({"lang": lang} if lang else {}))
    by_seg: dict[str, list[dict[str, Any]]] = {}
    for t in trs:
        by_seg.setdefault(t["segment_id"], []).append(
            {k: t.get(k) for k in ("id", "lang", "text", "edited", "fit_speed")})
    return [{"id": s["id"], "idx": s["idx"], "start_s": s["start_s"], "end_s": s["end_s"],
             "src_text": s.get("src_text") or "", "translations": by_seg.get(s["id"], [])} for s in segs]


class EditLine(BaseModel):
    text: str


@router.patch("/api/jobs/{job_id}/translations/{tid}")
async def edit_translation(job_id: str, tid: str, body: EditLine) -> dict[str, Any]:
    await _job_or_404(job_id)
    if not body.text.strip():
        raise HTTPException(400, "text is empty")
    try:
        tr = await runner.edit_line(job_id, tid, body.text)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ProviderError as e:
        raise HTTPException(502, f"Re-render failed: {e}") from e
    return {k: tr.get(k) for k in ("id", "lang", "text", "edited", "fit_speed")}


class RenderBody(BaseModel):
    langs: list[str]


@router.post("/api/jobs/{job_id}/render", status_code=202)
async def render_job(job_id: str, body: RenderBody, bg: BackgroundTasks) -> dict[str, Any]:
    job = await _job_or_404(job_id)
    langs = parse_langs(",".join(body.langs))
    if job["status"] in ("queued", "running") or _busy(job_id):
        raise HTTPException(409, "Job is still running.")
    if not await runner.store.select("segments", job_id=job_id):
        raise HTTPException(409, "Job has no transcript yet.")
    runner.start_render(job_id, langs)
    return {"job_id": job_id, "langs": langs}


@router.get("/api/jobs/{job_id}/outputs")
async def get_outputs(job_id: str) -> list[dict[str, Any]]:
    await _job_or_404(job_id)
    out = []
    for r in await runner.store.select("renders", order="lang", job_id=job_id):
        out.append({"lang": r["lang"], "mp4_url": await output_url(job_id, r["mp4_path"]),
                    "srt_url": await output_url(job_id, r["srt_path"]), "created_at": r.get("created_at")})
    return out


@router.get("/files/{job_id}/{name}")
async def local_file(job_id: str, name: str) -> FileResponse:
    """Local-mode download of render outputs only (data/jobs/<id>/out/)."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "bad name")
    try:
        uuid.UUID(job_id)
    except ValueError as e:
        raise HTTPException(404, "not found") from e
    path = runner.job_dir(job_id) / "out" / name
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path, filename=name)


def delete_job_files(job_id: str) -> None:
    shutil.rmtree(runner.job_dir(job_id), ignore_errors=True)
