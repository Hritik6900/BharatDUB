"""Studio eval: the same video through one or more running backends, standard and HQ, several runs each.

  python -m eval.v1.studio SRC --out DIR --langs ta-IN,bn-IN --runs 3 \
      --target standard=http://127.0.0.1:8111 --target hq=http://127.0.0.1:8115:hq [--voice video] [--engine gpu]

A target is `name=url` or `name=url:hq` (the job is created with quality=hq). After a job is done every dubbed
line is heard back by the same scorer on that backend (`/api/v1/jobs/<id>/backcheck`), so standard and HQ are
judged by one ear. Per run: turnaround, share of words heard back, largest speed-up, flagged lines, takes.
A repeated run of the same video is served from the stage cache, so only an uncached run counts towards
turnaround (a cached run is marked and left out of that mean).
"""
import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

KEYS = [("turnaround_s", "s"), ("backcheck_pct", "%"), ("backcheck_by_words_pct", "%"), ("speed_max", "x"),
        ("lines", ""), ("flagged", ""), ("takes", ""), ("warnings", ""),
        ("guard_script_failed", ""), ("guard_script_flagged", ""), ("guard_shift_checked", ""),
        ("guard_shift_not_checked", ""), ("guard_shift_failed", ""), ("guard_shift_flagged", ""),
        ("guard_shortened_flagged", ""), ("unspoken", "")]


async def one_job(a: argparse.Namespace, name: str, api: str, hq: bool, k: int) -> dict[str, Any]:
    res: dict[str, Any] = {"target": name, "run": k, "ok": False}
    langs = a.langs.split(",")
    async with httpx.AsyncClient(base_url=api, timeout=120) as c:
        data = {"target_langs": a.langs, "owns_video": "true"}
        if hq:
            data["quality"] = "hq"
        if a.engine == "gpu":
            data["engine"] = "gpu"
        if a.voice == "video":
            data |= {"voice_from_video": "true", "voice_consent": "true"}
        elif a.voice != "stock":
            data["voice_profile_id"] = a.voice
        src = Path(a.src)
        t0 = time.perf_counter()
        r = await c.post("/api/jobs", data=data, files={"file": (src.name, src.read_bytes(), "video/mp4")})
        if r.status_code != 201:
            res["error"] = r.text[:300]
            return res
        jid = r.json()["job_id"]
        res["job"] = jid
        job: dict[str, Any] = {}
        while time.perf_counter() - t0 < a.timeout:
            job = (await c.get(f"/api/jobs/{jid}")).json()
            if job["status"] in ("done", "failed"):
                break
            await asyncio.sleep(2)
        res["wall_s"] = round(time.perf_counter() - t0, 1)
        if job.get("status") != "done":
            res["error"] = str(job.get("error") or job.get("status"))[:300]
            return res
        t = job["stage_timings"]
        usage = t.get("_usage") or {}
        res |= {"ok": True, "turnaround_s": t.get("_total"), "cached": bool(usage.get("tts_cache_hits")) and not usage.get("tts_calls"),
                "warnings": len(t.get("_warnings") or []), "usage": usage,
                "stages": {key: v for key, v in t.items() if not key.startswith("_") and ":" not in key}}
        per_lang = {}
        for lang in langs:
            b = (await c.get(f"/api/v1/jobs/{jid}/backcheck", params={"lang": lang}, timeout=600)).json()
            per_lang[lang] = {key: b.get(key) for key in ("scored", "backcheck_mean", "backcheck_by_words", "speed_max", "flagged", "takes", "judges", "rule")}
            per_lang[lang]["lines"] = len(b.get("lines") or [])
            per_lang[lang]["guard"] = b.get("guard") or {}
        res["per_lang"] = per_lang
        means = [v["backcheck_mean"] for v in per_lang.values() if v["backcheck_mean"] is not None]
        byw = [v["backcheck_by_words"] for v in per_lang.values() if v["backcheck_by_words"] is not None]
        res["backcheck_pct"] = round(100 * statistics.mean(means), 1) if means else None
        res["backcheck_by_words_pct"] = round(100 * statistics.mean(byw), 1) if byw else None
        res["speed_max"] = max((v["speed_max"] or 1.0 for v in per_lang.values()), default=None)
        res["lines"] = sum(v["lines"] for v in per_lang.values())
        res["flagged"] = sum(v["flagged"] or 0 for v in per_lang.values())
        res["takes"] = sum(v["takes"] or 0 for v in per_lang.values())
        # v1.2 guards, each its own number (None = that backend did not run the guard): the script guard and the
        # content-shift check look at every line before the voice; `unspoken` = lines no voice could say.
        checked = [v["guard"] for v in per_lang.values() if v["guard"].get("checked")]
        for key in ("script_failed", "script_flagged", "shift_checked", "shift_not_checked", "shift_failed", "shift_flagged",
                    "shortened_flagged"):
            res[f"guard_{key}"] = sum(g.get(key) or 0 for g in checked) if checked else None
        res["unspoken"] = sum(v["guard"].get("unspoken") or 0 for v in per_lang.values())
    return res


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"runs": len(rows), "failed": sum(1 for r in rows if not r["ok"])}
    for key, _ in KEYS:
        use = [r for r in rows if r.get("ok") and isinstance(r.get(key), (int, float))]
        if key == "turnaround_s":
            use = [r for r in use if not r.get("cached")]   # a run served from the cache did no work
        vals = [r[key] for r in use]
        out[key] = {"mean": round(statistics.mean(vals), 2), "min": min(vals), "max": max(vals), "n": len(vals)} if vals else None
    return out


