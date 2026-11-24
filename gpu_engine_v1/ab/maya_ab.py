#!/usr/bin/env python3
"""Voice A/B kit: the same 20 lines spoken by IndicF5 (:9001) and by Maya 2 (:9042), in one copied voice,
written as two folders of same-named wav files plus a blind pairs folder for the listening page (/listen-test).

    python3 ab/maya_ab.py --store <data>/local_db.json --voice <voice profile id> --out <folder>
        [--lines ab/voice_lines.tsv] [--indicf5 http://127.0.0.1:9001] [--maya http://127.0.0.1:9042]
        [--voices-dir <data>/voices] [--nfe 16] [--seed 1] [--dry-run] [--pairs-only]

Out:
    <folder>/indicf5/<id>.wav      <folder>/maya/<id>.wav          the same file names in both
    <folder>/pairs/<id>_a.wav, <id>_b.wav, pairs.json               which system is A changes from pair to pair
    <folder>/timing.json                                            time to make each line, per system

Consent: the voice is taken from the store and only when its profile has `consent_at` (and is not deleted).
There is no way to give this script a sample directly, so it cannot copy a voice nobody agreed to.

One GPU serves everything: before it speaks, the script asks the v0 and v1 backends for live sessions and
refuses while a stream is live (`--busy`, `--force` to go on regardless).

Needs only Python 3.8+ (no packages). Works wherever both servers answer: on the GPU machine, or on the laptop
with 9001 through the tunnel and one more forwarded port for 9042.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy"))
import kit  # noqa: E402  (the deploy kit's small HTTP helpers)

SYSTEMS = ("indicf5", "maya")
INDICF5_LANGS = ("hi-IN", "ta-IN", "te-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "gu-IN", "pa-IN")   # no English


def read_lines(path: Path) -> List[Dict[str, str]]:
    rows, seen = [], set()
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) != 3 or not all(p.strip() for p in parts):
            raise SystemExit("%s line %d: expected id<TAB>language<TAB>line" % (path, n))
        lid, lang, text = (p.strip() for p in parts)
        if lid in seen:
            raise SystemExit("%s line %d: id %s is there twice" % (path, n, lid))
        seen.add(lid)
        rows.append({"id": lid, "lang": lang, "text": text})
    return rows


def consented_voice(store: Path, voice_id: str, voices_dir: Optional[Path]) -> Dict[str, Any]:
    """The voice profile's sample and its words, or SystemExit: no consent on record, no copy."""
    try:
        db = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit("cannot read the store %s: %s" % (store, e))
    rows = db.get("voice_profiles") or []
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    p = next((r for r in rows if str(r.get("id")) == voice_id), None)
    if p is None:
        raise SystemExit("no voice profile %s in %s" % (voice_id, store))
    if not p.get("consent_at") or p.get("deleted_at"):
        raise SystemExit("REFUSED: voice profile %s has no consent on record (or was deleted). Nothing was copied." % voice_id)
    if not p.get("ref_path") or not str(p.get("ref_text") or "").strip():
        raise SystemExit("voice profile %s has no stored sample with its words (record the voice on /streamer first)" % voice_id)
    sample = (voices_dir or store.parent / "voices") / str(p["ref_path"])
    if not sample.is_file():
        raise SystemExit("the sample file is not there: %s" % sample)
    return {"id": voice_id, "sample": sample, "text": str(p["ref_text"]).strip(), "consent_at": p["consent_at"]}


def live_now(urls: List[str]) -> List[str]:
    """Backends that report a live session (a backend that does not answer counts as not live)."""
    busy = []
    for u in urls:
        try:
            code, _h, body = kit.http("GET", u.rstrip("/") + "/api/live/sessions", timeout=5)
        except (OSError, ValueError):
            continue
        if code == 200 and b'"status":"live"' in body.replace(b'": "', b'":"'):
            busy.append(u)
    return busy


