"""Numbers from the trace: `GET /metrics` (Prometheus) and `GET /api/v1/metrics/summary` (the numbers page).

Everything is computed from trace records, so a number exists only if it was measured. Cost is shown only for the
rates that are set in the settings; a rate left at 0 gives no figure.
"""
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Query, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import Settings, get_settings
from app.shared.metrics import percentile
from app.v1 import trace

router = APIRouter()


def _pct(values: list[float], p: float) -> int | None:
    v = percentile(values, p)
    return int(v) if v is not None else None


def _share(hits: int, n: int) -> float | None:
    return round(100 * hits / n, 1) if n else None


def live_summary(recs: list[dict[str, Any]], s: Settings) -> dict[str, Any]:
    phrases = [r for r in recs if r["kind"] == "live_phrase"]
    played = [r["played_late_ms"] for r in recs if r["kind"] == "live_played" and r.get("played_late_ms") is not None]
    heard_langs = [r for r in phrases if r.get("skipped") != "unheard"]   # languages nobody listened to are not dubbed

    def block(rows: list[dict[str, Any]]) -> dict[str, Any]:
        first = [r["first_audio_ms"] for r in rows if r.get("first_audio_ms") is not None]
        heard = [r["heard_ms"] for r in rows if r.get("heard_ms") is not None]
        late = [r["late_ms"] for r in rows if r.get("late_ms") is not None]
        spoken = [r for r in rows if r.get("first_audio_ms") is not None]
        tr = [r["translate_ms"] for r in rows if r.get("translate_ms") is not None]
        return {
            "phrases": len(rows), "spoken": len(spoken),
            "skipped_late": sum(1 for r in rows if r.get("skipped") == "late"),
            "first_audio_p50_ms": _pct(first, 50), "first_audio_p95_ms": _pct(first, 95),
            "heard_p50_ms": _pct(heard, 50), "heard_p95_ms": _pct(heard, 95),
            "translate_p50_ms": _pct(tr, 50),
            "on_time_pct": _share(sum(v <= 250 for v in late), len(late)),
            "within_1s_pct": _share(sum(v <= 1000 for v in late), len(late)),
            "timed": len(late),
            "copied_voice_pct": _share(sum(1 for r in spoken if r.get("clone")), len(spoken)),
            "fallback_pct": {st: _share(sum(1 for r in rows if (r.get("fallback") or {}).get(st)), len(rows))
                             for st in ("stt", "llm", "tts")},
        }

    by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_engine: dict[str, list[dict[str, Any]]] = defaultdict(list)
    spans: dict[str, list[int]] = defaultdict(list)
    for r in heard_langs:
        by_lang[r["lang"]].append(r)
        by_engine[r.get("engine") or "cloud"].append(r)
    for r in phrases:
        for k in ("t_speech_ms", "t_speech_end"):
            if r.get(k) is not None:
                spans[r["session"]].append(r[k])
    minutes = sum((max(v) - min(v)) / 60000 for v in spans.values() if len(v) > 1)
    spoken = [r for r in heard_langs if r.get("first_audio_ms") is not None]
    usage = {
        "stream_minutes": round(minutes, 2), "sessions": len(spans),
        "gpu_seconds": round(sum(r.get("gpu_s") or 0 for r in phrases), 1),
        "hosted_tts_chars": sum(r.get("tts_chars") or 0 for r in spoken if r.get("tts") == "hosted"),
        "hosted_llm_calls": sum(1 for r in phrases if not str(r.get("llm") or "").startswith("LocalLLM")
                                or (r.get("fallback") or {}).get("llm")),
        "hosted_stt_minutes": round(sum((max(v) - min(v)) / 60000 for sid, v in spans.items() if len(v) > 1 and any(
            str(r.get("stt") or "").startswith("GnaniSTT") for r in phrases if r["session"] == sid)), 2),
    }
    return {**block(heard_langs), "per_lang": {k: block(v) for k, v in sorted(by_lang.items())},
            "per_engine": {k: block(v) for k, v in sorted(by_engine.items())},
            "viewer_reports": len(played), "viewer_within_1s_pct": _share(sum(v <= 1000 for v in played), len(played)),
            "usage": usage, "cost": cost(usage, minutes, s)}


