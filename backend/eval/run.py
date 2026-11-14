"""Evaluation: writes eval/results.csv with measured numbers only.

  python -m eval.run                 # Studio + Live numbers from stored runs (no API calls, no credits)
  python -m eval.run --wer           # also WER: eval/clips/<name>.wav + <name>.txt (ground truth), one Prisma call each
  python -m eval.run --live-sessions <id> <id>   # limit Live rows to these sessions

A metric with nothing to measure is written with value "" and a note; nothing is estimated.
"""
import argparse
import asyncio
import csv
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_store  # noqa: E402
from app.studio.stages.fit import MAX_SPEED  # noqa: E402

HERE = Path(__file__).resolve().parent
Row = dict[str, Any]


def words(text: str) -> list[str]:
    """Lowercase, drop punctuation (keeps Indic letters and their vowel signs)."""
    kept = "".join(c if unicodedata.category(c)[0] in "LMN" else " " for c in text.lower())
    return re.sub(r"\s+", " ", kept).split()


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1]


def pct(values: list[float], p: float) -> float:
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))]


def row(area: str, metric: str, value: Any, unit: str, n: int, note: str = "") -> Row:
    return {"area": area, "metric": metric, "value": value, "unit": unit, "n": n, "note": note}


async def wer_rows(lang: str) -> list[Row]:
    clips = sorted((HERE / "clips").glob("*.wav"))
    pairs = [(c, c.with_suffix(".txt")) for c in clips if c.with_suffix(".txt").exists()]
    if not pairs:
        return [row("stt", "wer", "", "%", 0, "no clips: put <name>.wav + <name>.txt in eval/clips")]
    from app.providers import get_stt
    stt = get_stt()
    errs = total = 0
    out: list[Row] = []
    for wav, txt in pairs:
        ref = words(txt.read_text(encoding="utf-8"))
        res = await stt.transcribe(str(wav), lang)
        e = edit_distance(ref, words(res.text))
        errs, total = errs + e, total + len(ref)
        out.append(row("stt", f"wer:{wav.stem}", round(100 * e / max(1, len(ref)), 1), "%", len(ref)))
    out.insert(0, row("stt", "wer", round(100 * errs / max(1, total), 1), "%", len(pairs),
                      f"{total} reference words, Prisma REST, lang={lang}"))
    return out


async def studio_rows() -> list[Row]:
    store = get_store()
    jobs = [j for j in await store.select("jobs") if j.get("status") == "done"]
    out: list[Row] = []
    # Turnaround only counts runs that really did the work (a cached rerun finishes in 2 s and proves nothing).
    fresh = [j for j in jobs if not (j["stage_timings"].get("_usage") or {}).get("tts_cache_hits")
             and (j["stage_timings"].get("_usage") or {}).get("tts_calls")]
    for j in fresh:
        t, langs = j["stage_timings"], j["target_langs"]
        out.append(row("studio", "turnaround", t.get("_total"), "s", len(langs),
                       f"{j['duration_s']:.1f} s video, {len(langs)} languages, "
                       f"{'cloned' if j.get('voice_profile_id') else 'stock'} voice, separate {t.get('separate')} s, job {j['id'][:8]}"))
    if not fresh:
        out.append(row("studio", "turnaround", "", "s", 0, "no uncached finished job in the store"))
    segs = await store.select_in("segments", "job_id", [j["id"] for j in jobs]) if jobs else []
    trs = await store.select_in("translations", "segment_id", [s["id"] for s in segs]) if segs else []
    speeds = [t["fit_speed"] for t in trs if t.get("fit_speed")]
    if speeds:
        n = len(speeds)
        out.append(row("studio", "slot_fit_natural", round(100 * sum(s <= 1.001 for s in speeds) / n, 1), "%", n,
                       "dubbed lines that fit their slot with no speed-up"))
        out.append(row("studio", "slot_fit_within_max", round(100 * sum(s < MAX_SPEED for s in speeds) / n, 1), "%", n,
                       f"lines that fit below the {MAX_SPEED}x cap; the rest hit the cap and may overrun"))
    else:
        out.append(row("studio", "slot_fit_natural", "", "%", 0, "no dubbed lines in the store"))
    return out


async def live_rows(session_ids: list[str]) -> list[Row]:
    store = get_store()
    out: list[Row] = []
    for sid in session_ids:
        chunks = await store.select("live_chunks", session_id=sid)
        langs = sorted({k.split(":", 1)[1] for c in chunks for k in c["timings"] if k.startswith("t_heard:")})
        if not langs:
            out.append(row("live", "heard_p50", "", "ms", 0, f"session {sid[:8]}: no heard timings"))
        for lang in langs:
            first = [c["timings"][f"t_first_audio:{lang}"] - c["timings"]["t_speech_end"] for c in chunks
                     if f"t_first_audio:{lang}" in c["timings"] and "t_speech_end" in c["timings"]]
            heard = [c["timings"][f"t_heard:{lang}"] - c["timings"]["t_speech_end"] for c in chunks
                     if f"t_heard:{lang}" in c["timings"] and "t_speech_end" in c["timings"]]
            skipped = sum(1 for c in chunks if c["timings"].get(f"skipped:{lang}") not in (None, "unheard"))
            note = f"session {sid[:8]}, {lang}, {skipped} phrases skipped"
            for name, vals in (("first_audio", first), ("heard", heard)):
                if vals:
                    out.append(row("live", f"{name}_p50", pct(vals, 50), "ms", len(vals), note))
                    out.append(row("live", f"{name}_p95", pct(vals, 95), "ms", len(vals), note))
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wer", action="store_true", help="run Prisma on eval/clips (uses credits)")
    ap.add_argument("--lang", default="hi-IN")
    ap.add_argument("--live-sessions", nargs="*", default=None)
    ap.add_argument("--out", default=str(HERE / "results.csv"))
    a = ap.parse_args()

    rows: list[Row] = []
    rows += await wer_rows(a.lang) if a.wer else [row("stt", "wer", "", "%", 0, "not run (pass --wer)")]
    rows += await studio_rows()
    sids = a.live_sessions
    if sids is None:  # default: the runs behind LIVE_TEST_REPORT.md
        base = HERE.parent / "scripts" / "out" / "live"
        sids = [(base / n / "session.txt").read_text().strip() for n in ("J_stock_ta", "J_stock_3all", "H_stream_ta", "P2_streamer_2lang", "P3_streamer_offset")
                if (base / n / "session.txt").exists()]
    rows += await live_rows(sids)

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["area", "metric", "value", "unit", "n", "note"])
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['area']:7} {r['metric']:22} {str(r['value']):>8} {r['unit']:3} n={r['n']:<4} {r['note']}")
    print("wrote", a.out)


if __name__ == "__main__":
    asyncio.run(main())
