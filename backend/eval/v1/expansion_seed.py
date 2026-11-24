"""Build the seed of Live's expansion model (`backend/config/live_expansion.json`) from stored history.

  python -m eval.v1.expansion_seed [--logs ../logs/sessions] [--trace ../data-v1/trace ../data-v1/ab/*/trace]
                                   [--out config/live_expansion.json]

The model (app/v1/dense.py) wants, per language and kind of voice, ms of dubbed speech per target letter, per
target word and per source word, at the voice's own pace. What the history holds:

  logs/sessions/<version>/*.jsonl (v0 and v1, from 13 Nov 2026): no field is the dub's length. `audio_ms` is the
      time between the first and the last audio message, about 0 for a line sent in one piece. The length can be
      worked out only for a phrase whose successor queued straight behind it: the successor's `heard` time minus
      this one's, times this one's `tempo`. That gives ms per SOURCE word, on the lines that ran long enough to
      make the next one wait (so it leans to the long side). Nothing about the target text is stored there.
  trace records from v1.1 on (`dub_raw_ms`, `tgt_words`, `tgt_chars`, `src_words`): exact, every spoken line.

So ms per letter and per word exist only where v1.1 trace records exist; a language with history in the logs
alone gets its ms per source word written down (`from_logs`) and no rate, and a session in that language starts
on v0's word limit until its own first lines have been spoken. Medians throughout. Kinds: gpu = our engine's
copied voice, clone = the hosted copy, stock = a stock voice.
"""
import argparse
import glob
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]


def kind_of(row: dict[str, Any]) -> str:
    if row.get("on_gpu"):
        return "gpu"
    return "clone" if row.get("copied_voice") else "stock"


def from_logs(folder: Path) -> dict[tuple[str, str], list[float]]:
    """ms of dubbed speech per source word, from phrases whose successor queued straight behind them."""
    out: dict[tuple[str, str], list[float]] = defaultdict(list)
    for path in sorted(folder.glob("*/*.jsonl")):
        by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("heard_ms") is None or r.get("first_audio_ms") is None or r.get("speech_ms") is None:
                continue
            end = r["t_speech_ms"] + r["speech_ms"]
            r["_heard"], r["_first"] = end + r["heard_ms"], end + r["first_audio_ms"]
            by_lang[r["lang"]].append(r)
        for lang, rows in by_lang.items():
            rows.sort(key=lambda r: r["seq"])
            groups: list[list[dict[str, Any]]] = []
            for r in rows:      # phrases spoken in one call start at the same moment
                if groups and abs(groups[-1][0]["_heard"] - r["_heard"]) < 2:
                    groups[-1].append(r)
                else:
                    groups.append([r])
            for g, h in zip(groups, groups[1:]):
                nxt = h[0]
                if nxt.get("late_ms") is not None:
                    queued = nxt["late_ms"] > 0 and nxt["_heard"] > nxt["_first"] + 150
                else:
                    queued = nxt["_heard"] > nxt["_first"] + 350
                words = sum(r.get("src_words") or 0 for r in g)
                dub = nxt["_heard"] - g[0]["_heard"]
                if not queued or words < 4 or not 0 < dub < 30000:
                    continue
                per = dub * (g[0].get("tempo") or 1.0) / words
                if 120 <= per <= 1500:
                    out[(lang, kind_of(g[0]))].append(per)
    return out


def from_trace(files: list[str]) -> dict[tuple[str, str], dict[str, list[float]]]:
    """Exact lengths from v1.1 trace records."""
    out: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    recs: list[dict[str, Any]] = []
    for f in files:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") == "live_phrase":
                recs.append(r)
    extra: dict[tuple[str, str, int], int] = defaultdict(int)   # source words of phrases spoken in another's call
    for r in recs:
        if r.get("merged_into") is not None:
            extra[(r["session"], r["lang"], r["merged_into"])] += r.get("src_words") or 0
    for r in recs:
        raw, words, chars = r.get("dub_raw_ms"), r.get("tgt_words"), r.get("tgt_chars")
        if not raw or not words or not chars or r.get("merged_into") is not None or words < 4 or raw < 300:
            continue
        kind = "gpu" if r.get("tts") == "gpu_voice" else "clone" if r.get("clone") else "stock"
        d = out[(r["lang"], kind)]
        if 20 <= raw / chars <= 400:
            d["char"].append(raw / chars)
            d["word"].append(raw / words)
            src = (r.get("src_words") or 0) + extra[(r["session"], r["lang"], r["seq"])]
            if src >= 3:
                d["src"].append(raw / src)
    return out


def build(logs: Path, trace_files: list[str], min_lines: int = 20) -> dict[str, Any]:
    a, c = from_logs(logs), from_trace(trace_files)
    rates: dict[str, Any] = {}
    log_only: dict[str, Any] = {}
    for key in sorted(set(a) | set(c)):
        lang, kind = key
        name = f"{lang}|{kind}"
        exact = c.get(key) or {}
        logs_n = len(a.get(key, []))
        logs_src = round(statistics.median(a[key]), 1) if logs_n >= min_lines else None
        if len(exact.get("char", [])) >= min_lines:
            rates[name] = {"ms_per_char": round(statistics.median(exact["char"]), 1),
                           "ms_per_word": round(statistics.median(exact["word"]), 1),
                           "ms_per_src_word": round(statistics.median(exact["src"]), 1) if len(exact["src"]) >= min_lines else logs_src,
                           "n": len(exact["char"]), "logs_ms_per_src_word": logs_src, "logs_n": logs_n}
        elif logs_src is not None:
            log_only[name] = {"ms_per_src_word": logs_src, "n": logs_n}
    return {"built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "what": "Seed of Live's expansion model: medians of ms of dubbed speech at the voice's own pace. "
                    "Built by eval/v1/expansion_seed.py; see its header for what each number comes from.",
            "rates": rates, "from_logs_only": log_only}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=str(BACKEND.parent / "logs" / "sessions"))
    ap.add_argument("--trace", nargs="*", default=[str(BACKEND.parent / "data-v1" / "trace")],
                    help="trace folders or files (globs allowed)")
    ap.add_argument("--out", default=str(BACKEND / "config" / "live_expansion.json"))
    a = ap.parse_args()
    files: list[str] = []
    for item in a.trace:
        for p in glob.glob(item) or [item]:
            files += sorted(glob.glob(str(Path(p) / "trace-*.jsonl"))) if Path(p).is_dir() else [p] if Path(p).is_file() else []
    seed = build(Path(a.logs), files)
    Path(a.out).write_text(json.dumps(seed, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    for name, r in seed["rates"].items():
        print(f"{name}: {r}")
    for name, r in seed["from_logs_only"].items():
        print(f"{name} (logs only, no rate): {r}")
    print(f"written to {a.out} from {len(files)} trace file(s)")


if __name__ == "__main__":
    main()
