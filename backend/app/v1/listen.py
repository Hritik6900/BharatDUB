"""Blind listening test (`V1_LISTEN_TEST`): pairs of clips from two systems, rated by people who are not told
which is which. Page `/listen-test`; summary on `/metrics-ui`.

Everything lives under `<DATA_DIR>/listen/` (never in the repository):
  pairs/manifest.json   the pairs (below); built by hand or by `scripts/v1/make-listen-pairs.py`
  pairs/...             the clips the manifest names, paths relative to `pairs/`
  results.jsonl         one line per answer: when, listener (a random id made by the browser), pair, the two
                        systems, the rating each got, which was preferred, and which system was played first

Manifest:
  {"name": "indicf5 against <other>, Tamil, 25 Nov",          (optional; stored with every answer)
   "pairs": [{"id": "ta_001",                                  unique, letters digits _ - only
              "a": "indicf5/ta_001.wav", "b": "other/ta_001.wav",
              "system_a": "indicf5", "system_b": "other",      which system made each clip (never sent to the page)
              "lang": "ta-IN",                                 optional
              "text": "the words both clips should say"}]}      optional; shown to the listener when present

Blind: the page gets, per pair, two sounds called "first" and "second" and nothing else; which system is first
is decided by a hash of the listener's id and the pair's id, so it differs between listeners and stays the same
for one listener. The sounds are served by pair id and position, never by file name or system.

A listener's later answer for a pair replaces their earlier one. Summary per system: mean rating (1-5), how
many ratings, and its share of the stated preferences ("same" counts for neither and is given by itself).
"""
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import get_settings

router = APIRouter()
ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SIDES = ("1", "2")
_lock = threading.Lock()


def folder() -> Path:
    """Where the test lives. Only names the place: nothing is created here."""
    s = get_settings()
    return Path(s.v1_listen_dir) if s.v1_listen_dir else s.data_path / "listen"


def manifest() -> dict[str, Any]:
    """The pairs that can be played: a well-formed entry whose two clips exist inside the pairs folder."""
    base = folder() / "pairs"
    try:
        raw = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"name": "", "pairs": []}
    root, pairs, seen = base.resolve(), [], set()
    for p in raw.get("pairs") or []:
        try:
            pid, sa, sb = str(p["id"]), str(p["system_a"]), str(p["system_b"])
            fa, fb = (base / str(p["a"])).resolve(), (base / str(p["b"])).resolve()
        except (KeyError, TypeError, ValueError, OSError):
            continue
        ok = ID.match(pid) and pid not in seen and sa and sb and sa != sb
        if not ok or not all(f.is_file() and root in f.parents for f in (fa, fb)):
            continue
        seen.add(pid)
        pairs.append({"id": pid, "files": {sa: fa, sb: fb}, "systems": (sa, sb), "lang": str(p.get("lang") or ""),
                      "text": str(p.get("text") or "")})
    return {"name": str(raw.get("name") or ""), "pairs": pairs}


def order(listener: str, pair: dict[str, Any]) -> tuple[str, str]:
    """The systems in the order this listener hears them (first, second)."""
    a, b = pair["systems"]
    flip = hashlib.sha256(f"{listener}|{pair['id']}".encode("utf-8")).digest()[0] & 1
    return (b, a) if flip else (a, b)


def results() -> list[dict[str, Any]]:
    """Every answer that counts: the last one of each listener for each pair."""
    p = folder() / "results.jsonl"
    last: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        lines = p.read_text(encoding="utf-8").splitlines() if p.is_file() else []
    except OSError:
        lines = []
    for line in lines:
        try:
            r = json.loads(line)
            last[(str(r["listener"]), str(r["pair"]))] = r
        except (ValueError, KeyError, TypeError):
            continue
    return list(last.values())


def queue(listener: str) -> dict[str, Any]:
    m = manifest()
    done = {r["pair"] for r in results() if r.get("listener") == listener}
    todo = [p for p in m["pairs"] if p["id"] not in done]
    todo.sort(key=lambda p: hashlib.sha256(f"{listener}#{p['id']}".encode("utf-8")).hexdigest())   # own order per listener
    return {"name": m["name"], "total": len(m["pairs"]), "done": len(done & {p["id"] for p in m["pairs"]}),
            "pairs": [{"id": p["id"], "lang": p["lang"], "text": p["text"]} for p in todo]}


