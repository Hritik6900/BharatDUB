"""Runs ON the GPU machine. Do separate engine processes really work in parallel, where replicas in one process do not?
  python bench_mp.py 9001 9002 9003
"""
import asyncio
import statistics
import sys
import time

import httpx

PORTS = sys.argv[1:]
REF = str(__import__("pathlib").Path.home() / "voice_engine" / "sample_ref.wav")
REF_TEXT = "ਭਹੰਪੀ ਵਿੱਚ ਸਮਾਰਕਾਂ ਦੇ ਭਵਨ ਨਿਰਮਾਣ ਕਲਾ ਦੇ ਵੇਰਵੇ ਗੁੰਝਲਦਾਰ ਅਤੇ ਹੈਰਾਨ ਕਰਨ ਵਾਲੇ ਹਨ, ਜੋ ਮੈਨੂੰ ਖੁਸ਼ ਕਰਦੇ  ਹਨ।"
TEXTS = ["இதை மெஷின்ல ஒன்றரை மணி நேரம் வேக வைப்போம்", "এই লোকটা ক্যাম্প করছে আর আমরা এখন বাঁ দিকে যাচ্ছি",
         "ఇప్పుడు ఎడమ వైపు వెళ్తున్నా, ఈ వ్యక్తి క్యాంప్ చేస్తున్నాడు"]


async def one(c, port, text):
    t0 = time.perf_counter()
    r = await c.post(f"http://127.0.0.1:{port}/tts", json={"session_id": "mp", "text": text, "lang": ""})
    r.raise_for_status()
    return time.perf_counter() - t0, float(r.headers["x-synth-ms"]), float(r.headers["x-audio-ms"])


async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        for p in PORTS:
            for _ in range(90):
                try:
                    await c.get(f"http://127.0.0.1:{p}/health")
                    break
                except Exception:
                    await asyncio.sleep(2)
            with open(REF, "rb") as f:
                (await c.post(f"http://127.0.0.1:{p}/ref", data={"session_id": "mp", "ref_text": REF_TEXT},
                              files={"audio": ("ref.wav", f, "audio/wav")})).raise_for_status()
            await one(c, p, TEXTS[0])
        single = [(await one(c, PORTS[0], t))[0] for _ in range(3) for t in TEXTS]
        print(f"one line, one process:          p50 {statistics.median(single):.2f} s")
        same = []
        for _ in range(5):
            t0 = time.perf_counter()
            await asyncio.gather(*[one(c, PORTS[0], t) for t in TEXTS])
            same.append(time.perf_counter() - t0)
        print(f"3 lines at once, one process:   p50 {statistics.median(same):.2f} s")
        if len(PORTS) >= 3:
            spread = []
            for _ in range(5):
                t0 = time.perf_counter()
                res = await asyncio.gather(*[one(c, p, t) for p, t in zip(PORTS, TEXTS)])
                spread.append(time.perf_counter() - t0)
            print(f"3 lines at once, 3 processes:   p50 {statistics.median(spread):.2f} s  (engine ms {[round(r[1]) for r in res]}, audio ms {[round(r[2]) for r in res]})")


asyncio.run(main())
