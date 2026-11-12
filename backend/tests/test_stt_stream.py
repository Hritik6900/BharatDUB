"""StreamingSTT against a local fake Prisma WebSocket server."""
import json

import websockets
from pydantic import SecretStr

from app.config import Settings
from app.providers.stt_gnani import FRAME_BYTES, GnaniSTT


async def test_stream_frames_headers_commit_and_events():
    got: dict = {"frames": [], "texts": []}

    async def fake_prisma(ws):
        got["headers"] = dict(ws.request.headers)
        await ws.send(json.dumps({"type": "connected", "message": "ok"}))
        async for msg in ws:
            if isinstance(msg, bytes):
                got["frames"].append(len(msg))
                if len(got["frames"]) == 3:
                    await ws.send(json.dumps({"type": "processing"}))
                    await ws.send(json.dumps({"type": "transcript", "text": "namaste", "is_final": True}))
            else:
                got["texts"].append(json.loads(msg))
                await ws.send(json.dumps({"type": "transcript", "text": "last", "is_final": True}))
                await ws.close()

    async with websockets.serve(fake_prisma, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        s = Settings(_env_file=None, gnani_api_key=SecretStr("k"), gnani_base=f"http://127.0.0.1:{port}")

        async def audio():
            yield b"\x01" * 1500   # odd sizes must be re-framed to 1024
            yield b"\x02" * 1500

        events = [ev async for ev in GnaniSTT(s).stream(audio(), "hi-IN")]

    assert got["headers"]["x-api-key-id"] == "k"
    assert got["headers"]["model"] == "prisma-v3.0" and got["headers"]["language_code"] == "hi-IN"
    assert set(got["frames"]) == {FRAME_BYTES}
    assert got["texts"] == [{"type": "commit"}]
    kinds = [e.kind for e in events]
    assert kinds[0] == "connected" and "processing" in kinds
    assert [e.text for e in events if e.kind == "final"] == ["namaste", "last"]
