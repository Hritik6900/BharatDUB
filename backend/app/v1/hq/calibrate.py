"""Studio HQ: calibrating the heard-back judge against a person's ear (`V1_HQ_CALIBRATE`).

The judge gives every take of a dubbed line a score (share of its words heard back) and a line under
`v1_hq_backcheck_min` is flagged. Whether that line is the right one is not known until a person has listened.
This module serves takes blind (the audio and the words it should say, never its score), stores a good/bad
label per take, and compares the labels with the scores.

Storage, all under `<DATA_DIR>/calibration/` (never in the repository):
  labels.jsonl     one line per label: when, which take, good or bad, and the take's language, score, judge and
                   rule at that moment (so a label outlives its job)
  hearings.json    optional: what the judge heard for takes whose job did not store it (written by
                   `python -m eval.v1.rescore`), so old takes are scored under the rule in use

The recommendation (`summary`): every threshold between two neighbouring scores is tried; a line under the
threshold is "flagged". The threshold with the highest balanced accuracy, the mean of
  bad lines that are flagged / all bad lines   and   good lines that are not flagged / all good lines,
is recommended; of equal ones the one nearest the threshold in use. Nothing is recommended under
`v1_hq_calibrate_min_labels` labels or with fewer than 5 good or 5 bad ones.
"""
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.v1.qa import HEARD_RULE, heard_share, rule_now

LABELS = ("good", "bad")
MIN_EACH = 5
BANDS = (0.7, 0.85, 0.95)     # the queue takes turns over these score bands so labels cover the whole range
_lock = threading.Lock()


def folder() -> Path:
    d = get_settings().data_path / "calibration"
    d.mkdir(parents=True, exist_ok=True)
    return d


def item_id(path: str, text: str) -> str:
    return hashlib.sha256(f"{Path(path).name}|{text}".encode("utf-8")).hexdigest()[:20]


