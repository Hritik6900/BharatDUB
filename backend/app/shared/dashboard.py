"""GET /api/dashboard: totals from real rows only. Unmeasured values are null (the UI hides them)."""
import statistics
from collections import Counter
from typing import Any

from fastapi import APIRouter

from app.config import LANG_NAMES, get_settings
from app.db import get_store
from app.shared.metrics import percentile

router = APIRouter()


@router.get("/api/dashboard")
async def dashboard() -> dict[str, Any]:
    store = get_store()
    jobs = await store.select("jobs")
    done = [j for j in jobs if j.get("status") in ("done", "expired")]
    renders = await store.select("renders")
    by_job = Counter(r["job_id"] for r in renders)
    minutes = sum((j.get("duration_s") or 0) * by_job.get(j["id"], 0) for j in jobs) / 60
    totals = [j["stage_timings"]["_total"] for j in done if (j.get("stage_timings") or {}).get("_total")]
    langs = Counter(r["lang"] for r in renders)

    chunks = await store.select("live_chunks")
    lat: list[float] = []
    for c in chunks:
        t = c.get("timings") or {}
        end = t.get("t_speech_end")
        for k, v in t.items():
            if k.startswith("t_first_audio:") and end is not None:
                lat.append(v - end)
    sessions = await store.select("live_sessions")
    return {
        "mock_providers": get_settings().mock_providers,
        "studio": {
            "jobs": len(jobs), "jobs_done": len(done),
            "minutes_dubbed": round(minutes, 2) if renders else None,
            "median_turnaround_s": round(statistics.median(totals), 1) if totals else None,
            "languages": dict(langs),
        },
        "live": {
            "sessions": len(sessions), "chunks": len(chunks),
            "p50_ms": round(percentile(lat, 50)) if lat else None,
            "p95_ms": round(percentile(lat, 95)) if lat else None,
        },
        "languages_supported": len(LANG_NAMES),
    }