def write_wav(path: Path, pcm: bytes, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm[: len(pcm) // 2 * 2])


def speak(base: str, session: str, line: Dict[str, str], nfe: int) -> Tuple[bytes, int, float]:
    t0 = time.perf_counter()
    h, pcm = kit.post_json(base + "/tts", {"session_id": session, "text": line["text"], "lang": line["lang"],
                                           "speed": 1.0, "fmt": "pcm", "nfe": nfe})
    ms = (time.perf_counter() - t0) * 1000
    kit.need(len(pcm) > 4000, "almost no audio came back")
    return pcm, int(h.get("x-sample-rate", "24000")), ms


def run_system(name: str, base: str, voice: Dict[str, Any], lines: List[Dict[str, str]], out: Path, nfe: int,
               session: str) -> Dict[str, Any]:
    """Register the voice once, speak every line; a line that fails is noted and left out."""
    report: Dict[str, Any] = {"url": base, "lines": {}, "failed": {}}
    r = kit.post_form(base + "/ref", {"session_id": session, "ref_text": voice["text"], "lang": "hi-IN"},
                      {"audio": (voice["sample"].name, voice["sample"].read_bytes())})
    kit.need(bool(r.get("ok")), "%s did not take the sample: %s" % (name, r))
    for ln in lines:
        try:
            pcm, sr, ms = speak(base, session, ln, nfe if name == "indicf5" else 0)
        except Exception as e:  # noqa: BLE001 - one line failing must not lose the others
            report["failed"][ln["id"]] = "%s: %s" % (type(e).__name__, str(e)[:160])
            print("  %-8s %s FAILED %s" % (name, ln["id"], report["failed"][ln["id"]]), flush=True)
            continue
        write_wav(out / name / (ln["id"] + ".wav"), pcm, sr)
        report["lines"][ln["id"]] = {"ms": round(ms), "audio_s": round(len(pcm) / 2 / sr, 2)}
        print("  %-8s %s %5.0f ms  %.2f s of audio" % (name, ln["id"], ms, len(pcm) / 2 / sr), flush=True)
    return report


def build_pairs(out: Path, lines: List[Dict[str, str]], seed: int, test: str = "maya-vs-indicf5") -> Dict[str, Any]:
    """The blind pairs folder from the two folders of same-named files. Which system is clip A is drawn per pair
    (seeded, so a rebuild gives the same order); the file names in the folder do not say which is which."""
    rng = random.Random(seed)
    pairs_dir = out / "pairs"
    pairs_dir.mkdir(parents=True, exist_ok=True)
    pairs, missing = [], []
    for ln in lines:
        files = {s: out / s / (ln["id"] + ".wav") for s in SYSTEMS}
        if not all(f.is_file() for f in files.values()):
            missing.append(ln["id"])
            continue
        order = list(SYSTEMS)
        rng.shuffle(order)
        a, b = ln["id"] + "_a.wav", ln["id"] + "_b.wav"
        shutil.copyfile(str(files[order[0]]), str(pairs_dir / a))
        shutil.copyfile(str(files[order[1]]), str(pairs_dir / b))
        pair = {"id": ln["id"], "lang": ln["lang"], "text": ln["text"], "a": a, "b": b,
                "a_system": order[0], "b_system": order[1]}
        if ln["lang"] not in INDICF5_LANGS:
            pair["note"] = "IndicF5 was not trained on this language"
        pairs.append(pair)
    manifest = {"test": test, "systems": list(SYSTEMS), "seed": seed, "pairs": pairs, "missing": missing}
    (pairs_dir / "pairs.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--store", type=Path, help="the v1 store (local_db.json) that holds the voice profile")
    ap.add_argument("--voice", help="voice profile id; it must carry consent")
    ap.add_argument("--voices-dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lines", type=Path, default=here / "voice_lines.tsv")
    ap.add_argument("--indicf5", default="http://127.0.0.1:9001")
    ap.add_argument("--maya", default="http://127.0.0.1:9042")
    ap.add_argument("--nfe", type=int, default=16, help="IndicF5 steps (16 = what a recorded voice gets in the product)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--busy", action="append", default=None, help="backends asked for live sessions first")
    ap.add_argument("--force", action="store_true", help="speak even while a stream is live")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pairs-only", action="store_true", help="only rebuild pairs/ from the two folders")
    a = ap.parse_args(argv)
    lines = read_lines(a.lines)
    print("%d lines (%s)" % (len(lines), ", ".join(sorted({ln["lang"] for ln in lines}))))
    if a.pairs_only:
        m = build_pairs(a.out, lines, a.seed)
        print("pairs: %d written to %s, %d missing" % (len(m["pairs"]), a.out / "pairs", len(m["missing"])))
        return 0 if m["pairs"] else 1
    if not (a.store and a.voice):
        ap.error("--store and --voice are needed (the voice must come from a profile with consent)")
    voice = consented_voice(a.store, a.voice, a.voices_dir)
    print("voice %s: consent of %s, sample %s" % (voice["id"], voice["consent_at"], voice["sample"].name))
    urls = {"indicf5": a.indicf5.rstrip("/"), "maya": a.maya.rstrip("/")}
    if a.dry_run:
        for name in SYSTEMS:
            print("would send the sample and %d lines to %s (%s)" % (len(lines), name, urls[name]))
        print("would write %s/{indicf5,maya}/<id>.wav, pairs/ and timing.json" % a.out)
        return 0
    busy = live_now(a.busy if a.busy is not None else ["http://127.0.0.1:8010", "http://127.0.0.1:8110"])
    if busy and not a.force:
        print("REFUSED: a stream is live on %s. One GPU serves everything; run this when nobody is live." % ", ".join(busy))
        return 3
    session = "abkit-%d" % int(time.time())
    timing: Dict[str, Any] = {"voice": voice["id"], "lines_file": a.lines.name, "systems": {}}
    for name in SYSTEMS:
        print("%s at %s" % (name, urls[name]), flush=True)
        try:
            timing["systems"][name] = run_system(name, urls[name], voice, lines, a.out, a.nfe, session)
        except Exception as e:  # noqa: BLE001
            print("FAILED: %s does not work: %s: %s" % (name, type(e).__name__, str(e)[:200]))
            return 1
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
    m = build_pairs(a.out, lines, a.seed)
    for name in SYSTEMS:
        ms = sorted(v["ms"] for v in timing["systems"][name]["lines"].values())
        if ms:
            print("%-8s %d lines, time to make a line: median %d ms, range %d-%d ms; %d failed" % (
                name, len(ms), ms[len(ms) // 2], ms[0], ms[-1], len(timing["systems"][name]["failed"])))
    print("pairs: %d in %s (%d lines without a pair)" % (len(m["pairs"]), a.out / "pairs", len(m["missing"])))
    return 0 if m["pairs"] else 1


if __name__ == "__main__":
    sys.exit(main())
