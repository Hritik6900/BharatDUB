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
from app.v1 import mode as v1mode

router = APIRouter()


def _pct(values: list[float], p: float) -> int | None:
    v = percentile(values, p)
    return int(v) if v is not None else None


def _share(hits: int, n: int) -> float | None:
    return round(100 * hits / n, 1) if n else None


def _ratio(values: list[float], p: float) -> float | None:
    v = percentile(values, p)
    return round(float(v), 2) if v is not None else None


def _talk(phrases: list[dict[str, Any]]) -> dict[str, Any]:
    """Speaking share and words a minute over the sessions in `phrases` (one record per phrase, any language)."""
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    for r in phrases:
        if r.get("t_speech_ms") is not None and r.get("t_speech_end") is not None:
            seen[(r["session"], r["seq"])] = r
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (sid, _), r in seen.items():
        by[sid].append(r)
    span = sum(max(r["t_speech_end"] for r in v) - min(r["t_speech_ms"] for r in v) for v in by.values())
    talk = sum(max(0, r["t_speech_end"] - r["t_speech_ms"]) for r in seen.values())
    words = sum(r.get("src_words") or 0 for r in seen.values())
    if span <= 0:
        return {"speaking_pct": None, "words_per_min": None}
    return {"speaking_pct": round(100 * talk / span, 1), "words_per_min": round(words / (span / 60000))}


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
        ratio = [r["dur_ratio"] for r in rows if r.get("dur_ratio") is not None]
        backlog = [r["backlog_ms"] for r in rows if r.get("backlog_ms") is not None and r.get("skipped") != "unheard"]
        planned = [r for r in rows if r.get("budget_ms")]
        return {
            # v1.1: the dub's length against its slot, and how far the dub queue was behind the video.
            "dur_ratio_p50": _ratio(ratio, 50), "dur_ratio_p90": _ratio(ratio, 90), "dur_ratio_n": len(ratio),
            "dur_ratio_over_1_pct": _share(sum(v > 1.0 for v in ratio), len(ratio)),
            "backlog_p50_ms": _pct(backlog, 50), "backlog_p95_ms": _pct(backlog, 95),
            "at_1_3x": sum(1 for r in rows if 1.295 <= (r.get("tempo") or 0) < 1.395),
            "at_1_4x": sum(1 for r in rows if (r.get("tempo") or 0) >= 1.395),
            "sped_up": sum(1 for r in rows if (r.get("tempo") or 0) > 1.03),
            # the translator's first answer against the duration it was given (1.0 = exactly the budget)
            "first_answer_over_budget_p50": _ratio([r["est0_ms"] / r["budget_ms"] for r in planned if r.get("est0_ms")], 50),
            "budgeted": len(planned), "reasked": sum(1 for r in rows if r.get("reasked")),
            "reask_used": sum(1 for r in rows if r.get("reasked") == 2),
            "dense_phrases": sum(1 for r in rows if r.get("dense")),
            # v1.2: the auto budget, the guards, and lines a voice refused
            "budget_auto_on": sum(1 for r in rows if r.get("budget_auto") is True),
            "budget_auto_off": sum(1 for r in rows if r.get("budget_auto") is False),
            "guard_script_failed": sum(1 for r in rows if r.get("guard_script")),
            "guard_script_flagged": sum(1 for r in rows if r.get("guard_script") == "flagged"),
            "src_script_failed": sum(1 for r in rows if r.get("src_script_ok") is False),
            "voice_fallback": sum(1 for r in rows if r.get("voice_fallback")),
            "unspoken": sum(1 for r in rows if r.get("unspoken")),
            "silent_unmarked": sum(1 for r in rows if r.get("first_audio_ms") is None and not r.get("skipped")
                                   and not r.get("unspoken")),
            "judged": sum(1 for r in rows if r.get("judged")),
            "budget_scale_mean": round(sum(r["ctl_scale"] for r in planned if r.get("ctl_scale")) / len(planned), 2) if planned else None,
            "phrases": len(rows), "spoken": len(spoken),
            "skipped_late": sum(1 for r in rows if r.get("skipped") == "late"),
            "first_audio_p50_ms": _pct(first, 50), "first_audio_p95_ms": _pct(first, 95),
            "heard_p50_ms": _pct(heard, 50), "heard_p95_ms": _pct(heard, 95),
            "translate_p50_ms": _pct(tr, 50),
            "on_time_pct": _share(sum(v <= 250 for v in late), len(late)),
            "within_1s_pct": _share(sum(v <= 1000 for v in late), len(late)),
            "timed": len(late),
            "copied_voice_pct": _share(sum(1 for r in spoken if r.get("clone")), len(spoken)),
            "shortened": sum(1 for r in rows if r.get("shortened")),
            "at_speed_limit": sum(1 for r in rows if (r.get("tempo") or 0) >= 1.19),
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
    # From the first word of a session to its first dubbed audio, per session (what a short first phrase is for).
    starts: dict[str, list[int]] = defaultdict(list)
    firsts: dict[str, list[int]] = defaultdict(list)
    for r in phrases:
        if r.get("t_speech_ms") is not None:
            starts[r["session"]].append(r["t_speech_ms"])
        if r.get("t_first_audio") is not None:
            firsts[r["session"]].append(r["t_first_audio"])
    opening = [min(firsts[sid]) - min(starts[sid]) for sid in firsts if starts.get(sid)]
    ends = [r for r in recs if r["kind"] == "live_session_end"]

    def total(key: str) -> int | None:
        vals = [r[key] for r in ends if r.get(key) is not None]
        return sum(vals) if vals else None
    usage = {
        "stream_minutes": round(minutes, 2), "sessions": len(spans), **_talk(phrases),
        "gpu_seconds": round(sum(r.get("gpu_s") or 0 for r in phrases), 1),
        "hosted_tts_chars": sum(r.get("tts_chars") or 0 for r in spoken if r.get("tts") == "hosted"),
        "hosted_llm_calls": sum(1 for r in phrases if not str(r.get("llm") or "").startswith("LocalLLM")
                                or (r.get("fallback") or {}).get("llm")),
        "hosted_stt_minutes": round(sum((max(v) - min(v)) / 60000 for sid, v in spans.items() if len(v) > 1 and any(
            str(r.get("stt") or "").startswith("GnaniSTT") for r in phrases if r["session"] == sid)), 2),
    }
    # v1.2: the meaning check judges a SAMPLE of the spoken lines after the fact (kind `live_meaning`); `lost` is
    # counted on the judged lines that were translated under the budget, `shifted` on every judged line.
    verdicts = [r for r in recs if r["kind"] == "live_meaning"]

    def judged(rows: list[dict[str, Any]]) -> dict[str, Any]:
        tight = [r for r in rows if r.get("budgeted")]
        return {"judged": len(rows), "shifted": sum(1 for r in rows if r.get("shift")),
                "shift_pct": _share(sum(1 for r in rows if r.get("shift")), len(rows)),
                "judged_budgeted": len(tight), "lost_budgeted": sum(1 for r in tight if r.get("lost")),
                "loss_pct": _share(sum(1 for r in tight if r.get("lost")), len(tight)),
                "lost_any": sum(1 for r in rows if r.get("lost"))}
    per_lang = {k: block(v) for k, v in sorted(by_lang.items())}
    for lg, b in per_lang.items():
        b["meaning"] = judged([r for r in verdicts if r.get("lang") == lg])
    steps = [r for r in recs if r["kind"] == "live_budget_adjust"]
    return {**block(heard_langs), "per_lang": per_lang,
            "meaning": judged(verdicts),
            "budget_switches": sum(1 for r in recs if r["kind"] == "live_auto_budget"),
            "budget_looser": sum(1 for r in steps if (r.get("steps") or 0) > (r.get("was") or 0)),
            "budget_tighter": sum(1 for r in steps if (r.get("steps") or 0) < (r.get("was") or 0)),
            "en_voice": [{"session": r.get("session"), "voice": r.get("mode"), "why": r.get("why"),
                          "probe_ms": r.get("probe_ms"), "available_ms": r.get("available_ms")}
                         for r in recs if r["kind"] == "live_en_voice"],
            "per_engine": {k: block(v) for k, v in sorted(by_engine.items())},
            "session_first_audio_ms": _pct(opening, 50),
            "short_lines_joined": total("merged"), "short_lines_alone": total("short_alone"),
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
        "gpu_seconds_lines": sum(1 for r in lines if r.get("gpu_s")),   # lines whose voice time the engine reported
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
    recs = trace.read(hours) if v1mode.on("trace", s) or trace.trace_dir().exists() else []
    if session:
        recs = [r for r in recs if r.get("session", "").startswith(session) or r.get("job", "").startswith(session)]
    return {"trace_on": v1mode.on("trace", s), "hours": hours, "records": len(recs),
            "live": live_summary(recs, s), "studio": studio_summary(recs, s)}
