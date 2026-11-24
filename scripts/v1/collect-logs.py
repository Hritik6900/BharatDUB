"""Collect the records of every test into logs/, in a form that can be pushed: measurements only.

Reads (never writes) each backend's store file, v1's trace folder and the stream watcher's folder, and writes

  logs/sessions/<version>/<date>_<session>.jsonl   one line per Live phrase and language: every step and its ms
  logs/sessions/index.csv                          one row per session and language: the numbers of that run
  logs/jobs/index.csv                              one row per Studio job: seconds per stage
  logs/trace/                                      v1's trace files (provider and fallback per phrase and line)
  logs/streams/                                    the stream watcher's files (events, rows every 20 s, summaries)

logs/api/ is written by the v1 backend itself while it runs (V1_API_LOG) and is left alone here.

Nothing that was said is copied: no source text, no translation, no voice sample, no voice or token id.

  python scripts/v1/collect-logs.py v0=C:/.../BharatDUB/backend/data/local_db.json v1=data-v1/local_db.json
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDIO_STAGES = ["ingest", "extract", "separate", "segment", "transcribe", "translate", "clone", "voice", "fit",
                 "mix", "render", "_total"]


def pct(values: list[float], p: float) -> float | None:
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))] if v else None


def share(flags: list) -> float | None:
    return round(100 * sum(map(bool, flags)) / len(flags), 1) if flags else None


def table(db: dict, name: str) -> list[dict]:
    rows = db.get(name) or []
    return list(rows.values()) if isinstance(rows, dict) else rows


def diff(t: dict, a: str, b: str) -> int | None:
    return int(t[a] - t[b]) if a in t and b in t else None


def phrase_rows(chunks: list[dict]) -> list[dict]:
    """One record per phrase and language, steps in the order they happen."""
    out = []
    for c in chunks:
        t = c.get("timings") or {}
        base = {"seq": c["seq"], "t_speech_ms": c.get("t_speech_ms"), "src_words": len((c.get("src_text") or "").split()),
                "speech_ms": diff(t, "t_speech_end", "t_speech_ms") if "t_speech_end" in t and c.get("t_speech_ms") is not None
                else None,
                "stt_ms": diff(t, "t_stt_final", "t_speech_end")}
        if base["speech_ms"] is None and "t_speech_end" in t and c.get("t_speech_ms") is not None:
            base["speech_ms"] = int(t["t_speech_end"] - c["t_speech_ms"])
        for lang in sorted({k.split(":", 1)[1] for k in t if k.startswith("t_translated:")}):
            first = f"t_first_audio:{lang}"
            out.append({**base, "lang": lang,
                        "translate_ms": diff(t, f"t_translated:{lang}", "t_stt_final"),
                        "voice_ms": diff(t, first, f"t_translated:{lang}"),
                        "audio_ms": diff(t, f"t_audio_done:{lang}", first),
                        "first_audio_ms": diff(t, first, "t_speech_end"),
                        "heard_ms": diff(t, f"t_heard:{lang}", "t_speech_end"),
                        "late_ms": t.get(f"late:{lang}"), "tempo": t.get(f"tempo:{lang}"),
                        "copied_voice": t.get(f"clone:{lang}"), "on_gpu": t.get(f"gpu:{lang}"),
                        "skipped": t.get(f"skipped:{lang}"),
                        # v1.1 (stored from 24 Nov 2026 on; empty before): lengths, never the words themselves
                        "dub_ms": t.get(f"dub_ms:{lang}"), "dub_raw_ms": t.get(f"dub_raw_ms:{lang}"),
                        "slot_ms": t.get(f"slot_ms:{lang}"), "dur_ratio": t.get(f"dur_ratio:{lang}"),
                        "backlog_ms": t.get(f"backlog:{lang}"), "tgt_words": t.get(f"tgt_words:{lang}"),
                        "tgt_chars": t.get(f"tgt_chars:{lang}"), "budget_ms": t.get(f"budget_ms:{lang}"),
                        "budget_scale": t.get(f"ctl:{lang}"), "reasked": t.get(f"reasked:{lang}"),
                        "merged_into": t.get(f"merged:{lang}")})
    return out


def session_index(version: str, s: dict, chunks: list[dict], rows: list[dict]) -> list[dict]:
    first, last = chunks[0], chunks[-1]
    dur = max(1.0, ((last.get("timings") or {}).get("t_speech_end", last["t_speech_ms"]) - first["t_speech_ms"]) / 1000)
    words = sum(len((c.get("src_text") or "").split()) for c in chunks)
    talk = sum(max(0, ((c.get("timings") or {}).get("t_speech_end", c["t_speech_ms"]) - c["t_speech_ms"])) for c in chunks) / 1000
    common = {"version": version, "date": (s.get("created_at") or "")[:10], "started_utc": (s.get("created_at") or "")[11:19],
              "session": s["id"][:8], "video": s.get("youtube_video_id"), "engine": s.get("engine") or "cloud",
              "voice_from_stream": bool(s.get("voice_from_stream")), "phrases": len(chunks), "minutes": round(dur / 60, 1),
              "speaking_pct": round(100 * talk / dur), "words_per_min": round(words / (dur / 60)),
              "stt_p50_ms": pct([r["stt_ms"] for r in rows if r["stt_ms"] is not None], 50)}
    out = []
    for lang in sorted({r["lang"] for r in rows}):
        spoken = [r for r in rows if r["lang"] == lang and r["first_audio_ms"] is not None]
        if not spoken:
            continue
        late = [r["late_ms"] for r in spoken if r["late_ms"] is not None]
        val = lambda key: [r[key] for r in spoken if r[key] is not None]  # noqa: E731
        out.append({**common, "lang": lang, "spoken": len(spoken),
                    "first_audio_p50_ms": pct(val("first_audio_ms"), 50), "first_audio_p95_ms": pct(val("first_audio_ms"), 95),
                    "translate_p50_ms": pct(val("translate_ms"), 50), "voice_p50_ms": pct(val("voice_ms"), 50),
                    "voice_p95_ms": pct(val("voice_ms"), 95), "heard_p50_ms": pct(val("heard_ms"), 50),
                    "within_250ms_pct": share([x <= 250 for x in late]), "within_1s_pct": share([x <= 1000 for x in late]),
                    "late_p95_ms": pct(late, 95), "copied_voice_pct": share([r["copied_voice"] for r in spoken]),
                    "on_gpu_pct": share([r["on_gpu"] for r in spoken]),
                    "at_speed_limit_pct": share([(r["tempo"] or 1.0) >= 1.295 for r in spoken]),
                    "dur_ratio_p50": pct(val("dur_ratio"), 50), "dur_ratio_p90": pct(val("dur_ratio"), 90),
                    "backlog_p95_ms": pct(val("backlog_ms"), 95),
                    "skipped_late": sum(1 for r in rows if r["lang"] == lang and r["skipped"] == "late")})
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def copy_folder(src: Path, dst: Path, patterns: tuple[str, ...]) -> int:
    n = 0
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for pattern in patterns:
            for f in src.glob(pattern):
                shutil.copyfile(f, dst / f.name)
                n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stores", nargs="+", help="version=path to that backend's store file")
    ap.add_argument("--out", default=str(ROOT / "logs"))
    ap.add_argument("--trace", default=str(ROOT / "data-v1" / "trace"))
    ap.add_argument("--streams", default=str(ROOT / "data-v1" / "streamwatch"))
    a = ap.parse_args()
    out = Path(a.out)
    index, jobs = [], []
    for item in a.stores:
        version, path = item.split("=", 1)
        db = json.loads(Path(path).read_text(encoding="utf-8"))
        by_session: dict[str, list[dict]] = {}
        for c in table(db, "live_chunks"):
            by_session.setdefault(c.get("session_id"), []).append(c)
        n = 0
        for s in sorted(table(db, "live_sessions"), key=lambda s: s.get("created_at") or ""):
            chunks = sorted(by_session.get(s["id"], []), key=lambda c: c["seq"])
            if not chunks:
                continue
            rows = phrase_rows(chunks)
            folder = out / "sessions" / version
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / f"{(s.get('created_at') or 'unknown')[:10]}_{s['id'][:8]}.jsonl").open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=True) + "\n")
            index += session_index(version, s, chunks, rows)
            n += 1
        for j in sorted(table(db, "jobs"), key=lambda j: j.get("created_at") or ""):
            t = j.get("stage_timings") or {}
            jobs.append({"version": version, "date": (j.get("created_at") or "")[:10], "job": j["id"][:8],
                         "status": j.get("status"), "video_s": j.get("duration_s"),
                         "langs": " ".join(j.get("target_langs") or []),
                         **{f"{k.strip('_')}_s": t.get(k) for k in STUDIO_STAGES},
                         "warnings": len(t.get("_warnings") or [])})
        print(f"{version}: {n} live sessions, {len(table(db, 'jobs'))} studio jobs")
    write_csv(out / "sessions" / "index.csv", index)
    write_csv(out / "jobs" / "index.csv", jobs)
    print(f"trace files: {copy_folder(Path(a.trace), out / 'trace', ('*.jsonl',))}, "
          f"stream watch files: {copy_folder(Path(a.streams), out / 'streams', ('*.log', '*.csv', '*.txt'))}")
    print(f"written to {out}")


if __name__ == "__main__":
    main()
