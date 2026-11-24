"""Score the stored output of earlier Studio jobs again with the judge in use, without making a voice line.

  python -m eval.v1.rescore --data <DATA_DIR of the backend that ran the jobs> --jobs <id>[,<id>...] \
      --out DIR [--hear] [--write-hearings]

Reads that backend's store file and cache (never writes them). For every job and language:
  takes   every take the HQ path made and scored, as long as its audio is still in the cache
  lines   the finished line as it is in the video (after fitting): the file of the job folder, or, when the
          job folder has expired, the kept take fitted to its slot again

What the judge heard is taken from the cache where it is there (the hearing of that day, counted again by the
rule in use: this shows what the rule alone changes). `--hear` lets the judge hear whatever is not in the cache,
and `--hear-all` everything again (this shows what a second hearing of the same audio changes).
`--write-hearings` puts the hearings of the takes into `<data>/calibration/hearings.json`, where the calibration
page finds them (old jobs did not store what was heard with their takes).
"""
import argparse
import asyncio
import json
import os
import statistics
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("V1_HQ_JUDGE", "true")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="bd-rescore-"))

from app.shared import audio_utils as au  # noqa: E402
from app.studio.stages import fit  # noqa: E402
from app.v1 import qa  # noqa: E402
from app.v1.hq import calibrate  # noqa: E402


def _cached(data: Path, stage: str, key: str) -> dict[str, Any] | None:
    p = data / "cache" / stage / f"{key}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def take_hearing(data: Path, alt: dict[str, Any], lang: str, refs: list[str]) -> dict[str, Any] | None:
    """The stored hearing of a take: the key `hq/voice.py` used, for whichever voice sample the job had."""
    sha = au.sha256_file(alt["path"])
    for ref in refs:
        for judges in ("prisma", "qa_server,prisma"):
            got = _cached(data, "score_hq", au.cache_key("hq-score-1", sha, alt["text"], lang, ref, judges))
            if got and got.get("heard") is not None:
                return got
    return None


