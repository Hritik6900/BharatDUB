"""What `eval.live_replay` does not report: a session's first phrases and which voice said each line.

  python -m eval.live_first OUT --data off=../data-v1/ab/ws2-off --data warm=../data-v1/ab/ws2-warm [--first 10] \
      [--lang en-IN] [--after-s 120]

OUT is a folder written by `eval.live_replay` (its `runs.json` names every run's session). `--data` gives each
target's data folder (the comparison backend's `DATA_DIR`), whose store holds the per-phrase timing marks. Read only.

Per run, over the first `--first` phrases of the session (every target language counts as a line):
first audio p50 / p95 (end of the phrase's speech to its first audio), and how many lines were said in a stock
voice, in the copied voice, or not at all. Per run and language over the whole session: the share of spoken lines in
the copied voice and in a stock voice, the stock lines of the opening (before the copy existed) and the stock lines
after the first copied one (the mix a viewer hears between the lines), the lines a voice was asked for and did not
make, and the lines asked a second time. `--after-s` repeats that count for the part of the session from that second
on (a copy learned from the stream arrives late: the part where both voices exist). Over the runs: mean (lowest-highest).
Writes `first.json` and `first.md` into OUT.
"""
import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def lines_of(chunks: list[dict[str, Any]], langs: list[str]) -> list[dict[str, Any]]:
    """One row per phrase and language, in the order spoken."""
    out = []
    for c in sorted(chunks, key=lambda r: r["seq"]):
        t = c.get("timings") or {}
        for lang in langs:
            first = t.get(f"t_first_audio:{lang}")
            out.append({"seq": c["seq"], "lang": lang, "spoken": first is not None, "t_speech_ms": c.get("t_speech_ms") or 0,
                        "first_audio_ms": first - t["t_speech_end"] if first is not None and t.get("t_speech_end") is not None else None,
                        "copied": bool(t.get(f"clone:{lang}")) if first is not None else None,
                        "gpu": bool(t.get(f"gpu:{lang}")), "open": bool(t.get(f"open:{lang}")),
                        "skipped": t.get(f"skipped:{lang}"), "late_ms": t.get(f"late:{lang}"),
                        "asked": t.get(f"clone:{lang}") is not None, "again": bool(t.get(f"tts_retry:{lang}")),
                        "t_first_audio": first})
    return out


def first_phrases(rows: list[dict[str, Any]], n: int) -> dict[str, Any]:
    seqs = sorted({r["seq"] for r in rows})[:n]
    head = [r for r in rows if r["seq"] in seqs]
    ms = [r["first_audio_ms"] for r in head if r["first_audio_ms"] is not None]
    return {"phrases": len(seqs), "lines": len(head), "first audio p50": pct(ms, 50), "first audio p95": pct(ms, 95),
            "first audio worst": max(ms) if ms else None,
            "in a stock voice": sum(1 for r in head if r["spoken"] and not r["copied"]),
            "in the copied voice": sum(1 for r in head if r["spoken"] and r["copied"]),
            "not spoken": sum(1 for r in head if not r["spoken"]),
            "within 1 s of its moment": sum(1 for r in head if r["late_ms"] is not None and r["late_ms"] <= 1000)}


def voice_share(rows: list[dict[str, Any]], lang: str, after_s: float = 0.0) -> dict[str, Any]:
    rows = [r for r in rows if r["t_speech_ms"] >= after_s * 1000]
    mine = [r for r in rows if r["lang"] == lang and r["spoken"]]
    copied = [r for r in mine if r["copied"]]
    first_copy = min((r["seq"] for r in copied), default=None)
    stock = [r for r in mine if not r["copied"]]
    after = [r for r in stock if first_copy is not None and r["seq"] > first_copy]
    n = len(mine)
    since = [r for r in mine if first_copy is not None and r["seq"] >= first_copy]
    failed = [r for r in rows if r["lang"] == lang and not r["spoken"] and not r["skipped"] and r["asked"]]
    late = [r["late_ms"] for r in mine if r["late_ms"] is not None]
    ms = [r["first_audio_ms"] for r in mine if r["first_audio_ms"] is not None]
    return {"lines": sum(1 for r in rows if r["lang"] == lang), "spoken": n, "copied": len(copied), "stock": len(stock),
            "copied %": round(100 * len(copied) / n, 1) if n else None,
            "stock %": round(100 * len(stock) / n, 1) if n else None,
            "stock before the first copied line": len(stock) - len(after), "stock after the first copied line": len(after),
            "stock % from the first copied line on": round(100 * len(after) / len(since), 1) if since else None,
            "changes of voice": sum(1 for a, b in zip(mine, mine[1:]) if a["copied"] != b["copied"]),
            "asked for and not spoken (the voice failed)": len(failed),
            "asked a second time": sum(1 for r in rows if r["lang"] == lang and r["again"]),
            "skipped as too late": sum(1 for r in rows if r["lang"] == lang and r["skipped"] == "late"),
            "within 1 s %": round(100 * sum(1 for v in late if v <= 1000) / len(late), 1) if late else None,
            "within 0.25 s %": round(100 * sum(1 for v in late if v <= 250) / len(late), 1) if late else None,
            "first audio p50": pct(ms, 50), "first audio p95": pct(ms, 95)}


def agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in dict.fromkeys(k for r in rows for k in r):
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool)]
        out[key] = {"mean": round(statistics.mean(vals), 1), "min": round(min(vals), 1), "max": round(max(vals), 1),
                    "n": len(vals)} if vals else None
    return out


def table(per_target: dict[str, dict[str, Any]]) -> str:
    names = list(per_target)
    keys = list(dict.fromkeys(k for a in per_target.values() for k in a))
    lines = ["| Measure | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for key in keys:
        cells = [(f"{v['mean']:g} ({v['min']:g}-{v['max']:g})" if (v := per_target[n].get(key)) else "not measured") for n in names]
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--data", action="append", required=True, help="target=its data folder (repeat)")
    ap.add_argument("--first", type=int, default=10)
    ap.add_argument("--after-s", type=float, default=0.0,
                    help="also count the voices over the lines spoken this many seconds into the session and later")
    ap.add_argument("--lang", action="append", default=None, help="a language whose voices are counted over the whole session (repeat)")
    a = ap.parse_args()
    out = Path(a.out)
    runs = [r for r in json.loads((out / "runs.json").read_text(encoding="utf-8")) if r.get("ok")]
    setup = json.loads((out / "summary.json").read_text(encoding="utf-8"))["setup"] if (out / "summary.json").exists() else {}
    data = dict(d.split("=", 1) for d in a.data)
    stores: dict[str, dict[str, Any]] = {}
    per_run: list[dict[str, Any]] = []
    for r in runs:
        name = r["target"]
        if name not in data:
            continue
        if name not in stores:
            stores[name] = json.loads((Path(data[name]) / "local_db.json").read_text(encoding="utf-8"))
        db = stores[name]
        sess = next((s for s in db["live_sessions"] if s["id"] == r["session"]), None)
        if sess is None:
            continue
        langs = list(sess["target_langs"])
        rows = lines_of([c for c in db["live_chunks"] if c["session_id"] == r["session"]], langs)
        run_json = out / "runs" / f"{name}_r{r['run']}" / "run.json"
        metrics = json.loads(run_json.read_text(encoding="utf-8")).get("metrics", {}) if run_json.exists() else {}
        per_run.append({"target": name, "run": r["run"], "session": r["session"], "first": first_phrases(rows, a.first),
                        "voices": {lg: voice_share(rows, lg) for lg in (a.lang or [])},
                        "voices_after": {lg: voice_share(rows, lg, a.after_s) for lg in (a.lang or [])} if a.after_s else {},
                        "warm": metrics.get("warm"), "en_voice": metrics.get("en_voice")})
    names = list(dict.fromkeys(p["target"] for p in per_run))
    first = {n: agg([p["first"] for p in per_run if p["target"] == n]) for n in names}
    voices = {lg: {n: agg([p["voices"][lg] for p in per_run if p["target"] == n]) for n in names} for lg in (a.lang or [])}
    md = f"First {a.first} phrases of a session (every target language is a line), runs: " + \
        ", ".join(f"{n} {sum(1 for p in per_run if p['target'] == n)}" for n in names) + "\n\n" + table(first) + "\n"
    for lg, per in voices.items():
        md += f"\nWhole session, {lg}: which voice said its lines\n\n" + table(per) + "\n"
    after = {lg: {n: agg([p["voices_after"][lg] for p in per_run if p["target"] == n]) for n in names}
             for lg in (a.lang or [])} if a.after_s else {}
    for lg, per in after.items():
        md += f"\nFrom {a.after_s:g} s into the session on, {lg}\n\n" + table(per) + "\n"
    (out / "first.json").write_text(json.dumps({"setup": setup, "first_n": a.first, "first": first, "voices": voices,
                                                "after_s": a.after_s, "voices_after": after,
                                                "runs": per_run}, indent=1), encoding="utf-8")
    (out / "first.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
