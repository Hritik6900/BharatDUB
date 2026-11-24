"""Tables from a Studio comparison made by `scripts/v1/eval-studio-ws3.sh`.

  python -m eval.v1.studio_table <run folder> --ab <data>/ab [--threshold 0.9]

Reads `<run folder>/<video>_<setup>/summary.json` (written by eval.v1.studio) and, for the HQ setups, the store of
the comparison backend that ran the job (`<ab>/ws3-<setup>/local_db.json`) for the takes of every line.
Prints, per video and language and setup: words heard back of the finished lines, takes, flagged lines, who
judged; per video and setup: total seconds and seconds per stage; and for the "fixed" setup what the adaptive rule
would have kept from the very same takes (an exact comparison: same lines, same audio).
"""
import argparse
import json
import statistics
from pathlib import Path
from typing import Any

SETUPS = ("std", "hq", "fixed", "adapt", "new")
NAMES: dict[str, str] = {}      # setup -> data folder of the comparison backend that ran it


def load(run: Path) -> dict[tuple[str, str], dict[str, Any]]:
    out = {}
    for d in sorted(run.iterdir()):
        f = d / "summary.json"
        if not f.exists() or "_" not in d.name:
            continue
        video, setup = d.name.rsplit("_", 1)
        rows = json.loads(f.read_text(encoding="utf-8"))["runs"]
        if rows and rows[0].get("ok"):
            out[(video, setup)] = rows[0]
        elif rows:
            print(f"failed: {d.name}: {rows[0].get('error')}")
    return out


def takes_of(ab: Path, setup: str, job_id: str) -> dict[str, list[dict[str, Any]]]:
    """lang -> the job's lines, each {text, picked, flagged, alts}."""
    p = ab / NAMES.get(setup, f"ws3-{setup}") / "local_db.json"
    if not p.exists():
        return {}
    db = json.loads(p.read_text(encoding="utf-8"))
    segs = {s["id"]: s for s in db["segments"] if s["job_id"] == job_id}
    out: dict[str, list[dict[str, Any]]] = {}
    for t in db["translations"]:
        if t["segment_id"] in segs and t.get("alts"):
            out.setdefault(t["lang"], []).append({**t, "idx": segs[t["segment_id"]]["idx"]})
    for rows in out.values():
        rows.sort(key=lambda r: r["idx"])
    return out


def transcript_of(ab: Path, setup: str, job_id: str) -> dict[str, int]:
    """How the job's cleaned transcript stands against its first hearing: lines the merge and clean steps changed,
    and of those the ones that are no longer the line that was heard (`hq/review.py: keeps_source`)."""
    from app.v1.hq.review import keeps_source
    p = ab / NAMES.get(setup, f"ws3-{setup}") / "local_db.json"
    if not p.exists():
        return {}
    segs = [s for s in json.loads(p.read_text(encoding="utf-8"))["segments"] if s["job_id"] == job_id and (s.get("src_text") or "").strip()]
    changed = [s for s in segs if s.get("src_text_raw") and s["src_text_raw"] != s["src_text"]]
    return {"lines": len(segs), "changed": len(changed),
            "not_the_line_heard": sum(1 for s in changed if not keeps_source(s["src_text_raw"], s["src_text"]))}


def adaptive_on(alts: list[dict[str, Any]], need: float, most: int, same_stop: bool = False) -> tuple[int, float]:
    """What "one take, more only while the best is under `need`, at most `most`" keeps from these takes in the
    order they were made: (takes made, score of the one kept). `same_stop`: no further take once two takes were
    heard back as exactly the same words (`V1_HQ_ADAPTIVE_SAME_STOP`)."""
    from app.v1.qa import _words
    made: list[float] = []
    heard: set[tuple[Any, ...]] = set()
    for a in alts[:most]:
        made.append(float(a["backcheck"] if a.get("backcheck") is not None else 1.0))
        if made[-1] >= need:
            break
        key = (a.get("engine_speed"), a.get("text"), tuple(_words(a.get("heard") or "", True)))
        if same_stop and (a.get("heard") or "").strip() and key in heard:
            break
        heard.add(key)
    return len(made), max(made)


