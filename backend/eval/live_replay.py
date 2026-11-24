"""Deterministic Live replay: a recording's sound and clock into the Live pipeline in real time, no YouTube.

  python -m eval.live_replay SRC --out DIR --target off=http://127.0.0.1:8111 --target budget=http://127.0.0.1:8112 \
      --runs 5 --langs pa-IN,ta-IN --engine gpu --voice stream [--loops 8 --gap-ms 400] [--max-s 1200] [--keep-audio]

SRC is any file ffmpeg reads (a 10-20 minute recording is fine: about 2 MB of sound a minute in memory). It is
fed to `/ws/ingest` as the console feeds it: 16 kHz frames of 32 ms at real-time pace, with the video's time every
0.5 s (sync mode), so every run of the same file gives the pipeline the same input at the same moments. A viewer
listens on every language. `--loops N` plays a short file N times with `--gap-ms` of silence between, and
`--lead-s` of silence comes first (default 6 s: the session's speech-to-text connection is open before the first word).

Targets are running backends (comparison backends on 8111 and up: scripts/v1/ab-server.*). Runs are taken in turn
(a, b, c, a, b, c ...) so a slow spell of the link or of a hosted service lands on every setting, and never two at
once: one GPU is one stream. Before every run each `--busy` backend is asked for live sessions; while one is live
the run waits (asked again every 60 s, up to `--busy-wait-min`), then is skipped and reported as skipped.

Numbers come from the backend: `/api/live/sessions/<id>/metrics` and the trace summary
`/api/v1/metrics/summary?session=<id>` (the comparison backends run with the trace on). Nothing is estimated here.
Per run: `runs/<target>_r<k>/run.json` (numbers, every caption with its source line, errors) and, with
`--keep-audio`, one WAV per dubbed phrase. Over the runs: `summary.json` and `summary.md` (mean, lowest-highest).
"""
import argparse
import asyncio
import base64
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import soundfile as sf
import websockets

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.shared.audio_utils import ffmpeg_bin  # noqa: E402

FRAME, FRAME_S = 1024, 0.032        # bytes and seconds of one 16 kHz PCM16 frame
# (name in the report, path in {"metrics": ..., "trace": ...}, unit)
KEYS = [
    ("phrases", "metrics.chunks", ""), ("spoken", "trace.spoken", ""),
    ("speaking share", "trace.usage.speaking_pct", "%"), ("source words a minute", "trace.usage.words_per_min", ""),
    ("first audio p50", "metrics.p50_ms", "ms"), ("first audio p95", "metrics.p95_ms", "ms"),
    ("within 0.25 s", "trace.on_time_pct", "%"), ("within 1 s", "trace.within_1s_pct", "%"),
    ("dur_ratio p50", "trace.dur_ratio_p50", ""), ("dur_ratio p90", "trace.dur_ratio_p90", ""),
    ("longer than its slot", "trace.dur_ratio_over_1_pct", "%"),
    ("backlog p50", "trace.backlog_p50_ms", "ms"), ("backlog p95", "trace.backlog_p95_ms", "ms"),
    ("skipped as too late", "trace.skipped_late", ""), ("skips per 10 min", "derived.skips_per_10min", ""),
    ("sped up at all", "trace.sped_up", ""), ("at 1.3x", "trace.at_1_3x", ""), ("at 1.4x", "trace.at_1_4x", ""),
    ("copied voice", "trace.copied_voice_pct", "%"), ("hold at the end", "metrics.sync_delay_ms", "ms"),
    ("translation p50", "trace.translate_p50_ms", "ms"), ("budgeted phrases", "trace.budgeted", ""),
    ("first answer / budget p50", "trace.first_answer_over_budget_p50", ""), ("asked to shorten", "trace.reasked", ""), ("shorter line used", "trace.reask_used", ""),
    ("budget scale mean", "trace.budget_scale_mean", ""), ("dense phrases", "trace.dense_phrases", ""),
    ("native speed lines", "trace.native_speed", ""),
]
PER_LANG = [("within 0.25 s", "on_time_pct", "%"), ("within 1 s", "within_1s_pct", "%"),
            ("dur_ratio p50", "dur_ratio_p50", ""), ("dur_ratio p90", "dur_ratio_p90", ""),
            ("backlog p95", "backlog_p95_ms", "ms"), ("skipped as too late", "skipped_late", ""),
            ("at 1.3x", "at_1_3x", ""), ("at 1.4x", "at_1_4x", ""), ("first audio p50", "first_audio_p50_ms", "ms")]


def dig(d: Any, path: str) -> Any:
    for part in path.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


