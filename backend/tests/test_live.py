import asyncio
import base64
import json

from fastapi.testclient import TestClient

from app.db import LocalStore
from app.live.assembler import Assembler
from app.live.bus import ALL
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession, parse_youtube_id
from app.main import app
from app.providers.base import TranscriptEvent
from app.providers.mock import LINES, PHRASEBOOK, MockLLM, MockTTS


def test_assembler_sentence_end_closes_chunk():
    a = Assembler()
    c = a.add("namaste doston.", t_start_ms=0, t_end_ms=900, t_final_ms=1500)
    assert c and c.seq == 1 and c.text == "namaste doston." and c.t_speech_end_ms == 900


def test_assembler_silence_and_max_length():
    a = Assembler()
    assert a.add("bhai ye", t_start_ms=0, t_end_ms=1000, t_final_ms=1500) is None
    assert a.poll(1800) is None                 # only 0.8 s since speech ended
    c = a.poll(2300)                            # 1.3 s: close
    assert c and c.text == "bhai ye"
    assert a.add("ek", t_start_ms=3000, t_end_ms=6500, t_final_ms=7000) is None
    c = a.add("do", t_start_ms=7000, t_end_ms=9600, t_final_ms=10000)  # 6.1 s of speech
    assert c and c.text == "ek do" and c.seq == 2 and c.t_speech_ms == 3000


def test_assembler_waits_while_speaking():
    a = Assembler()
    a.add("pehla", t_start_ms=0, t_end_ms=1000, t_final_ms=1500)
    a.speech_started()
    assert a.poll(5000) is None
    assert a.add("doosra", t_start_ms=1600, t_end_ms=2500, t_final_ms=3000) is None
    assert a.poll(3800) and not a.pending


def test_parse_youtube_id():
    assert parse_youtube_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert parse_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3") == "dQw4w9WgXcQ"
    assert parse_youtube_id("https://youtube.com/live/dQw4w9WgXcQ?si=x") == "dQw4w9WgXcQ"
    assert parse_youtube_id("not a link") is None


class ScriptedSTT:
    """Yields speech_start / processing / final for each scripted line, paced by the audio it receives."""

    async def stream(self, frames, lang, **kw):
        lines = iter([LINES[0], LINES[1]])
        n = 0
        async for _ in frames:
            n += 1
            if n % 3 == 1:
                yield TranscriptEvent(kind="speech_start")
            if n % 3 == 0:
                yield TranscriptEvent(kind="processing")
                text = next(lines, None)
                if text:
                    yield TranscriptEvent(kind="final", text=text, audio_duration_ms=1200)


async def test_pipeline_captions_audio_order_and_metrics(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    sess = LiveSession({"id": "s1", "target_langs": ["ta-IN", "bn-IN"], "src_lang": "indic-auto"})
    p = LivePipeline(sess, stt=ScriptedSTT(), llm=MockLLM(), tts=MockTTS())
    ta = sess.bus.subscribe("ta-IN")
    console = sess.bus.subscribe(ALL)
    await p.start()
    for _ in range(6):
        p.feed(b"\x00" * 1024)
        await asyncio.sleep(0.01)
    msgs: list[dict] = []
    while sum(1 for m in msgs if m["type"] == "audio" and m["last"]) < 2:
        msgs.append(await asyncio.wait_for(ta.get(), 10))
    await p.stop()

    captions = [m for m in msgs if m["type"] == "caption"]
    assert [c["text"] for c in captions] == PHRASEBOOK["ta-IN"][:2]
    seqs = [m["seq"] for m in msgs if m["type"] in ("caption", "audio")]
    assert seqs == sorted(seqs)  # in order per language
    first_audio = next(i for i, m in enumerate(msgs) if m["type"] == "audio")
    first_caption = next(i for i, m in enumerate(msgs) if m["type"] == "caption")
    assert first_caption < first_audio  # caption before audio
    pcm = base64.b64decode(next(m for m in msgs if m["type"] == "audio" and m["pcm_b64"])["pcm_b64"])
    assert len(pcm) % 2 == 0
    stats = p.stats()
    assert stats["n"] == 4 and stats["p50_ms"] is not None
    rows = await store.select("live_chunks", session_id="s1")
    assert len(rows) == 2 and "t_first_audio:bn-IN" in rows[0]["timings"]
    seen = []
    while not console.empty():
        seen.append(console.get_nowait()["type"])
    assert "transcript" in seen and "stats" in seen


def test_live_rest_and_ws_flow():
    c = TestClient(app)
    assert c.post("/api/live/sessions", json={"target_langs": ["hi-IN"]}).status_code == 400
    assert c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "youtube_video_id": "x"}).status_code == 400
    r = c.post("/api/live/sessions", json={"target_langs": ["ta-IN", "en-IN"],
                                           "youtube_video_id": "https://youtu.be/dQw4w9WgXcQ"})
    assert r.status_code == 201
    body = r.json()
    sid, token = body["session_id"], body["ingest_token"]
    assert body["youtube_video_id"] == "dQw4w9WgXcQ"
    info = c.get(f"/api/live/sessions/{sid}").json()
    assert "ingest_token" not in info
    assert c.patch(f"/api/live/sessions/{sid}", json={"offset_ms": 99999}).json()["offset_ms"] == 10000

    with c.websocket_connect(f"/ws/watch/{sid}?lang=ta-IN") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello" and hello["session"]["target_langs"] == ["ta-IN", "en-IN"]

    try:
        with c.websocket_connect(f"/ws/ingest/{sid}?token=wrong") as ws:
            ws.receive_text()
        raise AssertionError("ingest with a bad token must be refused")
    except Exception as e:  # noqa: BLE001
        assert "4403" in str(e) or "Disconnect" in type(e).__name__

    with c.websocket_connect(f"/ws/chat/{sid}?lang=hi-IN") as ws:
        ws.send_text(json.dumps({"text": "  bahut   badhiya  ", "name": "Ravi"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "chat" and msg["text"] == "bahut badhiya" and msg["translated"] == "bahut badhiya"

    m = c.get(f"/api/live/sessions/{sid}/metrics").json()
    assert m["chunks"] == 0 and m["p50_ms"] is None
    assert c.post(f"/api/live/sessions/{sid}/stop").json()["status"] == "ended"
    _ = token


def test_dashboard_nulls_when_unmeasured():
    d = TestClient(app).get("/api/dashboard").json()
    assert d["live"]["p50_ms"] is None and d["languages_supported"] == 10