def studio_summary(recs: list[dict[str, Any]], s: Settings) -> dict[str, Any]:
    lines = [r for r in recs if r["kind"] == "studio_line"]
    jobs = [r for r in recs if r["kind"] == "studio_job"]
    checks = [r["backcheck"] for r in lines if isinstance(r.get("backcheck"), (int, float))]
    sims = [r["similarity"] for r in lines if isinstance(r.get("similarity"), (int, float))]
    speeds = [r["speed"] for r in lines if isinstance(r.get("speed"), (int, float))]
    minutes = sum((j.get("duration_s") or 0) * max(1, len(j.get("langs") or [])) for j in jobs) / 60
    usage = {
        "dubbed_minutes": round(minutes, 2), "jobs": len(jobs),
        "gpu_seconds": round(sum(r.get("gpu_s") or 0 for r in lines) + sum(j.get("gpu_s") or 0 for j in jobs), 1),
        "hosted_tts_chars": int(sum((j.get("usage") or {}).get("tts_chars", 0) for j in jobs if j.get("tts_hosted", True))),
        "hosted_llm_calls": int(sum((j.get("usage") or {}).get("llm_calls", 0) for j in jobs if j.get("llm_hosted", True))),
        "hosted_stt_minutes": round(sum((j.get("usage") or {}).get("stt_audio_s", 0) for j in jobs if j.get("stt_hosted", True)) / 60, 2),
    }
    return {"jobs": len(jobs), "lines": len(lines), "flagged": sum(1 for r in lines if r.get("flagged")),
            "backcheck_mean_pct": round(100 * sum(checks) / len(checks), 1) if checks else None, "backchecked": len(checks),
            "similarity_mean": round(sum(sims) / len(sims), 3) if sims else None, "similarity_n": len(sims),
            "speed_max": max(speeds) if speeds else None,
            "within_115_pct": _share(sum(v <= 1.151 for v in speeds), len(speeds)),
            "fallback_pct": _share(sum(1 for r in lines if r.get("fallback")), len(lines)),
            "turnaround_p50_s": _pct([j["total_s"] for j in jobs if j.get("total_s")], 50),
            "usage": usage, "cost": cost(usage, minutes, s)}


def cost(usage: dict[str, Any], minutes: float, s: Settings) -> dict[str, Any]:
    """Cost per minute from what was counted, for each rate that is set. No rate, no figure."""
    parts: dict[str, float | None] = {
        "gpu": usage["gpu_seconds"] * s.v1_gpu_rate_per_hour / 3600 if s.v1_gpu_rate_per_hour > 0 else None,
        "hosted_stt": usage["hosted_stt_minutes"] * s.v1_stt_rate_per_min if s.v1_stt_rate_per_min > 0 else None,
        "hosted_tts": usage["hosted_tts_chars"] / 1000 * s.v1_tts_rate_per_1k_chars if s.v1_tts_rate_per_1k_chars > 0 else None,
        "hosted_llm": usage["hosted_llm_calls"] * s.v1_llm_rate_per_call if s.v1_llm_rate_per_call > 0 else None,
    }
    known = [v for v in parts.values() if v is not None]
    return {"currency": s.v1_cost_currency, "rates_set": [k for k, v in parts.items() if v is not None],
            "rates_missing": [k for k, v in parts.items() if v is None],
            "total": round(sum(known), 4) if known else None,
            "per_minute": round(sum(known) / minutes, 4) if known and minutes > 0 else None,
            "parts": {k: round(v, 4) if v is not None else None for k, v in parts.items()}}


@router.get("/metrics")
async def prometheus() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/v1/metrics/summary")
async def summary(hours: float = Query(24.0, gt=0, le=24 * 30), session: str = "") -> dict[str, Any]:
    s = get_settings()
    recs = trace.read(hours) if s.v1_trace or trace.trace_dir().exists() else []
    if session:
        recs = [r for r in recs if r.get("session", "").startswith(session) or r.get("job", "").startswith(session)]
    return {"trace_on": s.v1_trace, "hours": hours, "records": len(recs),
            "live": live_summary(recs, s), "studio": studio_summary(recs, s)}