def decode(src: str, max_s: float = 0.0) -> bytes:
    cmd = [ffmpeg_bin(), "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "16000", "-f", "s16le"]
    if max_s > 0:
        cmd += ["-t", str(max_s)]
    return subprocess.run([*cmd, "-"], check=True, capture_output=True).stdout


def build_feed(pcm: bytes, loops: int, gap_ms: int, lead_s: float = 0.0) -> bytes:
    gap = b"\x00" * (FRAME * max(0, round(gap_ms / 32)))
    lead = b"\x00" * (FRAME * max(0, round(lead_s / FRAME_S)))       # the recogniser's connection opens meanwhile
    feed = lead + (pcm + gap) * max(1, loops) + b"\x00" * (FRAME * 94)   # 3 s of silence closes the last line
    return feed[: len(feed) // FRAME * FRAME]


async def live_on(urls: list[str]) -> list[str]:
    """Sessions that are live on the backends that must not be disturbed."""
    out = []
    async with httpx.AsyncClient(timeout=8) as c:
        for u in urls:
            try:
                rows = (await c.get(u.rstrip("/") + "/api/live/sessions")).json()
                out += [f"{u} {str(r.get('id'))[:8]}" for r in rows if r.get("status") == "live"]
            except (httpx.HTTPError, ValueError):
                continue    # not running: nothing to disturb
    return out


async def wait_free(urls: list[str], wait_min: float) -> list[str]:
    """[] when no stream is live; else waits, asking every 60 s, and returns who is still live at the end."""
    deadline = time.monotonic() + wait_min * 60
    while True:
        busy = await live_on(urls)
        if not busy or time.monotonic() >= deadline:
            return busy
        print(f"waiting: a stream is live ({', '.join(busy)})", flush=True)
        await asyncio.sleep(60)


async def replay(api: str, feed: bytes, langs: list[str], out: Path, *, engine: str, voice: str, streamer: str,
                 sync: bool, keep_audio: bool, tail_s: float) -> dict[str, Any]:
    """One session: create, feed in real time, wait for the last phrase, read the numbers, stop."""
    out.mkdir(parents=True, exist_ok=True)
    ws_base = api.replace("http", "ws", 1)
    body: dict[str, Any] = {"youtube_video_id": "", "target_langs": langs}
    if streamer:
        body |= {"streamer_id": streamer, "voice_mode": "stock" if voice == "stock" else "clone"}
    elif voice == "stream":
        body |= {"voice_from_stream": True, "voice_consent": True}   # the consent the recording's owner gave
    elif voice != "stock":
        body["voice_profile_id"] = voice
    if engine == "gpu":
        body["engine"] = "gpu"
    async with httpx.AsyncClient(base_url=api, timeout=60) as http:
        r = await http.post("/api/live/sessions", json=body)
        r.raise_for_status()
        sid, token = r.json()["session_id"], r.json()["ingest_token"]
        (out / "session.txt").write_text(sid, encoding="utf-8")
        captions: dict[tuple[str, int], str] = {}
        done: set[tuple[str, int]] = set()
        audio: dict[tuple[str, int], bytearray] = {}
        rates: dict[str, int] = {}
        errors: list[str] = []
        last_event = [time.monotonic()]
        stop = asyncio.Event()

        async def watch(ch: str) -> None:
            async with websockets.connect(f"{ws_base}/ws/watch/{sid}?lang={ch}", max_size=None) as ws:
                while not stop.is_set():
                    try:
                        m = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
                    except TimeoutError:
                        continue
                    except websockets.ConnectionClosed:
                        return
                    kind = m.get("type")
                    if kind == "caption":
                        captions[(m.get("lang") or ch, m["seq"])] = m.get("text") or ""
                        last_event[0] = time.monotonic()
                    elif kind == "audio" and ch != "src":
                        last_event[0] = time.monotonic()
                        if m.get("last"):
                            done.add((m["lang"], m["seq"]))
                        elif m.get("pcm_b64") and keep_audio:
                            rates[m["lang"]] = m["sample_rate"]
                            audio.setdefault((m["lang"], m["seq"]), bytearray()).extend(base64.b64decode(m["pcm_b64"]))
                    elif kind == "error" and ch == langs[0] and str(m.get("message"))[:200] not in errors:
                        errors.append(str(m.get("message"))[:200])

        async def console() -> None:
            """The console's feed (`*`): the pipeline's error messages go only there (a voice or a translation
            that failed for one line). It is not a viewer: no audio is made for it."""
            async with websockets.connect(f"{ws_base}/ws/watch/{sid}?lang=%2A", max_size=None) as ws:
                while not stop.is_set():
                    try:
                        m = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
                    except TimeoutError:
                        continue
                    except websockets.ConnectionClosed:
                        return
                    if m.get("type") == "error":
                        errors.append(str(m.get("message"))[:200])

        tasks = [asyncio.create_task(watch(ch)) for ch in [*langs, "src"]] + [asyncio.create_task(console())]
        await asyncio.sleep(0.5)
        async with websockets.connect(f"{ws_base}/ws/ingest/{sid}?token={token}", max_size=None) as ws:
            t0 = time.monotonic()

            async def media() -> None:      # what the console sends while its video plays
                while True:
                    await ws.send(json.dumps({"type": "media", "t": time.monotonic() - t0, "playing": True}))
                    await asyncio.sleep(0.5)
            clock = asyncio.create_task(media()) if sync else None
            for i in range(0, len(feed), FRAME):
                await ws.send(feed[i:i + FRAME])
                delay = t0 + (i // FRAME + 1) * FRAME_S - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
            fed_s = time.monotonic() - t0
            deadline = time.monotonic() + tail_s
            while time.monotonic() < deadline:      # silence until every phrase is closed in every language
                seqs = {q for (lg, q) in captions if lg in langs}
                if seqs and all((lg, q) in done for lg in langs for q in seqs) and time.monotonic() - last_event[0] > 4:
                    break
                await ws.send(b"\x00" * FRAME)
                await asyncio.sleep(FRAME_S)
            if clock:
                clock.cancel()
        metrics = (await http.get(f"/api/live/sessions/{sid}/metrics")).json()
        await http.post(f"/api/live/sessions/{sid}/stop")
        await asyncio.sleep(1.5)
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        tr: dict[str, Any] = {}
        got = await http.get("/api/v1/metrics/summary", params={"hours": 3, "session": sid})
        if got.status_code == 200 and got.json().get("records"):
            tr = got.json()["live"]
    if keep_audio:
        for (lg, seq), b in sorted(audio.items()):
            sf.write(out / f"{lg}_{seq:04d}.wav", np.frombuffer(bytes(b), dtype="<i2"), rates[lg], subtype="PCM_16")
    minutes = dig(tr, "usage.stream_minutes") or 0
    skips = tr.get("skipped_late")
    lines = [{"seq": q, "lang": lg, "src": captions.get(("src", q), ""), "text": text}
             for (lg, q), text in sorted(captions.items(), key=lambda kv: (kv[0][1], kv[0][0])) if lg in langs]
    res = {"session": sid, "fed_s": round(fed_s, 1), "feed_s": round(len(feed) / 32000, 1), "metrics": metrics, "trace": tr,
           "derived": {"skips_per_10min": round(skips / minutes * 10, 2) if skips is not None and minutes else None},
           "errors": errors, "lines": lines}
    (out / "run.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def flatten(res: dict[str, Any], langs: list[str]) -> dict[str, Any]:
    row = {name: dig(res, path) for name, path, _ in KEYS}
    for lg in langs:
        for name, key, _ in PER_LANG:
            row[f"{lg} {name}"] = dig(res, f"trace.per_lang.{lg}.{key}")
    return row


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in dict.fromkeys(k for r in rows for k in r):
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool)]
        out[key] = ({"mean": round(statistics.mean(vals), 2), "min": min(vals), "max": max(vals),
                     "sd": round(statistics.stdev(vals), 2) if len(vals) > 1 else 0.0, "n": len(vals)} if vals else None)
    return out


def table(agg: dict[str, dict[str, Any]], units: dict[str, str]) -> str:
    names = list(agg)
    keys = list(dict.fromkeys(k for a in agg.values() for k in a))
    lines = ["| Measure | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for key in keys:
        cells = []
        for n in names:
            v = agg[n].get(key)
            cells.append(f"{v['mean']:g} ({v['min']:g}-{v['max']:g})" if v else "not measured")
        if any(c != "not measured" for c in cells):
            unit = units.get(key, "")
            lines.append(f"| {key}{' (' + unit + ')' if unit else ''} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--target", action="append", required=True, help="name=http://host:port (repeat)")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--langs", default="pa-IN,ta-IN")
    ap.add_argument("--engine", default="gpu", choices=["cloud", "gpu"])
    ap.add_argument("--voice", default="stream", help="stream (learned from the recording, consent given) | stock | <profile id>")
    ap.add_argument("--streamer", default="")
    ap.add_argument("--loops", type=int, default=1)
    ap.add_argument("--gap-ms", type=int, default=400, help="silence between loops")
    ap.add_argument("--max-s", type=float, default=0.0, help="use only this much of the file; 0 = all of it")
    ap.add_argument("--lead-s", type=float, default=6.0,
                    help="silence before the recording starts. A session's speech-to-text connection takes a few "
                         "seconds to open; speech fed before that reaches it in one burst and is stamped as a few "
                         "words a millisecond (seen 24 Nov 2026: 27 words in a 1 s slot), which spoils the first "
                         "phrases of every run in a different way")
    ap.add_argument("--no-sync", action="store_true", help="do not report the video's time (no sync mode)")
    ap.add_argument("--keep-audio", action="store_true", help="save one WAV per dubbed phrase (for hearing lines back)")
    ap.add_argument("--tail-s", type=float, default=60.0, help="how long to wait for the last phrases after the file ends")
    ap.add_argument("--busy", action="append", default=None,
                    help="a backend that must have no live session (default: 8010 and 8110); repeat")
    ap.add_argument("--busy-wait-min", type=float, default=30.0)
    ap.add_argument("--start-run", type=int, default=1, help="number of the first run (to add runs to an --out folder)")
    a = ap.parse_args()
    targets = dict(t.split("=", 1) for t in a.target)
    busy_urls = a.busy if a.busy is not None else ["http://127.0.0.1:8010", "http://127.0.0.1:8110"]
    langs = a.langs.split(",")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pcm = decode(a.src, a.max_s)
    feed = build_feed(pcm, a.loops, a.gap_ms, a.lead_s)
    print(f"{Path(a.src).name}: {len(pcm) / 32000:.1f} s x {a.loops} = {len(feed) / 32000:.1f} s fed per run", flush=True)
    rows_file = out / "runs.json"
    rows: list[dict[str, Any]] = json.loads(rows_file.read_text(encoding="utf-8")) if rows_file.exists() else []
    for k in range(a.start_run, a.start_run + a.runs):
        for name, api in targets.items():
            busy = await wait_free([*busy_urls, *[u for u in targets.values()]], a.busy_wait_min)
            if busy:
                rows.append({"target": name, "run": k, "ok": False, "skipped": f"a stream was live: {', '.join(busy)}"})
                print(json.dumps(rows[-1]), flush=True)
                continue
            try:
                res = await replay(api, feed, langs, out / "runs" / f"{name}_r{k}", engine=a.engine, voice=a.voice,
                                   streamer=a.streamer, sync=not a.no_sync, keep_audio=a.keep_audio, tail_s=a.tail_s)
                row = {"target": name, "run": k, "ok": True, "session": res["session"], "errors": len(res["errors"]),
                       **flatten(res, langs)}
            except Exception as e:  # noqa: BLE001 - one failed run must not lose the others
                row = {"target": name, "run": k, "ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
            rows.append(row)
            print(json.dumps({key: row.get(key) for key in ("target", "run", "ok", "phrases", "first audio p50", "within 0.25 s",
                                                             "within 1 s", "dur_ratio p50", "dur_ratio p90", "backlog p95",
                                                             "skipped as too late", "at 1.3x", "errors", "error")}), flush=True)
            rows_file.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    skip = ("target", "run", "ok", "session", "error", "skipped")
    agg = {name: aggregate([{k: v for k, v in r.items() if k not in skip} for r in rows if r["target"] == name and r.get("ok")])
           for name in targets}
    units = {name: unit for name, _, unit in KEYS} | {f"{lg} {name}": unit for lg in langs for name, _, unit in PER_LANG}
    setup = {"src": Path(a.src).name, "src_s": round(len(pcm) / 32000, 1), "loops": a.loops, "gap_ms": a.gap_ms,
             "fed_s": round(len(feed) / 32000, 1), "lead_s": a.lead_s, "langs": langs, "engine": a.engine, "voice": a.voice,
             "sync": not a.no_sync, "targets": targets,
             "runs": {n: sum(1 for r in rows if r["target"] == n and r.get("ok")) for n in targets},
             "failed": {n: sum(1 for r in rows if r["target"] == n and not r.get("ok")) for n in targets}}
    (out / "summary.json").write_text(json.dumps({"setup": setup, "targets": agg, "runs": rows}, indent=1), encoding="utf-8")
    md = table(agg, units) + "\n\nruns that counted: " + ", ".join(f"{n} {setup['runs'][n]}" for n in targets) \
        + "; failed or skipped: " + ", ".join(f"{n} {setup['failed'][n]}" for n in targets) + "\n"
    (out / "summary.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    asyncio.run(main())