def _hearings() -> dict[str, Any]:
    p = folder() / "hearings.json"
    try:
        return dict(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else {}
    except (OSError, ValueError):
        return {}


async def items(store: Any) -> list[dict[str, Any]]:
    """Every take of every HQ line that has a score and its audio on disk."""
    data = get_settings().data_path.resolve()
    rule = rule_now()
    known = _hearings()
    segs = {s["id"]: s for s in await store.select("segments")}
    out: dict[str, dict[str, Any]] = {}
    for t in await store.select("translations"):
        seg = segs.get(t.get("segment_id"))
        for a in t.get("alts") or []:
            path = Path(str(a.get("path") or ""))
            if a.get("backcheck") is None or not path.is_file() or data not in path.resolve().parents:
                continue
            iid = item_id(str(path), a.get("text") or "")
            heard = a.get("heard") if a.get("heard") is not None else (known.get(iid) or {}).get("heard")
            used = a.get("rule") or HEARD_RULE
            score = float(a["backcheck"])
            if heard is not None and used != rule:
                score, used = round(heard_share(a.get("text") or "", heard, rule), 3), rule
            out[iid] = {"id": iid, "lang": t.get("lang"), "text": a.get("text") or "", "path": str(path),
                        "score": score, "rule": used, "judge": a.get("scored_by") or (known.get(iid) or {}).get("by") or "",
                        "provider": a.get("provider") or "", "job": (seg or {}).get("job_id") or "",
                        "kept": a.get("idx") == t.get("picked")}
    return list(out.values())


def labels() -> dict[str, dict[str, Any]]:
    """The last label of every take."""
    p = folder() / "labels.jsonl"
    out: dict[str, dict[str, Any]] = {}
    if not p.exists():
        return out
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("label") in LABELS and rec.get("id"):
                out[str(rec["id"])] = rec
            elif rec.get("label") == "undo" and rec.get("id"):
                out.pop(str(rec["id"]), None)
    return out


def add_label(item: dict[str, Any], label: str) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "id": item["id"], "label": label,
           "lang": item.get("lang"), "score": item.get("score"), "rule": item.get("rule"), "judge": item.get("judge"),
           "provider": item.get("provider"), "job": item.get("job")}
    with _lock, open(folder() / "labels.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def queue(all_items: list[dict[str, Any]], done: set[str], lang: str | None = None, n: int = 10) -> list[dict[str, Any]]:
    """The next takes to label: not yet labelled, taking turns over the score bands, in an order that says
    nothing about the score (by the take's id inside a band)."""
    todo = [i for i in all_items if i["id"] not in done and (not lang or i["lang"] == lang)]
    bands: list[list[dict[str, Any]]] = [[] for _ in range(len(BANDS) + 1)]
    for i in sorted(todo, key=lambda i: i["id"]):
        bands[sum(1 for b in BANDS if i["score"] >= b)].append(i)
    out: list[dict[str, Any]] = []
    while len(out) < n and any(bands):
        for b in bands:
            if b and len(out) < n:
                out.append(b.pop(0))
    return sorted(out, key=lambda i: i["id"])     # the order handed out is not the order of the bands


def blind(item: dict[str, Any]) -> dict[str, Any]:
    return {"id": item["id"], "lang": item["lang"], "text": item["text"]}


def _confusion(pairs: list[tuple[float, bool]], threshold: float) -> dict[str, int]:
    c = {"flagged_bad": 0, "flagged_good": 0, "passed_bad": 0, "passed_good": 0}
    for score, good in pairs:
        c[("flagged" if score < threshold else "passed") + ("_good" if good else "_bad")] += 1
    return c


def _balanced(c: dict[str, int]) -> float:
    bad, good = c["flagged_bad"] + c["passed_bad"], c["flagged_good"] + c["passed_good"]
    return (c["flagged_bad"] / bad + c["passed_good"] / good) / 2 if bad and good else 0.0


def agreement(pairs: list[tuple[float, bool]], threshold: float) -> dict[str, Any]:
    c = _confusion(pairs, threshold)
    n = len(pairs)
    agree = (c["flagged_bad"] + c["passed_good"]) / n if n else None
    return {"threshold": threshold, "labels": n, **c,
            "agreement_pct": round(100 * agree, 1) if agree is not None else None,
            "balanced_pct": round(100 * _balanced(c), 1) if n and _balanced(c) else None}


def recommend(pairs: list[tuple[float, bool]], current: float, min_labels: int) -> dict[str, Any]:
    good = sum(1 for _, g in pairs if g)
    bad = len(pairs) - good
    if not pairs:
        return {"threshold": None, "why": "no labels yet"}
    if len(pairs) < min_labels or good < MIN_EACH or bad < MIN_EACH:
        return {"threshold": None, "why": f"not enough labels: {len(pairs)} ({good} good, {bad} bad); a recommendation "
                                          f"needs {min_labels} with at least {MIN_EACH} of each"}
    scores = sorted({s for s, _ in pairs})
    cuts = [round((a + b) / 2, 3) for a, b in zip(scores, scores[1:])] + [round(min(1.0, scores[-1] + 0.001), 3)]
    best = max(cuts, key=lambda t: (round(_balanced(_confusion(pairs, t)), 6), -abs(t - current)))
    return {"threshold": best, "why": "highest balanced accuracy over the labels", **agreement(pairs, best)}


async def summary(store: Any) -> dict[str, Any]:
    s = get_settings()
    its = {i["id"]: i for i in await items(store)}
    labs = labels()
    rule = rule_now(s)
    pairs: list[tuple[float, bool]] = []
    per_lang: dict[str, list[tuple[float, bool]]] = {}
    other_rule = gone = 0
    for iid, rec in labs.items():
        item = its.get(iid)
        score, used = (item["score"], item["rule"]) if item else (rec.get("score"), rec.get("rule"))
        gone += int(item is None)
        if score is None or used != rule:
            other_rule += 1     # scored under another rule than the one in use: not comparable, left out
            continue
        pair = (float(score), rec["label"] == "good")
        pairs.append(pair)
        per_lang.setdefault(str(rec.get("lang") or (item or {}).get("lang") or ""), []).append(pair)
    current = float(s.v1_hq_backcheck_min)
    return {"rule": rule, "takes": len(its), "labelled": len(labs), "used": len(pairs),
            "left_out_other_rule": other_rule, "labelled_takes_no_longer_stored": gone,
            "unlabelled": sum(1 for i in its if i not in labs),
            "good": sum(1 for _, g in pairs if g), "bad": sum(1 for _, g in pairs if not g),
            "threshold_in_use": current, "at_threshold_in_use": agreement(pairs, current) if pairs else None,
            "recommended": recommend(pairs, current, s.v1_hq_calibrate_min_labels),
            "by_lang": {lang: agreement(p, current) for lang, p in sorted(per_lang.items())},
            "note": "no labels yet" if not labs else ""}