def pct(x: float | None) -> str:
    return "not scored" if x is None else f"{100 * x:.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--ab", required=True)
    ap.add_argument("--threshold", type=float, default=0.9)
    ap.add_argument("--json", default="")
    ap.add_argument("--names", default="", help="setup=data folder name under --ab when it is not ws3-<setup>, e.g. fixed=ws3-fixed2,adapt=ws3-adapt2")
    a = ap.parse_args()
    NAMES.update(dict(pair.split("=", 1) for pair in a.names.split(",") if pair))
    runs = load(Path(a.run))
    videos = sorted({v for v, _ in runs})
    setups = [s for s in SETUPS if any((v, s) in runs for v in videos)]
    langs = sorted({lang for r in runs.values() for lang in r["per_lang"]})
    result: dict[str, Any] = {"videos": videos, "setups": setups, "rows": [], "times": [], "adaptive_on_fixed": []}

    print("| Video | Language | Setup | Heard back (finished lines) | Lines | Takes | Flagged | Judge |")
    print("|---|---|---|---|---|---|---|---|")
    for v in videos:
        for lang in langs:
            for s in setups:
                r = runs.get((v, s))
                if not r:
                    continue
                p = r["per_lang"][lang]
                row = {"video": v, "lang": lang, "setup": s, "heard": p["backcheck_mean"], "lines": p["lines"],
                       "takes": p["takes"], "flagged": p["flagged"], "judges": p.get("judges"), "rule": p.get("rule")}
                result["rows"].append(row)
                print(f"| {v} | {lang} | {s} | {pct(p['backcheck_mean'])} | {p['lines']} | {p['takes']} | {p['flagged']} | "
                      f"{', '.join(f'{k} {n}' for k, n in (p.get('judges') or {}).items())} ({p.get('rule')}) |")

    print("\n| Setup | " + " | ".join(videos) + " | Mean (lowest-highest) |")
    print("|---|" + "---|" * (len(videos) + 1))
    for s in setups:
        per_video = []
        for v in videos:
            r = runs.get((v, s))
            per_video.append(statistics.mean(p["backcheck_mean"] for p in r["per_lang"].values()) if r else None)
        have = [x for x in per_video if x is not None]
        print(f"| {s}: heard back | " + " | ".join(pct(x) for x in per_video) + " | "
              + (f"{pct(statistics.mean(have))} ({pct(min(have))}-{pct(max(have))})" if have else "") + " |")
        result.setdefault("heard_by_setup", {})[s] = {"per_video": per_video, "mean": statistics.mean(have) if have else None}
        for lang in langs:
            xs = [runs[(v, s)]["per_lang"][lang]["backcheck_mean"] for v in videos if (v, s) in runs]
            print(f"| {s}: {lang} | " + " | ".join(pct(x) for x in xs) + f" | {pct(statistics.mean(xs))} |")

    print("\n| Video | Setup | Total s | Voice s | Translate s | Transcribe + hear again s | Takes | Score calls | Flagged | Lines |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for v in videos:
        for s in setups:
            r = runs.get((v, s))
            if not r:
                continue
            st, u = r["stages"], r["usage"]
            row = {"video": v, "setup": s, "total_s": r["turnaround_s"], "voice_s": st.get("voice"), "translate_s": st.get("translate"),
                   "hear_s": round(st.get("transcribe", 0) + st.get("hear_again", 0), 1), "takes": r["takes"],
                   "score_calls": u.get("score_calls"), "flagged": r["flagged"], "lines": r["lines"], "cached": r.get("cached"),
                   "tts_cache_hits": u.get("tts_cache_hits"), "warnings": r.get("warnings")}
            result["times"].append(row)
            print(f"| {v} | {s} | {row['total_s']:.0f} | {row['voice_s'] or 0:.0f} | {row['translate_s'] or 0:.0f} | {row['hear_s']} | "
                  f"{row['takes']} | {row['score_calls'] or 0} | {row['flagged']} | {row['lines']} |")

    ab = Path(a.ab)
    if "fixed" in setups:
        print("\nThe adaptive rule applied to the takes the fixed setup made (same lines, same audio; scores of the takes before fitting):")
        print("| Video | Language | Lines | Fixed: takes / best take | Adaptive without the same-words stop: takes / kept take | Adaptive as built: takes / kept take | Lines where adaptive as built kept a lower-scored take | First take alone |")
        print("|---|---|---|---|---|---|---|---|")
        for v in videos:
            r = runs.get((v, "fixed"))
            if not r:
                continue
            for lang, lines in takes_of(ab, "fixed", r["job"]).items():
                fixed_n = sum(len(t["alts"]) for t in lines)
                fixed_best = [max(float(x["backcheck"] or 0) for x in t["alts"]) for t in lines]
                plain = [adaptive_on(t["alts"], a.threshold, 5) for t in lines]
                sim = [adaptive_on(t["alts"], a.threshold, 5, same_stop=True) for t in lines]
                lower = sum(1 for (n, kept), best in zip(sim, fixed_best) if kept < best - 1e-9)
                row = {"video": v, "lang": lang, "lines": len(lines), "fixed_takes": fixed_n, "fixed_best": statistics.mean(fixed_best),
                       "adaptive_takes": sum(n for n, _ in sim), "adaptive_kept": statistics.mean(k for _, k in sim), "lower": lower,
                       "plain_takes": sum(n for n, _ in plain), "plain_kept": statistics.mean(k for _, k in plain),
                       "flagged_fixed": sum(1 for b in fixed_best if b < a.threshold), "flagged_adaptive": sum(1 for _, k in sim if k < a.threshold),
                       "first_take": statistics.mean(float(t["alts"][0]["backcheck"] or 0) for t in lines)}
                result["adaptive_on_fixed"].append(row)
                print(f"| {v} | {lang} | {len(lines)} | {fixed_n} / {pct(row['fixed_best'])} | {row['plain_takes']} / {pct(row['plain_kept'])} | "
                      f"{row['adaptive_takes']} / {pct(row['adaptive_kept'])} | {lower} | {pct(row['first_take'])} |")
    for s in ("hq", "adapt", "new"):
        rows = []
        for v in videos:
            r = runs.get((v, s))
            for lang, lines in (takes_of(ab, s, r["job"]) if r else {}).items():
                kept = [next(x for x in t["alts"] if x["idx"] == t["picked"]) for t in lines]
                rows.append({"video": v, "lang": lang, "first": statistics.mean(float(t["alts"][0]["backcheck"] or 0) for t in lines),
                             "kept": statistics.mean(float(k["backcheck"] or 0) for k in kept),
                             "more_than_one": sum(1 for t in lines if len(t["alts"]) > 1), "lines": len(lines),
                             "providers": sorted({k["provider"] for k in kept}),
                             "judges": sorted({str(x.get("scored_by")) for t in lines for x in t["alts"]}),
                             "passed_over": sum(1 for t in lines for x in t["alts"] if x.get("passed_over"))})
        if rows:
            result[f"takes_{s}"] = rows
            print(f"\n{s}: first take -> kept take (scores of the takes, before fitting)")
            for x in rows:
                print(f"  {x['video']} {x['lang']}: {pct(x['first'])} -> {pct(x['kept'])}; {x['more_than_one']} of {x['lines']} lines needed more "
                      f"than one take; voice {', '.join(x['providers'])}; judged by {', '.join(x['judges'])}; judge passed over {x['passed_over']}x")
    print("\nTranscript after the merge and clean steps, against the first hearing:")
    print("| Video | Setup | Lines | Changed | No longer the line that was heard |")
    print("|---|---|---|---|---|")
    for v in videos:
        for s in setups:
            r = runs.get((v, s))
            t = transcript_of(ab, s, r["job"]) if r and s != "std" else {}
            if t:
                result.setdefault("transcripts", []).append({"video": v, "setup": s, **t})
                print(f"| {v} | {s} | {t['lines']} | {t['changed']} | {t['not_the_line_heard']} |")
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
