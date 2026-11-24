"""Translation A/B: the same fixed lines through two translation models, a blind sheet for a person, a verdict.

Three steps (from `backend/`); the two models need not be loaded at the same time:

  python -m eval.v1.llm_ab run --name current --url http://127.0.0.1:9020/v1 --model local --out <folder>
  python -m eval.v1.llm_ab run --name big12   --url http://127.0.0.1:9044/v1 --model big   --out <folder>
  python -m eval.v1.llm_ab sheet --a current --b big12 --out <folder>
        -> side_by_side.csv (fill the `better` column: X, Y or same), side_by_side.md, key.json, auto.json
  python -m eval.v1.llm_ab verdict --a current --b big12 --out <folder>

The set: the 24 class lines of `hard_set.json` and the 16 stream lines of `translate_lines.txt`, into Tamil, Bengali
and Punjabi (40 x 3 = 120 lines a model). The prompt is the product's own (`LocalLLM.translate_batch`, what Studio
sends our own model), in batches of 8 lines as a short video would give them. `--mode live` sends them one at a
time with the live prompt instead, which is what a Live phrase costs.

What "wins" means is fixed here, before any result exists (WIN_RULE). The candidate (b) wins over (a) when:
  1. a person preferred b in at least 60% of the pairs they decided (not "same"), on at least 40 decided pairs;
  2. in no language b was preferred in under 50% of that language's decided pairs (at least 10 decided each);
  3. b has no more lines in a wrong script or with Latin letters than a, and no empty line;
  4. b's lines are not longer: median of (letters in b / letters in a) at most 1.10 (a longer line is a later dub);
  5. b is fast enough for Studio: median time per line at most 2.0 s in batch mode.
Reported beside it, not part of the rule: whether b would be fast enough for Live (live mode: median at most
0.6 s and 95th percentile at most 1.0 s a phrase, about what the model on 9020 does through the tunnel).

One GPU serves everything: `run` asks the v0 and v1 backends for live sessions first and waits while one is live.
"""
import argparse
import asyncio
import csv
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
LANGS = ("ta-IN", "bn-IN", "pa-IN")
BATCH = 8
WIN_RULE = {"prefer_share": 0.60, "decided_min": 40, "lang_share_min": 0.50, "lang_decided_min": 10,
            "length_ratio_max": 1.10, "studio_line_s_max": 2.0, "live_p50_s_max": 0.6, "live_p95_s_max": 1.0}


def fixed_lines() -> list[dict[str, str]]:
    rows = [{"id": f"class{i:02d}", "text": r["text"]}
            for i, r in enumerate(json.loads((HERE / "hard_set.json").read_text(encoding="utf-8")))]
    stream = [ln.strip() for ln in (HERE / "translate_lines.txt").read_text(encoding="utf-8").splitlines()
              if ln.strip() and not ln.startswith("#")]
    return rows + [{"id": f"stream{i:02d}", "text": t} for i, t in enumerate(stream)]


def translator(url: str, model: str, client: httpx.AsyncClient | None = None) -> Any:
    """Our own-model translator pointed at `url`, built the way the product builds it."""
    from pydantic import SecretStr

    from app.config import get_settings
    from app.providers.llm_local import LocalLLM
    s = get_settings().model_copy(update={
        "llm_base_url": url, "llm_model": model, "llm_model_fast": "", "llm_api_key": SecretStr("local"),
        "llm_reasoning_effort": "", "llm_reasoning_effort_fast": ""})
    return LocalLLM(s, client) if client is not None else LocalLLM(s)


async def live_on(urls: list[str]) -> list[str]:
    out = []
    async with httpx.AsyncClient(timeout=5.0) as c:
        for u in urls:
            try:
                rows = (await c.get(u.rstrip("/") + "/api/live/sessions")).json()
            except (httpx.HTTPError, ValueError):
                continue
            if any(isinstance(r, dict) and r.get("status") == "live" for r in rows if isinstance(rows, list)):
                out.append(u)
    return out


async def wait_quiet(urls: list[str], wait_min: float) -> list[str]:
    deadline = time.monotonic() + wait_min * 60
    while True:
        busy = await live_on(urls)
        if not busy or time.monotonic() >= deadline:
            return busy
        print(f"waiting: a stream is live ({', '.join(busy)})", flush=True)
        await asyncio.sleep(60)


