"""Trace (`V1_TRACE`): one record per Live phrase and language, and one per Studio line.

Records are appended to `<DATA_DIR>/trace/trace-YYYYMMDD.jsonl` and counted in Prometheus metrics. A record says
when each step happened (session clock, ms), which provider did it, whether a fallback answered, and the seconds
of GPU work that were reported or can be bounded. With the flag off nothing here is called.

Live record (kind `live_phrase`), times in ms on the session clock:
  t_speech_ms (the phrase began), t_speech_end, t_stt_final, t_translate_start, t_translated, t_first_audio,
  t_audio_done (last audio sent to viewers), t_heard (when a viewer starts hearing it, estimated by the server)
  and the differences that matter: first_audio_ms, heard_ms, late_ms (sync mode: start after its video moment).
  v1.1: dub_ms (audio sent), dub_raw_ms (the same line at the voice's own pace), slot_ms (the span of the source
  phrase, or of the phrases spoken in one call), dur_ratio = dub_ms / slot_ms, backlog_ms (how far the dub queue
  was behind the video when the phrase's turn came), tgt_words, tgt_chars, and with `V1_LIVE_BUDGET` /
  `V1_LIVE_RATECTRL`: budget_words, budget_chars, budget_ms, est0_ms (the first answer), est_ms (the line spoken), reasked (1 asked, 2 the shorter line was
  used), ctl_scale, ctl_integral, dense, speaking_pct, native (speed asked of the engine).
A viewer's own report arrives later as kind `live_played` with the same `trace_id`.
"""
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prometheus_client import Counter, Histogram

from app.config import get_settings

_lock = threading.Lock()
SECONDS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0)

LIVE_PHRASES = Counter("bd_v1_live_phrases_total", "Live phrases per language", ["lang", "engine", "outcome"])
LIVE_FIRST_AUDIO = Histogram("bd_v1_live_first_audio_seconds", "End of phrase to first dubbed audio",
                             ["lang", "engine"], buckets=SECONDS)
LIVE_LATE = Histogram("bd_v1_live_late_seconds", "Sync mode: dub start after its video moment", ["lang"],
                      buckets=(0.25, 0.5, 1.0, 2.0, 4.0, 8.0))
LIVE_DUR_RATIO = Histogram("bd_v1_live_dur_ratio", "Dubbed audio seconds over source slot seconds", ["lang"],
                           buckets=(0.6, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0))
LIVE_BACKLOG = Histogram("bd_v1_live_backlog_seconds", "How far the dub queue is behind the video at a phrase's turn",
                         ["lang"], buckets=(0.25, 0.5, 1.0, 2.0, 4.0, 8.0))
FALLBACKS = Counter("bd_v1_fallback_total", "Calls answered by a fallback provider", ["stage", "mode"])
GPU_SECONDS = Counter("bd_v1_gpu_seconds_total", "Seconds of work on our GPU servers", ["stage", "mode"])
STUDIO_LINES = Counter("bd_v1_studio_lines_total", "Studio lines voiced", ["lang", "outcome"])
STUDIO_BACKCHECK = Histogram("bd_v1_studio_backcheck_ratio", "Share of a dubbed line's words heard back", ["lang"],
                             buckets=(0.5, 0.7, 0.8, 0.9, 0.95, 1.0))
VENDOR = Counter("bd_v1_vendor_units_total", "Hosted usage: stt seconds, tts characters, llm calls", ["unit", "mode"])


def enabled() -> bool:
    return bool(get_settings().v1_trace)