def table(agg: dict[str, dict[str, Any]]) -> str:
    names = list(agg)
    lines = ["| Measure | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for key, unit in KEYS:
        cells = [(f"{v['mean']:g} ({v['min']:g}-{v['max']:g}), n={v['n']}" if (v := agg[n].get(key)) else "not measured") for n in names]
        lines.append(f"| {key.replace('_', ' ')}{' (' + unit + ')' if unit and unit not in ('%', 's') else ''} | " + " | ".join(cells) + " |")
    lines.append("| runs (failed) | " + " | ".join(f"{agg[n]['runs']} ({agg[n]['failed']})" for n in names) + " |")
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--target", action="append", required=True, help="name=http://host:port or name=http://host:port:hq")
    ap.add_argument("--langs", default="ta-IN")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--engine", default="cloud", choices=["cloud", "gpu"])
    ap.add_argument("--voice", default="stock", help="stock | video (copy the voice in the video, with consent) | <voice profile id>")
    ap.add_argument("--timeout", type=float, default=1800)
    a = ap.parse_args()
    targets: dict[str, tuple[str, bool]] = {}
    for t in a.target:
        name, url = t.split("=", 1)
        hq = url.endswith(":hq")
        targets[name] = (url[:-3] if hq else url, hq)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for k in range(1, a.runs + 1):
        for name, (api, hq) in targets.items():   # one job at a time: the hosted account takes one request at once
            res = await one_job(a, name, api, hq, k)
            rows.append(res)
            print(json.dumps({key: res.get(key) for key in ("target", "run", "ok", "turnaround_s", "cached", "backcheck_pct",
                                                              "speed_max", "flagged", "takes", "error")}), flush=True)
            (out / "runs.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    agg = {name: aggregate([r for r in rows if r["target"] == name]) for name in targets}
    setup = {"src": Path(a.src).name, "runs": a.runs, "langs": a.langs, "engine": a.engine, "voice": a.voice,
             "targets": {n: {"api": u, "hq": h} for n, (u, h) in targets.items()}}
    (out / "summary.json").write_text(json.dumps({"setup": setup, "targets": agg, "runs": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "summary.md").write_text(table(agg) + "\n", encoding="utf-8")
    print(table(agg))


if __name__ == "__main__":
    asyncio.run(main())