def save(listener: str, pair_id: str, rating_1: int, rating_2: int, prefer: str) -> dict[str, Any]:
    m = manifest()
    pair = next((p for p in m["pairs"] if p["id"] == pair_id), None)
    if pair is None:
        raise KeyError(pair_id)
    first, second = order(listener, pair)
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "listener": listener, "pair": pair_id,
           "set": m["name"], "lang": pair["lang"], "first": first,
           "ratings": {first: rating_1, second: rating_2},
           "prefer": {"1": first, "2": second}.get(prefer, "same")}
    d = folder()
    with _lock:
        d.mkdir(parents=True, exist_ok=True)
        with (d / "results.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def summary() -> dict[str, Any]:
    rows = results()
    m = manifest()
    systems: dict[str, dict[str, Any]] = {}
    stated = same = 0
    for r in rows:
        for name, rating in (r.get("ratings") or {}).items():
            s = systems.setdefault(name, {"ratings": [], "preferred": 0, "first": 0})
            s["ratings"].append(int(rating))
            s["first"] += int(r.get("first") == name)
        if r.get("prefer") == "same":
            same += 1
        elif r.get("prefer") in (r.get("ratings") or {}):
            stated += 1
            systems[r["prefer"]]["preferred"] += 1
    out = {name: {"n": len(s["ratings"]), "mean_rating": round(sum(s["ratings"]) / len(s["ratings"]), 2),
                  "preferred": s["preferred"],
                  "preference_pct": round(100 * s["preferred"] / stated, 1) if stated else None,
                  "played_first": s["first"]}
           for name, s in sorted(systems.items())}
    return {"answers": len(rows), "listeners": len({r.get("listener") for r in rows}), "pairs": len(m["pairs"]),
            "pairs_rated": len({r.get("pair") for r in rows}), "set": m["name"], "same": same, "stated": stated,
            "systems": out, "note": "" if rows else "no ratings yet"}


# ---------- routes ----------
def _on() -> None:
    if not get_settings().v1_listen_test:
        raise HTTPException(404, "The listening test is switched off (V1_LISTEN_TEST).")


def _listener(value: str) -> str:
    if not ID.match(value or ""):
        raise HTTPException(400, "listener is an id of letters, digits, _ and -")
    return value


class Answer(BaseModel):
    listener: str
    pair: str
    rating_1: int = Field(ge=1, le=5)
    rating_2: int = Field(ge=1, le=5)
    prefer: str     # "1" | "2" | "same"


@router.get("/api/v1/listen/pairs")
async def listen_pairs(listener: str) -> dict[str, Any]:
    """The pairs this listener has not answered, in their own order. No system names, no file names."""
    _on()
    return queue(_listener(listener))


@router.get("/api/v1/listen/audio/{pair_id}/{side}")
async def listen_audio(pair_id: str, side: str, listener: str) -> FileResponse:
    _on()
    _listener(listener)
    pair = next((p for p in manifest()["pairs"] if p["id"] == pair_id), None)
    if pair is None or side not in SIDES:
        raise HTTPException(404, "no such clip")
    path = pair["files"][order(listener, pair)[SIDES.index(side)]]
    # no file name and no caching: the response must not tell the two systems apart
    kind = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".flac": "audio/flac"}.get(path.suffix.lower(), "audio/wav")
    return FileResponse(path, media_type=kind, headers={"Cache-Control": "no-store"})


@router.post("/api/v1/listen/answers")
async def listen_answer(body: Answer) -> dict[str, Any]:
    _on()
    if body.prefer not in (*SIDES, "same"):
        raise HTTPException(400, "prefer is 1, 2 or same")
    try:
        save(_listener(body.listener), body.pair, body.rating_1, body.rating_2, body.prefer)
    except KeyError:
        raise HTTPException(404, "no such pair") from None
    return {"ok": True}


@router.get("/api/v1/listen/summary")
async def listen_summary() -> dict[str, Any]:
    _on()
    return summary()