def trace_dir() -> Path:
    d = get_settings().data_path / "trace"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write(rec: dict[str, Any]) -> None:
    """Append one record. Never raises: a trace must not break a stream or a job."""
    try:
        now = datetime.now(timezone.utc)
        rec = {"ts": now.isoformat(timespec="milliseconds"), **rec}
        line = json.dumps(rec, ensure_ascii=False, default=str)
        with _lock, open(trace_dir() / f"trace-{now:%Y%m%d}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def provider_name(obj: Any) -> str:
    """A short name for a provider object; a fallback pair is `first>second`."""
    if obj is None:
        return "none"
    first, second = getattr(obj, "first", None), getattr(obj, "second", None)
    if first is not None:
        return provider_name(first) + (">" + provider_name(second) if second is not None else "")
    main = getattr(obj, "main", None)
    if main is not None:
        return provider_name(main)
    return str(getattr(obj, "name", "") or type(obj).__name__)


def live_phrase(sid: str, row: dict[str, Any], seq: int, p: dict[str, Any], providers: dict[str, str]) -> None:
    """One record per target language from a finished phrase's timing marks (`LivePipeline._pending[seq]`)."""
    t = p.get("timings") or {}
    engine = row.get("engine") or "cloud"
    end = t.get("t_speech_end")
    langs = sorted({k.split(":", 1)[1] for k in t if ":" in k})
    for lang in langs:
        def g(name: str) -> Any:
            return t.get(f"{name}:{lang}")
        first, heard = g("t_first_audio"), g("t_heard")
        skipped = g("skipped")
        on_gpu_voice = bool(g("gpu"))
        tr0, tr1 = g("t_translate_start"), g("t_translated")
        llm_local = providers.get("llm", "").startswith("LocalLLM") and not g("llm_fb")
        gpu_s = (g("gpu_ms") or 0) / 1000 + ((tr1 - tr0) / 1000 if llm_local and tr0 is not None and tr1 is not None else 0)
        rec = {
            "kind": "live_phrase", "trace_id": f"{sid[:8]}-{seq}-{lang}", "session": sid, "seq": seq, "lang": lang,
            "engine": engine, "streamer": bool(row.get("streamer_id")), "src_words": len((p.get("src_text") or "").split()),
            "t_speech_ms": p.get("t_speech_ms"), "t_speech_end": end, "t_stt_final": t.get("t_stt_final"),
            "t_translate_start": tr0, "t_translated": tr1, "t_first_audio": first, "t_audio_done": g("t_audio_done"),
            "t_heard": heard,
            "first_audio_ms": first - end if first is not None and end is not None else None,
            "heard_ms": heard - end if heard is not None and end is not None else None,
            "translate_ms": tr1 - tr0 if tr0 is not None and tr1 is not None else None,
            "late_ms": g("late"), "skipped": skipped, "merged_into": g("merged"),
            "stt": providers.get("stt"), "llm": providers.get("llm"),
            "tts": "gpu_voice" if on_gpu_voice else "hosted", "clone": bool(g("clone")),
            "fallback": {"stt": bool(t.get("stt_fb")), "llm": bool(g("llm_fb")), "tts": bool(g("tts_fb"))},
            "gpu_s": round(gpu_s, 3), "gpu_voice_ms": g("gpu_ms"), "tempo": g("tempo"), "pace": g("pace"),
            "budget_words": g("budget"), "brief": bool(g("brief")), "shortened": bool(g("shortened")),
            "backcheck": g("backcheck"), "redone": bool(g("redone")), "tts_chars": g("tts_chars"),
            "dub_ms": g("dub_ms"), "dub_raw_ms": g("dub_raw_ms"), "slot_ms": g("slot_ms"), "dur_ratio": g("dur_ratio"),
            "backlog_ms": g("backlog"), "tgt_words": g("tgt_words"), "tgt_chars": g("tgt_chars"),
            "budget_chars": g("budget_chars"), "budget_ms": g("budget_ms"), "est_ms": g("est_ms"), "est0_ms": g("est0_ms"),
            "reasked": g("reasked"), "ctl_scale": g("ctl"), "ctl_integral": g("ctl_i"), "native": g("native"),
            "dense": bool(t.get("dense")), "speaking_pct": t.get("share"),
        }
        write(rec)
        outcome = "skipped" if skipped else "spoken" if first is not None else "silent"
        LIVE_PHRASES.labels(lang, engine, outcome).inc()
        if rec["first_audio_ms"] is not None:
            LIVE_FIRST_AUDIO.labels(lang, engine).observe(max(0, rec["first_audio_ms"]) / 1000)
        if rec["late_ms"] is not None:
            LIVE_LATE.labels(lang).observe(max(0, rec["late_ms"]) / 1000)
        if rec["dur_ratio"] is not None:
            LIVE_DUR_RATIO.labels(lang).observe(rec["dur_ratio"])
        if rec["backlog_ms"] is not None and not skipped:
            LIVE_BACKLOG.labels(lang).observe(rec["backlog_ms"] / 1000)
        for stage, hit in rec["fallback"].items():
            if hit:
                FALLBACKS.labels(stage, "live").inc()
        if g("gpu_ms"):
            GPU_SECONDS.labels("speak", "live").inc(g("gpu_ms") / 1000)
        if gpu_s and llm_local and rec["translate_ms"]:
            GPU_SECONDS.labels("translate", "live").inc(rec["translate_ms"] / 1000)


def live_played(sid: str, seq: int, lang: str, late_ms: int) -> None:
    write({"kind": "live_played", "trace_id": f"{sid[:8]}-{seq}-{lang}", "session": sid, "seq": seq, "lang": lang,
           "played_late_ms": late_ms})


def studio_line(job_id: str, lang: str, idx: int, **fields: Any) -> None:
    """One record per voiced Studio line. `fields`: mode, provider names, ms per step, speed, scores, flagged."""
    write({"kind": "studio_line", "trace_id": f"{job_id[:8]}-{idx}-{lang}", "job": job_id, "idx": idx, "lang": lang,
           **fields})
    STUDIO_LINES.labels(lang, "flagged" if fields.get("flagged") else "ok").inc()
    if isinstance(fields.get("backcheck"), (int, float)):
        STUDIO_BACKCHECK.labels(lang).observe(float(fields["backcheck"]))
    if fields.get("gpu_s"):
        GPU_SECONDS.labels("speak", str(fields.get("mode") or "studio")).inc(float(fields["gpu_s"]))
    if fields.get("fallback"):
        FALLBACKS.labels("speak", str(fields.get("mode") or "studio")).inc()


def studio_job(job_id: str, **fields: Any) -> None:
    """One record per finished Studio run: duration of the video, stage seconds, usage counters."""
    write({"kind": "studio_job", "job": job_id, **fields})
    mode = str(fields.get("mode") or "studio")
    usage = fields.get("usage") or {}
    for unit, key in (("stt_seconds", "stt_audio_s"), ("tts_chars", "tts_chars"), ("llm_calls", "llm_calls")):
        if usage.get(key):
            VENDOR.labels(unit, mode).inc(float(usage[key]))


def event(kind: str, **fields: Any) -> None:
    """Anything else worth a line: a router fallback with its reason, a profile switch."""
    write({"kind": kind, **fields})


def read(hours: float = 24.0, kinds: tuple[str, ...] | None = None, limit: int = 200000) -> list[dict[str, Any]]:
    """Records of the last `hours`, oldest first."""
    since = time.time() - hours * 3600
    out: list[dict[str, Any]] = []
    for path in sorted(trace_dir().glob("trace-*.jsonl"))[-(int(hours // 24) + 2):]:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if kinds and rec.get("kind") not in kinds:
                        continue
                    try:
                        if datetime.fromisoformat(rec["ts"]).timestamp() < since:
                            continue
                    except (KeyError, ValueError):
                        continue
                    out.append(rec)
        except OSError:
            continue
    return out[-limit:]