def mean(xs: list[float]) -> float | None:
    return round(100 * statistics.mean(xs), 1) if xs else None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--jobs", required=True, help="job ids or their first characters, comma-separated")
    ap.add_argument("--out", required=True)
    ap.add_argument("--hear", action="store_true", help="hear what is not in the cache (hosted calls)")
    ap.add_argument("--hear-all", action="store_true", help="hear every finished line again (hosted calls)")
    ap.add_argument("--write-hearings", action="store_true")
    ap.add_argument("--max-speed", type=float, default=1.15, help="the fit limit the HQ jobs ran with")
    ap.add_argument("--threshold", type=float, default=0.9)
    a = ap.parse_args()
    data = Path(a.data).resolve()
    db = json.loads((data / "local_db.json").read_text(encoding="utf-8"))
    refs = [""] + sorted({Path(str((v.get("embedding") or {}).get("ref_path") or v.get("ref_path") or "")).name
                          for v in db.get("voice_profiles", [])} - {""})
    st: Any = None
    if a.hear or a.hear_all:
        from app.v1.stages import Stages
        st = Stages("studio_hq", "gpu")
    tmp = Path(tempfile.mkdtemp(prefix="bd-refit-"))
    hearings: dict[str, Any] = {}
    report: list[dict[str, Any]] = []
    not_found: dict[str, int] = {}

    async def hear(path: Path, text: str, lang: str) -> dict[str, Any] | None:
        try:
            return await st.score(path, text, lang)
        except Exception as e:  # noqa: BLE001
            print("  not heard:", str(e)[:120])
            return None

    for prefix in a.jobs.split(","):
        job = next((j for j in db["jobs"] if j["id"].startswith(prefix.strip())), None)
        if job is None:
            print("no such job:", prefix)
            continue
        segs = sorted((s for s in db["segments"] if s["job_id"] == job["id"] and (s.get("src_text") or "").strip()),
                      key=lambda s: s["idx"])
        slots = fit.slots([s["start_s"] for s in segs], float(job["duration_s"]))
        job_dir = data / "jobs" / job["id"]
        for lang in job["target_langs"]:
            rows: list[dict[str, Any]] = []
            for seg, slot in zip(segs, slots):
                t = next((t for t in db["translations"] if t["segment_id"] == seg["id"] and t["lang"] == lang), None)
                if t is None:
                    continue
                row: dict[str, Any] = {"idx": seg["idx"], "words": len(t["text"].split()), "takes": [], "hq": bool(t.get("alts"))}
                for alt in t.get("alts") or []:
                    if not Path(alt["path"]).is_file():
                        not_found["take audio"] = not_found.get("take audio", 0) + 1
                        continue
                    got = take_hearing(data, alt, lang, refs)
                    src = "cache"
                    if got is None and a.hear:
                        got, src = await hear(Path(alt["path"]), alt["text"], lang), "heard now"
                    if got is None:
                        not_found["take hearing"] = not_found.get("take hearing", 0) + 1
                        continue
                    new = round(qa.heard_share(alt["text"], got["heard"], qa.HEARD_RULE_NFC), 3)
                    row["takes"].append({"idx": alt["idx"], "old": alt.get("backcheck"), "new": new, "by": got.get("by"),
                                         "from": src, "kept": alt["idx"] == t.get("picked")})
                    hearings[calibrate.item_id(alt["path"], alt["text"])] = {"heard": got["heard"], "by": got.get("by") or "prisma"}
                # the finished line
                line = job_dir / str(t.get("audio_path") or "").replace("\\", "/")
                how = "job folder"
                if not line.is_file() and t.get("alts"):
                    kept = next((x for x in t["alts"] if x["idx"] == t.get("picked")), None)
                    if kept and Path(kept["path"]).is_file():
                        line = tmp / f"{job['id'][:8]}_{lang}_{seg['idx']:03}.wav"
                        speed = fit.fit_clip(Path(kept["path"]), slot, line, a.max_speed)
                        how = "kept take fitted again" + ("" if abs(speed - float(t.get("fit_speed") or 1.0)) < 0.01 else
                                                           f" (speed {speed} now, {t.get('fit_speed')} then)")
                if line.is_file():
                    got, src = None, "cache"
                    if not a.hear_all:
                        sha = au.sha256_file(line)
                        for judges in ("prisma", "qa_server,prisma"):
                            got = got or _cached(data, "score_eval", au.cache_key("eval-backcheck-1", sha, t["text"], lang, judges))
                        if got is not None and got.get("heard") is None:
                            got = None
                    if got is None and st is not None:
                        got, src = await hear(line, t["text"], lang), "heard now"
                    if got is not None:
                        row["line"] = {"old": round(qa.heard_share(t["text"], got["heard"]), 3),
                                       "new": round(qa.heard_share(t["text"], got["heard"], qa.HEARD_RULE_NFC), 3),
                                       "by": got.get("by"), "from": src, "audio": how}
                    else:
                        not_found["line hearing"] = not_found.get("line hearing", 0) + 1
                else:
                    not_found["line audio"] = not_found.get("line audio", 0) + 1
                rows.append(row)
            lines = [r["line"] for r in rows if "line" in r]
            kept = [k for r in rows for k in r["takes"] if k["kept"]]
            firsts = [r["takes"][0] for r in rows if r["takes"] and r["takes"][0]["idx"] == 0]
            best_new = [max(k["new"] for k in r["takes"]) for r in rows if r["takes"]]
            out = {"job": job["id"], "video": job.get("source_path"), "lang": lang, "hq": any(r["hq"] for r in rows),
                   "lines": len(rows),
                   "finished_old_pct": mean([x["old"] for x in lines]), "finished_new_pct": mean([x["new"] for x in lines]),
                   "finished_scored": len(lines), "finished_from": sorted({x["from"] for x in lines}),
                   "finished_audio": sorted({x["audio"].split(" (")[0] for x in lines}),
                   "kept_old_pct": mean([k["old"] for k in kept if k["old"] is not None]), "kept_new_pct": mean([k["new"] for k in kept]),
                   "first_take_new_pct": mean([k["new"] for k in firsts]), "best_take_new_pct": mean(best_new),
                   "takes": sum(len(r["takes"]) for r in rows),
                   "flagged_old": sum(1 for k in kept if k["old"] is not None and k["old"] < a.threshold),
                   "flagged_new": sum(1 for k in kept if k["new"] < a.threshold),
                   "judges": sorted({str(x["by"]) for x in lines} | {str(k["by"]) for r in rows for k in r["takes"]}),
                   "rows": rows}
            report.append(out)
            print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False), flush=True)
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "rescore.json").write_text(json.dumps({"data": str(data), "rule": qa.HEARD_RULE_NFC, "not_found": not_found,
                                                     "jobs": report}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("could not be scored again:", not_found or "nothing")
    if a.write_hearings and hearings:
        p = data / "calibration" / "hearings.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        p.write_text(json.dumps({**old, **hearings}, ensure_ascii=False), encoding="utf-8")
        print(f"{len(hearings)} hearings written to {p}")


if __name__ == "__main__":
    asyncio.run(main())
