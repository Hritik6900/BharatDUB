"""End-to-end Live test against the running backend, real providers.

Plays a video's audio into /ws/ingest at real-time speed (exactly like the mic client), listens on /ws/watch for
every language, posts one viewer chat message, then stops the session and writes everything it measured.

Run from backend/:
  python scripts/live_e2e.py SRC OUTDIR --name NAME --langs ta-IN,bn-IN,en-IN [--voice stream|stock|<profile id>]
                     [--loops 2] [--yt ID] [--api http://localhost:8010]
"""
import argparse
import asyncio
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf
import websockets

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from app.shared.audio_utils import ffmpeg_bin  # noqa: E402

FRAME = 1024          # bytes, 32 ms of 16 kHz PCM16
FRAME_S = 0.032


def decode(src: str) -> bytes:
    out = subprocess.run([ffmpeg_bin(), "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("outdir")
    ap.add_argument("--name", required=True)
    ap.add_argument("--langs", default="ta-IN,bn-IN,en-IN")
    ap.add_argument("--voice", default="stock")
    ap.add_argument("--listen", default="", help="languages a viewer is tuned to (default: all of --langs)")
    ap.add_argument("--loops", type=int, default=2)
    ap.add_argument("--yt", default="")
    ap.add_argument("--api", default="http://localhost:8010")
    ap.add_argument("--chat", default="அண்ணா stream சூப்பர், அடுத்து எந்த game விளையாடப் போறீங்க?")
    a = ap.parse_args()
    out = Path(a.outdir) / a.name
    out.mkdir(parents=True, exist_ok=True)
    langs = a.langs.split(",")
    heard = a.listen.split(",") if a.listen else langs
    ws_base = a.api.replace("http", "ws", 1)

    pcm = decode(a.src)
    clip_s = len(pcm) / 32000
    gap = b"\x00" * (FRAME * 47)                       # ~1.5 s of silence between loops
    feed = (pcm + gap) * a.loops + b"\x00" * (FRAME * 94)
    feed = feed[: len(feed) // FRAME * FRAME]

    body: dict = {"youtube_video_id": a.yt, "target_langs": langs}
    if a.voice == "stream":
        body |= {"voice_from_stream": True, "voice_consent": True}
    elif a.voice != "stock":
        body["voice_profile_id"] = a.voice
    async with httpx.AsyncClient(base_url=a.api, timeout=60) as http:
        r = await http.post("/api/live/sessions", json=body)
        r.raise_for_status()
        s = r.json()
        sid, token = s["session_id"], s["ingest_token"]
        print(f"session {sid}  voice={a.voice}  langs={langs}  clip {clip_s:.1f}s x{a.loops}")
        (out / "session.txt").write_text(sid, encoding="utf-8")

        events: list[dict] = []          # everything received, with client arrival time
        t0 = time.monotonic()
        stop = asyncio.Event()

        async def watch(lang: str) -> None:
            async with websockets.connect(f"{ws_base}/ws/watch/{sid}?lang={lang}", max_size=None) as ws:
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 0.5)
                    except TimeoutError:
                        continue
                    except websockets.ConnectionClosed:
                        return
                    m = json.loads(raw)
                    m["_ch"], m["_t"] = lang, round(time.monotonic() - t0, 3)
                    events.append(m)

        chat_seen: list[dict] = []

        async def chat() -> None:
            async with websockets.connect(f"{ws_base}/ws/chat/{sid}?lang=ta-IN&name=Viewer") as ws:
                await asyncio.sleep(min(8.0, clip_s / 2))
                t_send = time.monotonic()
                await ws.send(json.dumps({"text": a.chat, "lang": "ta-IN", "name": "Viewer"}))
                try:
                    m = json.loads(await asyncio.wait_for(ws.recv(), 20))
                    m["_roundtrip_s"] = round(time.monotonic() - t_send, 2)
                    chat_seen.append(m)
                except TimeoutError:
                    chat_seen.append({"error": "no chat reply in 20 s"})

        tasks = [asyncio.create_task(watch(lg)) for lg in [*heard, "all"]]
        await asyncio.sleep(0.5)
        tasks.append(asyncio.create_task(chat()))

        async with websockets.connect(f"{ws_base}/ws/ingest/{sid}?token={token}", max_size=None) as ws:
            t_feed0 = time.monotonic()
            feed_offset = round(t_feed0 - t0, 3)       # client clock at first frame
            for i in range(0, len(feed), FRAME):
                await ws.send(feed[i:i + FRAME])
                due = t_feed0 + (i // FRAME + 1) * FRAME_S
                delay = due - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
            fed_s = time.monotonic() - t_feed0
            print(f"fed {len(feed) / 32000:.1f}s of audio in {fed_s:.1f}s wall")
            # keep the socket open (silence) until every language has finished every chunk, or 90 s
            deadline = time.monotonic() + 90
            silence = b"\x00" * FRAME
            while time.monotonic() < deadline:
                seqs = {m["seq"] for m in events if m.get("type") == "caption" and m["_ch"] == "all" and m.get("lang") == "src"}
                done = {(m["lang"], m["seq"]) for m in events if m.get("type") == "audio" and m.get("last") and m["_ch"] != "all"}
                quiet_for = time.monotonic() - t0 - max((m["_t"] for m in events), default=0)
                if seqs and all((lg, q) in done for lg in heard for q in seqs) and quiet_for > 4:
                    break
                await ws.send(silence)
                await asyncio.sleep(FRAME_S)
        metrics = (await http.get(f"/api/live/sessions/{sid}/metrics")).json()
        await http.post(f"/api/live/sessions/{sid}/stop")
        await asyncio.sleep(1.0)
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        sess_after = (await http.get(f"/api/live/sessions/{sid}")).json()

    # ---- save dubbed audio: one WAV per language, and one per chunk
    sr_by_lang: dict[str, int] = {}
    audio: dict[tuple[str, int], bytearray] = {}
    for m in events:
        if m.get("type") == "audio" and m["_ch"] != "all" and m.get("pcm_b64"):
            sr_by_lang[m["lang"]] = m["sample_rate"]
            audio.setdefault((m["lang"], m["seq"]), bytearray()).extend(base64.b64decode(m["pcm_b64"]))
    for (lg, seq), b in sorted(audio.items()):
        x = np.frombuffer(bytes(b), dtype="<i2")
        sf.write(out / f"{lg}_chunk{seq:02d}.wav", x, sr_by_lang[lg], subtype="PCM_16")
    for lg in langs:
        parts = [np.frombuffer(bytes(b), dtype="<i2") for (l2, _), b in sorted(audio.items()) if l2 == lg]
        if parts:
            pause = np.zeros(int(0.3 * sr_by_lang[lg]), dtype="<i2")
            joined = np.concatenate([p for part in parts for p in (part, pause)])
            sf.write(out / f"dub_{lg}.wav", joined, sr_by_lang[lg], subtype="PCM_16")

    light = [{k: v for k, v in m.items() if k != "pcm_b64"} | ({"bytes": len(m["pcm_b64"]) * 3 // 4} if m.get("pcm_b64") else {})
             for m in events]
    (out / "events.json").write_text(json.dumps(light, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {"session_id": sid, "voice": a.voice, "langs": langs, "clip_s": round(clip_s, 2), "loops": a.loops,
               "feed_offset_s": feed_offset, "metrics": metrics, "chat": chat_seen, "session_after": sess_after,
               "errors": [m for m in light if m.get("type") == "error"],
               "voice_events": [m for m in light if m.get("type") == "voice" and m["_ch"] == "all"]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("metrics", "chat", "errors", "voice_events")}, ensure_ascii=False)[:1800])


asyncio.run(main())