async def run_model(llm: Any, lines: list[dict[str, str]], langs: tuple[str, ...], mode: str) -> dict[str, Any]:
    """Every line into every language; one call at a time, so the times are the model's and not a queue's."""
    results, calls = [], []
    for lang in langs:
        if mode == "live":
            for i, ln in enumerate(lines):
                t0 = time.perf_counter()
                try:
                    out = await llm.translate_chunk(ln["text"], lang, [], [x["text"] for x in lines[max(0, i - 3):i]],
                                                    native=True)
                except Exception as e:  # noqa: BLE001 - a failed line is a result
                    out = ""
                    print(f"  {lang} {ln['id']} failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
                s = time.perf_counter() - t0
                calls.append({"lang": lang, "lines": 1, "s": round(s, 3)})
                results.append({"id": ln["id"], "lang": lang, "src": ln["text"], "out": out, "s": round(s, 3)})
        else:
            for k in range(0, len(lines), BATCH):
                part = lines[k:k + BATCH]
                t0 = time.perf_counter()
                try:
                    outs = await llm.translate_batch([x["text"] for x in part], lang, [])
                except Exception as e:  # noqa: BLE001
                    outs = [""] * len(part)
                    print(f"  {lang} batch {k // BATCH} failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
                s = time.perf_counter() - t0
                calls.append({"lang": lang, "lines": len(part), "s": round(s, 3)})
                results += [{"id": x["id"], "lang": lang, "src": x["text"], "out": o, "s": round(s / len(part), 3)}
                            for x, o in zip(part, outs)]
        print(f"  {lang}: {sum(1 for r in results if r['lang'] == lang)} lines", flush=True)
    return {"mode": mode, "results": results, "calls": calls}


def letters(text: str) -> int:
    return sum(1 for ch in text if ch.isalnum())


def pct(values: list[float], q: float) -> float:
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))] if v else 0.0


def auto_checks(run: dict[str, Any]) -> dict[str, Any]:
    """What can be counted without a person: lines the voice engine could not read, empty lines, times."""
    from app.providers.llm_local import has_latin
    from app.providers.llm_openai import wrong_script
    rows = run["results"]
    per_line = [r["s"] for r in rows]
    return {"lines": len(rows), "empty": sum(1 for r in rows if not r["out"].strip()),
            "wrong_script_or_latin": sum(1 for r in rows if r["out"].strip()
                                         and (wrong_script(r["out"], r["lang"]) or has_latin(r["out"]))),
            "line_s_median": round(statistics.median(per_line), 3) if per_line else None,
            "line_s_p95": round(pct(per_line, 0.95), 3) if per_line else None,
            "call_s_median": round(statistics.median([c["s"] for c in run["calls"]]), 3) if run["calls"] else None}


