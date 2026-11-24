"""Live eval: the same recording through one or more running backends, several runs each, mean and spread.

  python -m eval.v1.live SRC --out DIR --runs 3 --loops 3 --langs ta-IN,bn-IN --engine gpu --voice stream \
      --target base=http://127.0.0.1:8111 --target dynamic=http://127.0.0.1:8112 [--v0 http://127.0.0.1:8010]

Runs are taken in turn (base, dynamic, base, dynamic, ...) so a slow spell of a provider falls on every target, and
never two at once: one GPU through one tunnel is one stream. Before every run the `--v0` backend is asked whether
one of its sessions is live; if so the eval stops (a second stream would spoil both).

Numbers come from the backend itself: `/api/live/sessions/<id>/metrics` (every version) and, where the trace is
on, `/api/v1/metrics/summary?session=<id>`. Nothing is estimated; a missing number stays empty.
"""
import argparse
import asyncio
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

BACKEND = Path(__file__).resolve().parents[2]
KEYS = [  # (name in the result, where it comes from, unit)
    ("first_audio_p50_ms", "metrics.p50_ms", "ms"), ("first_audio_p95_ms", "metrics.p95_ms", "ms"),
    ("heard_p50_ms", "metrics.heard_p50_ms", "ms"), ("on_time_pct", "metrics.sync_on_time_pct", "%"),
    ("within_1s_pct", "trace.within_1s_pct", "%"), ("late_p95_ms", "metrics.sync_late_p95_ms", "ms"),
    ("hold_ms", "metrics.sync_delay_ms", "ms"), ("phrases", "metrics.chunks", ""),
    ("skipped_late", "trace.skipped_late", ""), ("at_speed_limit", "trace.at_speed_limit", ""),
    ("copied_voice_pct", "trace.copied_voice_pct", "%"), ("translate_p50_ms", "trace.translate_p50_ms", "ms"),
    ("session_first_audio_ms", "trace.session_first_audio_ms", "ms"),
    ("shortened", "trace.shortened", ""),
    ("short_lines_joined", "trace.short_lines_joined", ""), ("short_lines_alone", "trace.short_lines_alone", ""),
    ("fallback_llm_pct", "trace.fallback_pct.llm", "%"), ("fallback_tts_pct", "trace.fallback_pct.tts", "%"),
]


def dig(d: Any, path: str) -> Any:
    for part in path.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


async def v0_live(v0: str) -> list[str]:
    if not v0:
        return []
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            rows = (await c.get(v0.rstrip("/") + "/api/live/sessions")).json()
        return [str(r.get("id"))[:8] for r in rows if r.get("status") == "live"]
    except (httpx.HTTPError, ValueError):
        return []   # v0 is not running: nothing to disturb


async def one_run(a: argparse.Namespace, name: str, api: str, k: int) -> dict[str, Any]:
    out = Path(a.out)
    run = f"{name}_r{k}"
    cmd = [sys.executable, "scripts/live_e2e.py", a.src, str(out / "runs"), "--name", run, "--langs", a.langs,
           "--voice", a.voice, "--loops", str(a.loops), "--engine", a.engine, "--api", api]
    if a.sync >= 0:
        cmd += ["--sync", str(a.sync)]
    if a.streamer:
        cmd += ["--streamer", a.streamer]
    proc = await asyncio.to_thread(subprocess.run, cmd, cwd=BACKEND, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
    sid_file = out / "runs" / run / "session.txt"
    sid = sid_file.read_text(encoding="utf-8").strip() if sid_file.exists() else ""
    res: dict[str, Any] = {"target": name, "run": k, "session": sid, "ok": proc.returncode == 0 and bool(sid)}
    if not res["ok"]:
        res["error"] = (proc.stderr or proc.stdout)[-400:]
        return res
    async with httpx.AsyncClient(base_url=api, timeout=30) as c:
        metrics = (await c.get(f"/api/live/sessions/{sid}/metrics")).json()
        trace: dict[str, Any] = {}
        r = await c.get("/api/v1/metrics/summary", params={"hours": 2, "session": sid})
        if r.status_code == 200 and r.json().get("records"):
            trace = r.json()["live"]
    src = {"metrics": metrics, "trace": trace}
    for key, path, _ in KEYS:
        res[key] = dig(src, path)
    errs = [ln for ln in proc.stdout.splitlines() if '"errors"' in ln]
    res["errors"] = len(json.loads(errs[-1]).get("errors") or []) if errs else None
    return res


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"runs": len(rows), "failed": sum(1 for r in rows if not r["ok"])}
    for key, _, _ in KEYS:
        vals = [r[key] for r in rows if r.get("ok") and isinstance(r.get(key), (int, float))]
        out[key] = ({"mean": round(statistics.mean(vals), 1), "min": min(vals), "max": max(vals), "n": len(vals)}
                    if vals else None)
    return out


def table(agg: dict[str, dict[str, Any]]) -> str:
    names = list(agg)
    lines = ["| Measure | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for key, _, unit in KEYS:
        cells = []
        for n in names:
            v = agg[n].get(key)
            cells.append(f"{v['mean']:g} ({v['min']:g}-{v['max']:g})" if v else "not measured")
        if any(c != "not measured" for c in cells):
            lines.append(f"| {key.replace('_', ' ')}{' (' + unit + ')' if unit and unit not in key else ''} | " + " | ".join(cells) + " |")
    lines.append("| runs (failed) | " + " | ".join(f"{agg[n]['runs']} ({agg[n]['failed']})" for n in names) + " |")
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--target", action="append", required=True, help="name=http://host:port (repeat)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--loops", type=int, default=3)
    ap.add_argument("--langs", default="ta-IN,bn-IN")
    ap.add_argument("--engine", default="gpu", choices=["cloud", "gpu"])
    ap.add_argument("--voice", default="stream")
    ap.add_argument("--streamer", default="")
    ap.add_argument("--sync", type=float, default=0.0, help="report video time from this second on; -1 = no sync mode")
    ap.add_argument("--v0", default="http://127.0.0.1:8010", help="stop if this backend has a live session; empty = no check")
    a = ap.parse_args()
    targets = dict(t.split("=", 1) for t in a.target)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for k in range(1, a.runs + 1):
        for name, api in targets.items():
            busy = await v0_live(a.v0)
            if busy:
                print(f"stopped: a v0 session is live ({busy}); no eval beside a real stream")
                break
            res = await one_run(a, name, api, k)
            rows.append(res)
            print(json.dumps({key: res.get(key) for key in ("target", "run", "ok", "first_audio_p50_ms", "on_time_pct",
                                                              "within_1s_pct", "session_first_audio_ms", "skipped_late",
                                                              "error")}), flush=True)
            (out / "runs.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        else:
            continue
        break
    agg = {name: aggregate([r for r in rows if r["target"] == name]) for name in targets}
    setup = {"src": Path(a.src).name, "runs": a.runs, "loops": a.loops, "langs": a.langs, "engine": a.engine,
             "voice": a.voice, "sync": a.sync, "targets": targets}
    (out / "summary.json").write_text(json.dumps({"setup": setup, "targets": agg, "runs": rows}, indent=1), encoding="utf-8")
    (out / "summary.md").write_text(table(agg) + "\n", encoding="utf-8")
    print(table(agg))


if __name__ == "__main__":
    asyncio.run(main())
