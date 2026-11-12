"""Streamer mic -> 16 kHz mono PCM16 -> Bharat Dub /ws/ingest/{session}.

    pip install -r requirements.txt
    python client.py --session <id> --token <ingest_token> [--server ws://localhost:8000] [--gate 0.01]
    python client.py --list-devices

Wear headphones so the dubbed audio does not leak back into the mic.
A simple noise gate (RMS threshold) sends silence instead of room noise.
"""
import argparse
import asyncio
import queue
import sys

import numpy as np
import sounddevice as sd
import websockets

SR = 16000
FRAME_SAMPLES = 512  # 1024 bytes of PCM16, 32 ms (what Prisma expects)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--token")
    ap.add_argument("--server", default="ws://localhost:8000")
    ap.add_argument("--gate", type=float, default=0.01, help="RMS noise gate (0 disables)")
    ap.add_argument("--device", default=None, help="input device index or name")
    ap.add_argument("--list-devices", action="store_true")
    a = ap.parse_args()
    if a.list_devices:
        print(sd.query_devices())
        return
    if not (a.session and a.token):
        sys.exit("--session and --token are required (shown on the /live console)")
    asyncio.run(stream(a))


async def stream(a: argparse.Namespace) -> None:
    q: queue.Queue[bytes] = queue.Queue(maxsize=200)
    hold = 0

    def callback(indata, frames, t, status):  # noqa: ANN001
        nonlocal hold
        x = indata[:, 0].astype(np.float32)
        rms = float(np.sqrt(np.mean(x ** 2)))
        if a.gate and rms < a.gate:
            hold = max(0, hold - 1)
            if hold == 0:
                x = np.zeros_like(x)
        else:
            hold = 15  # keep ~0.5 s open after speech so word endings are not clipped
        pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
        try:
            q.put_nowait(pcm)
        except queue.Full:
            pass

    url = f"{a.server.rstrip('/')}/ws/ingest/{a.session}?token={a.token}"
    device = int(a.device) if a.device and a.device.isdigit() else a.device
    while True:
        try:
            async with websockets.connect(url, max_size=None) as ws:
                print("connected, streaming mic (Ctrl+C to stop)")
                with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME_SAMPLES,
                                    device=device, callback=callback):
                    while True:
                        pcm = await asyncio.to_thread(q.get)
                        await ws.send(pcm)
        except (OSError, websockets.ConnectionClosed) as e:
            print(f"disconnected ({e}); retrying in 2 s")
            await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
