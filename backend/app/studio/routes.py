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
from app.v1.queue import JobQueue
from app.studio.runner import runner
from app.studio.stages.extract import IngestError

router = APIRouter()
hq_queue = JobQueue("hq:held")   # v1: HQ jobs created with hold=true, waiting for a batch run
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
    quality: Annotated[str, Form()] = "standard",   # v1: `hq` = the HQ path (needs V1_STUDIO_HQ)
    hold: Annotated[bool, Form()] = False,          # v1 HQ: wait for a batch run instead of starting now
) -> dict[str, str]:
    if engine not in ("cloud", "gpu"):
        raise HTTPException(400, "engine is cloud or gpu")
    if engine == "gpu" and not get_settings().gpu_mode_ready:
        raise HTTPException(400, "The GPU engine is not set up on this server.")
    if quality not in ("standard", "hq"):
        raise HTTPException(400, "quality is standard or hq")
    if quality == "hq" and not get_settings().v1_studio_hq:
        raise HTTPException(400, "The HQ path is not switched on on this server.")
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
                                      engine=engine, quality=quality)
    except IngestError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, str(e)) from e
    if hold and quality == "hq":
        await hq_queue.push(job["id"])
        return {"job_id": job["id"], "held": "true"}
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
            {**{k: t.get(k) for k in ("id", "lang", "text", "edited", "fit_speed")}, **_hq_fields(t)})
    return [{"id": s["id"], "idx": s["idx"], "start_s": s["start_s"], "end_s": s["end_s"],
             "src_text": s.get("src_text") or "", "translations": by_seg.get(s["id"], []),
             **({"speaker": s["speaker"]} if s.get("speaker") else {})} for s in segs]


def _hq_fields(t: dict[str, Any]) -> dict[str, Any]:
    """v1 HQ: what the editor shows for a line (present only on lines the HQ path voiced)."""
    if "alts" not in t:
        return {}
    keep = ("idx", "provider", "text", "dur_s", "speed", "backcheck", "similarity", "passed", "why")
    if get_settings().v1_hq_judge:
        keep += ("scored_by",)     # who judged each take; what was heard stays on the server
    return {"flagged": bool(t.get("flagged")), "flag_reason": t.get("flag_reason") or "", "qa": t.get("qa"),
            "picked": t.get("picked"), "alts": [{k: a.get(k) for k in keep} for a in t.get("alts") or []]}


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


class PickVersion(BaseModel):
    alt: int


@router.post("/api/jobs/{job_id}/translations/{tid}/pick")
async def pick_version(job_id: str, tid: str, body: PickVersion) -> dict[str, Any]:
    """v1 HQ: use another version of this line that was already made; the language is mixed and rendered again."""
    await _job_or_404(job_id)
    if _busy(job_id):
        raise HTTPException(409, "Job is still running.")
    try:
        tr = await runner.pick_version(job_id, tid, body.alt)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {**{k: tr.get(k) for k in ("id", "lang", "text", "edited", "fit_speed")}, **_hq_fields(tr)}


@router.get("/api/jobs/{job_id}/translations/{tid}/alts/{alt}")
async def version_audio(job_id: str, tid: str, alt: int) -> FileResponse:
    """v1 HQ: one version of a line, to listen to before picking it."""
    await _job_or_404(job_id)
    tr = await runner.store.get("translations", tid)
    seg = await runner.store.get("segments", tr["segment_id"]) if tr else None
    row = next((a for a in (tr or {}).get("alts") or [] if a.get("idx") == alt), None)
    if not seg or seg["job_id"] != job_id or not row:
        raise HTTPException(404, "not found")
    path = Path(row["path"]).resolve()
    if get_settings().data_path.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="audio/wav")


class HQBatch(BaseModel):
    job_ids: list[str] | None = None   # None = every HQ job that is waiting


@router.post("/api/v1/hq/batch", status_code=202)
async def hq_batch(body: HQBatch, bg: BackgroundTasks) -> dict[str, Any]:
    """v1 HQ: run the waiting HQ jobs phase by phase (audio for all, text for all, voice for all)."""
    if not get_settings().v1_studio_hq:
        raise HTTPException(400, "The HQ path is not switched on on this server.")
    waiting = await hq_queue.take_all()
    ids = [j for j in (body.job_ids or waiting)]
    for j in waiting:
        if j not in ids:
            await hq_queue.push(j)   # not asked for now: it keeps waiting
    if not ids:
        raise HTTPException(409, "No HQ job is waiting.")
    bg.add_task(runner.run_hq_batch, ids)
    return {"job_ids": ids}


@router.get("/api/v1/hq/waiting")
async def hq_waiting() -> dict[str, int]:
    return {"waiting": await hq_queue.size()}


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