def paired(a: dict[str, Any], b: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    index = {(r["id"], r["lang"]): r for r in b["results"]}
    return [(r, index[(r["id"], r["lang"])]) for r in a["results"] if (r["id"], r["lang"]) in index]


def length_ratio(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    ratios = [letters(y["out"]) / letters(x["out"]) for x, y in paired(a, b) if letters(x["out"]) and letters(y["out"])]
    return round(statistics.median(ratios), 3) if ratios else None


def make_sheet(a: dict[str, Any], b: dict[str, Any], names: tuple[str, str], out: Path, seed: int = 1) -> dict[str, Any]:
    """The blind sheet: per line the source and the two translations as X and Y; which model is X is drawn per
    line (seeded) and kept in key.json, away from the sheet."""
    rng = random.Random(seed)
    key, rows = {}, []
    for x, y in paired(a, b):
        pid = f"{x['id']}:{x['lang']}"
        a_is_x = rng.random() < 0.5
        key[pid] = {"X": names[0] if a_is_x else names[1], "Y": names[1] if a_is_x else names[0]}
        rows.append({"pair": pid, "lang": x["lang"], "source": x["src"], "X": (x if a_is_x else y)["out"],
                     "Y": (y if a_is_x else x)["out"], "better": "", "note": ""})
    out.mkdir(parents=True, exist_ok=True)
    with (out / "side_by_side.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pair", "lang", "source", "X", "Y", "better", "note"])
        w.writeheader()
        w.writerows(rows)
    md = ["# Translation A/B: which line would you rather hear?", "",
          "Fill the `better` column of `side_by_side.csv` with X, Y or same. Which model is X changes per line.", ""]
    for r in rows:
        md += [f"**{r['pair']}**  ", f"source: {r['source']}  ", f"X: {r['X']}  ", f"Y: {r['Y']}", ""]
    (out / "side_by_side.md").write_text("\n".join(md), encoding="utf-8")
    (out / "key.json").write_text(json.dumps({"seed": seed, "a": names[0], "b": names[1], "pairs": key},
                                             ensure_ascii=False, indent=1), encoding="utf-8")
    auto = {"a": {"name": names[0], "mode": a["mode"], **auto_checks(a)},
            "b": {"name": names[1], "mode": b["mode"], **auto_checks(b)},
            "length_ratio_b_over_a": length_ratio(a, b), "pairs": len(rows), "rule": WIN_RULE}
    (out / "auto.json").write_text(json.dumps(auto, ensure_ascii=False, indent=1), encoding="utf-8")
    return auto


def read_votes(sheet: Path, key: dict[str, Any]) -> dict[str, dict[str, int]]:
    """lang -> {"a": n, "b": n, "same": n} from the filled sheet, unblinded with the key."""
    votes: dict[str, dict[str, int]] = {}
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            v = (r.get("better") or "").strip().upper()
            k = key["pairs"].get(r.get("pair", ""))
            if not k or v not in ("X", "Y", "SAME"):
                continue
            tally = votes.setdefault(r["lang"], {"a": 0, "b": 0, "same": 0})
            tally["same" if v == "SAME" else ("a" if k[v] == key["a"] else "b")] += 1
    return votes


def verdict(votes: dict[str, dict[str, int]], auto: dict[str, Any], rule: dict[str, float] | None = None) -> dict[str, Any]:
    """Applies WIN_RULE. `wins` is True, False, or None when there are not enough votes to say."""
    rule = rule or WIN_RULE
    a_n, b_n = sum(v["a"] for v in votes.values()), sum(v["b"] for v in votes.values())
    decided = a_n + b_n
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool | None, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    share = b_n / decided if decided else None
    add("preferred overall", None if decided < rule["decided_min"] else share >= rule["prefer_share"],
        f"b preferred in {b_n} of {decided} decided pairs" + (f" ({share:.0%})" if share is not None else "")
        + f"; needs {rule['prefer_share']:.0%} of at least {rule['decided_min']:.0f}")
    for lang in sorted(votes):
        d = votes[lang]["a"] + votes[lang]["b"]
        add(f"preferred in {lang}", None if d < rule["lang_decided_min"] else votes[lang]["b"] / d >= rule["lang_share_min"],
            f"b preferred in {votes[lang]['b']} of {d} decided; needs {rule['lang_share_min']:.0%} of at least "
            f"{rule['lang_decided_min']:.0f}")
    if not votes:
        add("preferred per language", None, "no votes in the sheet yet")
    a, b = auto["a"], auto["b"]
    add("script", b["wrong_script_or_latin"] <= a["wrong_script_or_latin"] and b["empty"] == 0,
        f"b: {b['wrong_script_or_latin']} lines in a wrong script or with Latin letters, {b['empty']} empty; "
        f"a: {a['wrong_script_or_latin']}, {a['empty']}")
    ratio = auto.get("length_ratio_b_over_a")
    add("length", None if ratio is None else ratio <= rule["length_ratio_max"],
        f"median letters b / a = {ratio}; at most {rule['length_ratio_max']}")
    if b["mode"] == "batch":
        add("fast enough for Studio", None if b["line_s_median"] is None else b["line_s_median"] <= rule["studio_line_s_max"],
            f"b: median {b['line_s_median']} s a line; at most {rule['studio_line_s_max']} s")
    else:
        add("fast enough for Studio", None, "b was run in live mode; run it in batch mode for this check")
    oks = [c["ok"] for c in checks]
    wins = False if any(o is False for o in oks) else (None if any(o is None for o in oks) else True)
    live = None
    if b["mode"] == "live" and b["line_s_median"] is not None:
        live = b["line_s_median"] <= rule["live_p50_s_max"] and b["line_s_p95"] <= rule["live_p95_s_max"]
    return {"wins": wins, "checks": checks, "votes": votes, "fit_for_live": live}


def load_run(out: Path, name: str) -> dict[str, Any]:
    p = out / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"no run called {name!r} in {out} (make it with `run --name {name}`)")
    return json.loads(p.read_text(encoding="utf-8"))


