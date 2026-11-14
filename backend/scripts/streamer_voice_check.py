"""Phase 1 of Streamer Mode on the real APIs: make a streamer, record a voice (with consent), preview it.

  python scripts/streamer_voice_check.py <recording.wav|mp4> [--api http://localhost:8010] [--langs ta-IN,bn-IN]

Prints how long the voice took to build, its score, and the preview times; saves the previews to scripts/out/streamer/.
Only use a recording of your own voice, or one you have the speaker's permission for.
"""
import argparse
import time
import uuid
from pathlib import Path

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("recording")
ap.add_argument("--api", default="http://localhost:8010")
ap.add_argument("--langs", default="ta-IN,bn-IN")
ap.add_argument("--name", default="Test streamer")
a = ap.parse_args()
out = Path("scripts/out/streamer")
out.mkdir(parents=True, exist_ok=True)
langs = a.langs.split(",")
consent = f"I, {a.name}, agree that Bharat Dub may make a copy of my voice to dub my streams."

with httpx.Client(base_url=a.api, timeout=180) as c:
    for _ in range(20):
        try:
            c.get("/health")
            break
        except httpx.HTTPError:
            time.sleep(2)
    s = c.post("/api/streamers", json={"handle": "test_" + uuid.uuid4().hex[:8], "display_name": a.name,
                                       "default_langs": langs}).json()
    print("streamer", s["handle"])
    rec = Path(a.recording)
    r = c.post(f"/api/streamers/{s['id']}/voice", files={"sample": (rec.name, rec.read_bytes())},
               data={"consent_text": consent})
    print("without the consent box:", r.status_code)
    t0 = time.perf_counter()
    r = c.post(f"/api/streamers/{s['id']}/voice", files={"sample": (rec.name, rec.read_bytes())},
               data={"consent_text": consent, "consent": "true"})
    total = time.perf_counter() - t0
    r.raise_for_status()
    v = r.json()["voice"]
    print(f"voice recorded in {total:.1f} s (whole request) |", {k: v.get(k) for k in (
        "gnani_clone", "gpu_voice", "ref_score", "ref_seconds", "ref_cleaned", "ref_cuts_tried", "ref_build_s")})
    for lang in langs:
        for n in range(2):
            t0 = time.perf_counter()
            r = c.post(f"/api/streamers/{s['id']}/voice/preview", params={"lang": lang})
            dt = time.perf_counter() - t0
            if r.status_code != 200:
                print(f"preview {lang}: HTTP {r.status_code} {r.text[:120]}")
                break
            f = out / f"{s['handle']}_{lang}.wav"
            f.write_bytes(r.content)
            print(f"preview {lang} #{n + 1}: {dt:.2f} s, engine {r.headers.get('x-engine')}, saved {f}")
    print("id for the next phase:", s["id"])