@router.get("/api/v1/jobs/{job_id}/backcheck")
async def job_backcheck(job_id: str, lang: str) -> dict[str, Any]:
    """v1 eval: hear every dubbed line of one language back (the audio that is in the video, after fitting) and
    report the share of its words that were understood. Works for standard and HQ jobs alike, so the two can be
    compared with the same ear. Scores are cached by the line's audio."""
    from app.shared import audio_utils as au
    from app.shared import cache
    from app.v1.stages import StageFailed, Stages
    await _job_or_404(job_id)
    st = Stages("studio_hq", runner.job_engine(job_id), key=job_id)
    segs = await runner.store.select("segments", order="idx", job_id=job_id)
    trs = {t["segment_id"]: t for t in await runner.store.select_in("translations", "segment_id", [s["id"] for s in segs], lang=lang)}
    lines: list[dict[str, Any]] = []
    for s in segs:
        t = trs.get(s["id"])
        path = runner.job_dir(job_id) / str(t.get("audio_path")) if t and t.get("audio_path") else None
        if not t or path is None or not path.is_file():
            continue
        key = au.cache_key("eval-backcheck-1", au.sha256_file(path), t["text"], lang, ",".join(st.judges(lang)))
        got = cache.get_json("score_eval", key)
        if got is None:
            try:
                got = await st.score(path, t["text"], lang)
                cache.put_json("score_eval", key, got)
            except StageFailed as e:
                got = {"backcheck": None, "by": "", "error": str(e)[:160]}
        from app.v1.qa import heard_share, rule_now
        if got.get("backcheck") is not None and "heard" in got and got.get("rule") != rule_now():
            got = {**got, "backcheck": round(heard_share(t["text"], got["heard"], rule_now()), 3)}
        lines.append({"idx": s["idx"], "words": len(t["text"].split()), "backcheck": got.get("backcheck"),
                      "by": got.get("by"), "fit_speed": t.get("fit_speed"), "flagged": bool(t.get("flagged")),
                      "takes": len(t.get("alts") or []) or 1})
    scored = [x for x in lines if x["backcheck"] is not None]
    words = sum(x["words"] for x in scored)
    judges: dict[str, int] = {}
    for x in scored:
        judges[str(x["by"] or "")] = judges.get(str(x["by"] or ""), 0) + 1
    return {"job_id": job_id, "lang": lang, "lines": lines, "scored": len(scored), "judges": judges, "rule": rule_now(),
            "backcheck_mean": round(sum(x["backcheck"] for x in scored) / len(scored), 4) if scored else None,
            "backcheck_by_words": round(sum(x["backcheck"] * x["words"] for x in scored) / words, 4) if words else None,
            "speed_max": max((x["fit_speed"] or 1.0 for x in lines), default=None),
            "flagged": sum(1 for x in lines if x["flagged"]), "takes": sum(x["takes"] for x in lines)}


# ---------- v1.1: calibrating the heard-back judge (V1_HQ_CALIBRATE) ----------
def _calibrate_on() -> None:
    if not get_settings().v1_hq_calibrate:
        raise HTTPException(404, "The calibration page is switched off (V1_HQ_CALIBRATE).")


class CalibrationLabel(BaseModel):
    id: str
    label: str      # good | bad | undo


@router.get("/api/v1/calibrate/next")
async def calibrate_next(lang: str | None = None, n: int = 10) -> dict[str, Any]:
    """Takes to label, blind: the id, the language and the words the take should say. Never a score."""
    _calibrate_on()
    from app.v1.hq import calibrate
    its = await calibrate.items(runner.store)
    done = set(calibrate.labels())
    return {"items": [calibrate.blind(i) for i in calibrate.queue(its, done, lang, max(1, min(n, 50)))],
            "takes": len(its), "labelled": len(done & {i["id"] for i in its}),
            "langs": sorted({str(i["lang"]) for i in its})}


@router.get("/api/v1/calibrate/audio/{item_id}")
async def calibrate_audio(item_id: str) -> FileResponse:
    _calibrate_on()
    from app.v1.hq import calibrate
    item = next((i for i in await calibrate.items(runner.store) if i["id"] == item_id), None)
    if item is None:
        raise HTTPException(404, "not found")
    return FileResponse(item["path"], media_type="audio/wav", headers={"Cache-Control": "no-store"})


@router.post("/api/v1/calibrate/labels")
async def calibrate_label(body: CalibrationLabel) -> dict[str, Any]:
    _calibrate_on()
    from app.v1.hq import calibrate
    if body.label not in (*calibrate.LABELS, "undo"):
        raise HTTPException(400, "label is good, bad or undo")
    item = next((i for i in await calibrate.items(runner.store) if i["id"] == body.id), None)
    if item is None:
        raise HTTPException(404, "not found")
    calibrate.add_label(item, body.label)
    return {"ok": True, "labelled": len(calibrate.labels())}


@router.get("/api/v1/calibrate/summary")
async def calibrate_summary() -> dict[str, Any]:
    """Agreement between the labels and the judge, and the flag threshold the labels point to (or why none)."""
    _calibrate_on()
    from app.v1.hq import calibrate
    return await calibrate.summary(runner.store)


# ---------- v1.1: glossary candidates from a job's transcript (V1_HQ_AUTO_GLOSSARY) ----------
@router.get("/api/v1/jobs/{job_id}/glossary-candidates")
async def glossary_candidates(job_id: str) -> dict[str, Any]:
    """Names, brands and repeated English terms found in this job's transcript. Proposals: nothing is saved."""
    if not get_settings().v1_hq_auto_glossary:
        raise HTTPException(404, "Glossary candidates are switched off (V1_HQ_AUTO_GLOSSARY).")
    await _job_or_404(job_id)
    from app.v1.hq import glossary as hqgloss
    segs = await runner.store.select("segments", order="idx", job_id=job_id)
    lines = [s.get("src_text_raw") or s.get("src_text") or "" for s in segs]
    known = await runner.glossary()
    return {"job_id": job_id, "candidates": hqgloss.candidates([t for t in lines if t.strip()], known=known,
                                                               limit=get_settings().v1_hq_auto_glossary_max)}