async def cmd_run(a: argparse.Namespace) -> int:
    busy = await wait_quiet(a.busy if a.busy is not None else ["http://127.0.0.1:8010", "http://127.0.0.1:8110"],
                            a.busy_wait_min)
    if busy:
        print(f"SKIPPED: a stream is still live ({', '.join(busy)}); nothing was sent")
        return 3
    lines = fixed_lines()[: a.limit or None]
    langs = tuple(x for x in a.langs.split(",") if x)
    print(f"{a.name}: {len(lines)} lines x {len(langs)} languages, {a.mode} mode, {a.url} ({a.model})", flush=True)
    run = await run_model(translator(a.url, a.model), lines, langs, a.mode)
    run.update({"name": a.name, "url": a.url, "model": a.model, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"{a.name}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(auto_checks(run), indent=1))
    return 0


def cmd_sheet(a: argparse.Namespace) -> int:
    auto = make_sheet(load_run(a.out, a.a), load_run(a.out, a.b), (a.a, a.b), a.out, a.seed)
    print(json.dumps({k: v for k, v in auto.items() if k != "rule"}, indent=1))
    print(f"sheet: {a.out / 'side_by_side.csv'} ({auto['pairs']} pairs). Fill `better` with X, Y or same.")
    return 0


def cmd_verdict(a: argparse.Namespace) -> int:
    key = json.loads((a.out / "key.json").read_text(encoding="utf-8"))
    auto = json.loads((a.out / "auto.json").read_text(encoding="utf-8"))
    if (key["a"], key["b"]) != (a.a, a.b):
        raise SystemExit(f"the sheet in {a.out} compares {key['a']} with {key['b']}, not {a.a} with {a.b}")
    v = verdict(read_votes(a.votes or a.out / "side_by_side.csv", key), auto)
    for c in v["checks"]:
        print(f"{'ok ' if c['ok'] else 'NO ' if c['ok'] is False else '?  '} {c['check']}: {c['detail']}")
    word = {True: f"{a.b} WINS over {a.a}", False: f"{a.b} DOES NOT WIN over {a.a}",
            None: "NOT DECIDED: a check above has too few votes or no number"}[v["wins"]]
    print("VERDICT: " + word)
    if v["fit_for_live"] is not None:
        print(f"fast enough for Live: {'yes' if v['fit_for_live'] else 'no'}")
    (a.out / "verdict.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Translation A/B with a blind sheet and a fixed rule for winning.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--name", required=True)
    r.add_argument("--url", required=True, help="OpenAI-compatible base, e.g. http://127.0.0.1:9020/v1")
    r.add_argument("--model", required=True, help="the name the server serves the model under (9020: local, 9044: big)")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--mode", choices=("batch", "live"), default="batch")
    r.add_argument("--langs", default=",".join(LANGS))
    r.add_argument("--limit", type=int, default=0, help="only the first N lines (a quick check)")
    r.add_argument("--busy", action="append", default=None)
    r.add_argument("--busy-wait-min", type=float, default=30.0)
    for name in ("sheet", "verdict"):
        s = sub.add_parser(name)
        s.add_argument("--a", required=True, help="the model in use (run name)")
        s.add_argument("--b", required=True, help="the candidate (run name)")
        s.add_argument("--out", type=Path, required=True)
        s.add_argument("--seed", type=int, default=1)
        s.add_argument("--votes", type=Path, help="the filled sheet, when it is not <out>/side_by_side.csv")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return asyncio.run(cmd_run(a))
    return cmd_sheet(a) if a.cmd == "sheet" else cmd_verdict(a)


if __name__ == "__main__":
    raise SystemExit(main())
