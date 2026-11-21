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
    for kind in ("caption", "audio"):
        seqs = [m["seq"] for m in msgs if m["type"] == kind]
        assert seqs == sorted(seqs)  # captions in order, audio in order (a later caption may pass earlier audio)
    for seq in (1, 2):
        cap = next(i for i, m in enumerate(msgs) if m["type"] == "caption" and m["seq"] == seq)
        aud = next(i for i, m in enumerate(msgs) if m["type"] == "audio" and m["seq"] == seq)
        assert cap < aud  # a chunk's caption comes before its audio
    pcm = base64.b64decode(next(m for m in msgs if m["type"] == "audio" and m["pcm_b64"])["pcm_b64"])
    assert len(pcm) % 2 == 0
    stats = p.stats()
    assert stats["n"] == 2 and stats["p50_ms"] is not None
    rows = await store.select("live_chunks", session_id="s1")
    # Tamil has a viewer; nobody is tuned to Bengali, so its audio is not made (the caption still goes out).
    t0 = rows[0]["timings"]
    assert len(rows) == 2 and "t_first_audio:ta-IN" in t0 and t0["skipped:bn-IN"] == "unheard"
    assert "t_translated:bn-IN" in t0 and "t_first_audio:bn-IN" not in t0
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
    assert c.patch(f"/api/live/sessions/{sid}", json={"offset_ms": 99999}).json()["offset_ms"] == 40000  # YouTube delay

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


class TalkingSTT:
    """Says speech has started on the first frame and never finishes the utterance."""

    async def stream(self, frames, lang, **kw):
        first = True
        async for _ in frames:
            if first:
                first = False
                yield TranscriptEvent(kind="speech_start")


async def test_voice_from_stream_clones_only_with_consent(tmp_path, monkeypatch):
    import numpy as np

    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    monkeypatch.setattr("app.live.pipeline.ENROL_SPEECH_S", 0.5)
    loud = (np.sin(np.arange(512) / 5) * 8000).astype("<i2").tobytes()
    quiet = b"\x00" * 1024

    async def run(row_extra: dict, frame: bytes) -> tuple[LivePipeline, list[dict]]:
        row = await store.insert("live_sessions", {"target_langs": ["ta-IN"], "src_lang": "indic-auto", **row_extra})
        sess = LiveSession(row)
        tts = MockTTS()
        calls: list[str | None] = []

        async def clone(wav_path, *, consent_at):
            calls.append(consent_at)
            return {"embedding": "e", "shape": [1, 768], "dtype": "torch.bfloat16"}

        tts.clone_embedding = clone  # type: ignore[method-assign]
        p = LivePipeline(sess, stt=TalkingSTT(), llm=MockLLM(), tts=tts)
        await p.start()
        for _ in range(40):
            p.feed(frame)
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.1)
        await p.stop()
        return p, calls  # type: ignore[return-value]

    consent = {"voice_from_stream": {"consent_at": "2026-11-13T00:00:00+00:00", "consent_text": "ok"}}
    p, calls = await run(consent, loud)
    assert calls == ["2026-11-13T00:00:00+00:00"] and p.voice and p.voice["kind"] == "clone"
    profiles = await store.select("voice_profiles")
    assert len(profiles) == 1 and profiles[0]["consent_at"] and p.sess.row["voice_profile_id"] == profiles[0]["id"]

    p, calls = await run({}, loud)            # no consent: never collected, never cloned
    assert calls == [] and p.voice is None
    p, calls = await run(consent, quiet)      # consent but only silence: nothing to copy
    assert calls == [] and p.voice is None
    assert len(await store.select("voice_profiles")) == 1


def test_voice_from_stream_needs_consent_flag():
    c = TestClient(app)
    r = c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "voice_from_stream": True})
    assert r.status_code == 403
    from app.config import get_settings
    was = get_settings().live_clone_needs_streamer
    get_settings().__dict__["live_clone_needs_streamer"] = True       # the strict setting: only a streamer profile clones
    r = c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "voice_from_stream": True, "voice_consent": True})
    assert r.status_code == 403 and "streamer" in r.json()["detail"]
    assert c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "voice_profile_id": "x"}).status_code == 403
    r = c.post("/api/live/sessions", json={"target_langs": ["ta-IN"]})   # stock voices: always allowed
    assert r.status_code == 201 and r.json()["voice_from_stream"] is False and r.json()["voice_profile_id"] is None
    get_settings().__dict__["live_clone_needs_streamer"] = False      # the open setting: the tick box is enough
    try:
        r = c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "voice_from_stream": True, "voice_consent": True})
        assert r.status_code == 201 and r.json()["voice_from_stream"] is True and "consent" not in json.dumps(r.json())
        # ... and still nothing without the consent tick
        assert c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "voice_from_stream": True}).status_code == 403
    finally:
        get_settings().__dict__["live_clone_needs_streamer"] = was


class SilentSTT:
    """Keeps the stream open without events, so the test can dispatch chunks itself."""

    async def stream(self, frames, lang, *, sample_rate=16000, pace=False, extra_headers=None):
        async for _ in frames:
            pass
        return
        yield  # pragma: no cover


async def test_phrases_waiting_behind_the_voice_are_spoken_in_one_call(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    sess = LiveSession({"id": "m1", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    tts = MockTTS()
    calls: list[str] = []
    plain = tts.synth_stream

    def counting(text, lang, voice, **kw):
        calls.append(text)
        return plain(text, lang, voice, **kw)

    monkeypatch.setattr(tts, "synth_stream", counting)
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=tts)
    ta = sess.bus.subscribe("ta-IN")
    await p.start()
    for i in range(4):  # four phrases arrive faster than one can be spoken
        now = sess.now_ms()
        p._dispatch(p.assembler.make(f"line {i}", t_start_ms=now, t_end_ms=now, t_final_ms=now))
        await asyncio.sleep(0.02)
    ended: set[int] = set()
    with_audio: set[int] = set()
    while len(ended) < 4:
        m = await asyncio.wait_for(ta.get(), 10)
        if m["type"] == "audio":
            if m["last"]:
                ended.add(m["seq"])
            elif m["pcm_b64"]:
                with_audio.add(m["seq"])
    await p.stop()
    assert ended == {1, 2, 3, 4}            # every phrase is closed for the viewer
    assert len([c for c in calls if c != "ok"]) < 4   # ... with fewer voice calls than phrases ("ok" = warm-up)
    rows = {r["seq"]: r["timings"] for r in await store.select("live_chunks", session_id="m1")}
    merged = [seq for seq, t in rows.items() if "merged:ta-IN" in t]
    assert merged and all(rows[s]["merged:ta-IN"] in with_audio for s in merged)
    assert all("t_first_audio:ta-IN" in t and "t_heard:ta-IN" in t for t in rows.values())


async def test_sync_mode_tags_phrases_with_video_time_and_measures_lateness(tmp_path, monkeypatch):
    """Once the console reports the video's time, captions and audio carry the video moment they belong to,
    the delay is published for viewers, and how late each phrase started is recorded."""
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    sess = LiveSession({"id": "y1", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS())
    ta = sess.bus.subscribe("ta-IN")
    await p.start()
    assert p.sync_delay() == 0 and "media_s" not in p._media_tag(0)   # nothing reported: the old behaviour
    p.set_media(100.0, True)
    assert p.sync_delay() == p.s.live_sync_delay_ms
    assert abs(p._media_at(sess.now_ms() + 2000) - 102.0) < 0.2         # carried forward while the video plays
    now = sess.now_ms()
    p._dispatch(p.assembler.make("line one", t_start_ms=now, t_end_ms=now + 10, t_final_ms=now + 10))
    msgs: list[dict] = []
    while not any(m["type"] == "audio" and m["last"] for m in msgs):
        msgs.append(await asyncio.wait_for(ta.get(), 10))
    await p.stop()
    sync = next(m for m in msgs if m["type"] == "sync")
    assert sync["delay_ms"] == p.s.live_sync_delay_ms and sync["media_s"] == 100.0
    cap = next(m for m in msgs if m["type"] == "caption")
    aud = next(m for m in msgs if m["type"] == "audio" and m["pcm_b64"])
    assert abs(cap["media_s"] - 100.0) < 0.5 and aud["media_s"] == cap["media_s"]
    t = (await store.select("live_chunks", session_id="y1"))[0]["timings"]
    assert t["late:ta-IN"] == 0                                         # ready long before its moment
    assert t["t_heard:ta-IN"] == now + p.s.live_sync_delay_ms           # heard exactly then
    assert p.stats()["sync_on_time_pct"] == 100.0


async def test_sync_delay_grows_only_when_audio_keeps_coming_late(tmp_path, monkeypatch):
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: LocalStore(tmp_path / "db.json"))
    sess = LiveSession({"id": "y2", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS())
    p.running = True
    p.set_media(5.0, True)
    base = p.sync_delay()
    for late in (0, 900, 100):
        p._note_late(late)
    assert p.sync_delay() == base                    # one late phrase is not a pattern
    for late in (1200, 1300):
        p._note_late(late)
    assert p.sync_delay() == base + p.s.live_sync_grow_step_ms   # three of the last six: a step, not all at once
    grown = p.sync_delay()
    for lang_late in (2900, 2800, 2700):             # one long line, late in three languages, is one late phrase
        p._note_late(lang_late, seq=7)
    assert p.sync_delay() == grown
    for _ in range(40):
        for late in (2900, 2900, 2900):
            p._note_late(late)
    assert p.sync_delay() == p.s.live_sync_delay_max_ms   # never beyond the limit
    p._media.clear()
    assert p.sync_delay() == 0                       # the console stopped reporting: back to the old behaviour


class FakeGpu:
    """Stands in for the GPU voice engine: records what it is given."""
    enabled = True

    def __init__(self):
        self.refs: list[tuple[str, str, str | None]] = []
        self.lines: list[tuple[str, str]] = []

    def speaks(self, lang):
        return lang != "en-IN"

    async def set_ref(self, session_id, wav_path, ref_text, *, consent_at, steps=None):
        assert consent_at, "the pipeline must never ask for a copy without consent"
        self.refs.append((session_id, ref_text, consent_at))
        return {"ok": True}

    async def synth(self, session_id, text, lang, speed=None):
        self.lines.append((lang, text))
        return (b"\x10\x20" * 12000, 24000)


async def test_gpu_voice_needs_consent_and_speaks_indian_languages_only(tmp_path, monkeypatch):
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: LocalStore(tmp_path / "db.json"))
    line = "yeh ek poori line hai jo paanch second chali"
    # Without the consent given for this stream the engine is never handed a voice sample.
    plain = LiveSession({"id": "g0", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    gpu0 = FakeGpu()
    p0 = LivePipeline(plain, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS(), gpu=gpu0)
    p0.running = True
    p0.feed(b"\x00\x10" * 512)
    p0._t_start, p0._t_end = 0, 5000
    p0._maybe_gpu_ref(line, 5600)
    assert not p0._ring and not gpu0.refs and not p0._gpu_speaks("ta-IN")

    sess = LiveSession({"id": "g1", "target_langs": ["ta-IN", "en-IN"], "src_lang": "hi-IN",
                        "voice_from_stream": {"consent_at": "2026-11-14T10:00:00+00:00", "consent_text": "ok"}})
    gpu = FakeGpu()
    tts = MockTTS()
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=tts, gpu=gpu)
    ta, en = sess.bus.subscribe("ta-IN"), sess.bus.subscribe("en-IN")
    await p.start()
    for t in range(0, 5200, 32):                       # 5 s of the stream's sound, stamped as it arrived
        p._ring.append((t, b"\x00\x10" * 512))
    p._t_start, p._t_end = 100, 5000
    p._maybe_gpu_ref(line, 5600)
    for _ in range(50):
        if p.gpu_ready:
            break
        await asyncio.sleep(0.02)
    assert p.gpu_ready and gpu.refs == [("g1-v1", line, "2026-11-14T10:00:00+00:00")]
    now = sess.now_ms()
    p._dispatch(p.assembler.make("line one", t_start_ms=now, t_end_ms=now, t_final_ms=now))
    for q in (ta, en):
        while True:
            m = await asyncio.wait_for(q.get(), 10)
            if m["type"] == "audio" and m["last"]:
                break
    await p.stop()
    assert {lang for lang, _ in gpu.lines} == {"ta-IN"}   # Tamil from the engine; English stays on the Gnani voice


def test_speech_cut_joins_short_lines_and_needs_enough_speech():
    from app.live.pipeline import speech_cut
    loud, quiet = b"\x00\x10" * 512, b"\x00\x00" * 512      # 32 ms frames
    line = [loud] * 30 + [quiet] * 40                        # ~1 s of speech, then a 1.3 s pause
    assert speech_cut(line * 2) is None                      # 2 s of speech: not enough to copy a voice
    cut = speech_cut(line * 5)                               # five short lines: 4.8 s of speech
    assert cut is not None
    frames = len(cut) // 1024
    assert 150 + 5 * 12 <= frames <= 150 + 5 * 28            # all the speech; each 1.3 s pause cut to under 0.9 s
    long = speech_cut([loud] * 600)                          # 19 s without a pause: only the last 7 s
    assert long is not None and 215 <= len(long) // 1024 <= 222
    dip = [loud] * 60 + [quiet] * 8 + [loud] * 60            # a 0.25 s dip inside a sentence stays whole
    assert len(speech_cut(dip)) // 1024 == 128


async def test_gpu_voice_comes_back_after_the_engine_was_away(tmp_path, monkeypatch):
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: LocalStore(tmp_path / "db.json"))
    sess = LiveSession({"id": "g2", "target_langs": ["ta-IN"], "src_lang": "hi-IN",
                        "voice_from_stream": {"consent_at": "2026-11-14T10:00:00+00:00", "consent_text": "ok"}})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS(), gpu=FakeGpu())
    p.gpu_ready = True
    assert p._gpu_speaks("ta-IN")
    p._gpu_fail, p._gpu_retry_at = 3, sess.now_ms() + 60_000      # three failures: the Gnani voice carries on
    assert not p._gpu_speaks("ta-IN")
    p._gpu_retry_at = sess.now_ms() - 1                           # later the engine gets another try
    assert p._gpu_speaks("ta-IN")


class BudgetLLM(MockLLM):
    def __init__(self):
        super().__init__()
        self.seen: list[dict] = []

    async def translate_chunk(self, text, target, glossary, context, brief=False, native=False, max_words=None):
        self.seen.append({"words": len(text.split()), "brief": brief, "max_words": max_words})
        return await super().translate_chunk(text, target, glossary, context)


async def test_translator_gets_a_word_limit_from_the_measured_pace(tmp_path, monkeypatch):
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: LocalStore(tmp_path / "db.json"))
    sess = LiveSession({"id": "b1", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    llm = BudgetLLM()
    p = LivePipeline(sess, stt=SilentSTT(), llm=llm, tts=MockTTS())
    sess.bus.subscribe("ta-IN")
    await p.start()
    line = "ek do teen chaar paanch chheh saat aath"     # 8 words: about 2.8 s at the default pace
    now = sess.now_ms()
    chunk = p.assembler.make(line, t_start_ms=now, t_end_ms=now, t_final_ms=now)
    await p._translate("ta-IN", chunk, [], None)
    assert llm.seen[-1]["max_words"] is None              # no pace measured yet: no limit
    p._dub_ms_per_word["ta-IN"] = 700.0                   # this voice needs 0.7 s a word
    await p._translate("ta-IN", chunk, [], None)
    assert llm.seen[-1] == {"words": 8, "brief": False, "max_words": 4}   # 2.8 s * 1.15 / 0.7 s
    p._playhead["ta-IN"] = sess.now_ms() + 3000           # the dub is 3 s behind: a much shorter line
    await p._translate("ta-IN", chunk, [], None)
    assert llm.seen[-1]["brief"] and llm.seen[-1]["max_words"] == 2
    await p.stop()


def test_words_heard_scores_a_copied_voice():
    from app.live.pipeline import words_heard
    said = "இன்று வானிலை மிகவும் நன்றாக இருக்கிறது"
    assert words_heard(said, "இன்று வானிலை மிகவும் நன்றாக இருக்கிறது.") == 1.0
    assert words_heard(said, "இன்று வானிலை நன்றாக") == 0.6
    assert words_heard(said, "மேய்ச்சல் இயந்திரம்") == 0.0


class ScoringSTT(SilentSTT):
    """Hears the first voice badly and the second one well."""

    def __init__(self):
        self.n = 0

    async def transcribe(self, wav_path, lang="indic-auto", **kw):
        from app.live.pipeline import GPU_CHECK_LINES
        from app.providers.base import STTResult
        if "bd_gpu_check" not in wav_path:
            return STTResult(text="yeh ek poori line hai jo abhi boli gayi", latency_s=0.0)
        self.n += 1
        line = GPU_CHECK_LINES["ta-IN"]
        return STTResult(text=line.split()[0] if self.n == 1 else line, latency_s=0.0)


async def test_a_better_voice_sample_replaces_a_poor_one(tmp_path, monkeypatch):
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: LocalStore(tmp_path / "db.json"))
    sess = LiveSession({"id": "g3", "target_langs": ["ta-IN"], "src_lang": "hi-IN",
                        "voice_from_stream": {"consent_at": "2026-11-14T10:00:00+00:00", "consent_text": "ok"}})
    p = LivePipeline(sess, stt=ScoringSTT(), llm=MockLLM(), tts=MockTTS(), gpu=FakeGpu())

    async def four_seconds(session_id, text, lang, speed=None):   # a natural pace for the check sentence
        return (b" " * 96000, 24000)

    p.gpu.synth = four_seconds
    p.running = True
    pcm = b"\x00\x10" * 16000 * 5
    p._gpu_tries = 1
    await p._gpu_enrol(pcm, "x")
    assert p.gpu_ready and p._gpu_sid == "g3-v1" and p._gpu_score is not None and p._gpu_score < 0.3
    assert not p._gpu_wanted()                       # not again straight away
    p._gpu_last_try = sess.now_ms() - 60_000
    assert p._gpu_wanted()                           # ... but a later pause may give a better sample
    p._gpu_tries = 2
    await p._gpu_enrol(pcm, "x")
    assert p._gpu_sid == "g3-v2" and p._gpu_score == 1.0
    p._gpu_last_try = sess.now_ms() - 60_000
    assert not p._gpu_wanted()                       # good enough: it stays


async def test_streamer_session_speaks_in_the_stored_voice_from_the_first_phrase(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    monkeypatch.setattr("app.shared.voices.voices_dir", lambda: tmp_path)
    (tmp_path / "p1_ref.wav").write_bytes(b"RIFF")
    await store.insert("voice_profiles", {"id": "p1", "consent_at": "2026-11-15T08:00:00+00:00", "embedding": None,
                                          "ref_path": "p1_ref.wav", "ref_text": "meri awaaz ka namoona", "ref_score": 0.9})
    gpu = FakeGpu()
    sess = LiveSession({"id": "st1", "target_langs": ["ta-IN"], "src_lang": "hi-IN", "streamer_id": "s1",
                        "voice_mode": "clone", "voice_profile_id": "p1"})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS(), gpu=gpu)
    ta = sess.bus.subscribe("ta-IN")
    await p.start()
    assert p.gpu_ready and p._gpu_sid == "voice-p1" and p._gpu_score == 0.9
    assert gpu.refs == [("voice-p1", "meri awaaz ka namoona", "2026-11-15T08:00:00+00:00")]
    assert not p._gpu_wanted()                              # the recorded voice is not replaced from the stream
    now = sess.now_ms()
    p._dispatch(p.assembler.make("pehli line", t_start_ms=now, t_end_ms=now, t_final_ms=now))
    while True:
        m = await asyncio.wait_for(ta.get(), 10)
        if m["type"] == "audio" and m["last"]:
            break
    await p.stop()
    assert [lang for lang, _ in gpu.lines] == ["ta-IN"]     # the very first phrase came from the engine

    # voice_mode stock: the same streamer, never a copied voice
    gpu2 = FakeGpu()
    sess2 = LiveSession({"id": "st2", "target_langs": ["ta-IN"], "src_lang": "hi-IN", "streamer_id": "s1",
                         "voice_mode": "stock", "voice_profile_id": None})
    p2 = LivePipeline(sess2, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS(), gpu=gpu2)
    await p2.start()
    assert not p2.gpu_ready and not gpu2.refs and not p2._gpu_planned("ta-IN")
    await p2.stop()


async def test_streamer_mic_session_times_the_dub_to_the_youtube_delay(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    sess = LiveSession({"id": "o1", "target_langs": ["ta-IN"], "src_lang": "hi-IN", "streamer_id": "s1",
                        "voice_mode": "stock", "offset_ms": 8000})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS())
    ta = sess.bus.subscribe("ta-IN")
    await p.start()
    assert p.offset_delay() == 8000 and p.sync_delay() == 8000
    now = sess.now_ms()
    p._dispatch(p.assembler.make("pehli line", t_start_ms=now, t_end_ms=now + 10, t_final_ms=now + 10))
    msgs: list[dict] = []
    while not any(m["type"] == "audio" and m["last"] for m in msgs):
        msgs.append(await asyncio.wait_for(ta.get(), 10))
    aud = next(m for m in msgs if m["type"] == "audio" and m["pcm_b64"])
    assert aud["t_speech_ms"] == now and "media_s" not in aud      # timed by the session clock, not a video's
    for late in (0, 300, 2500):
        p.viewer_played("ta-IN", late)
    for _ in range(40):                                              # the pipeline stays in step for a whole stream
        p._note_late(3000)
    assert p.sync_delay() == 8000                                    # YouTube's delay is not ours to stretch
    st = p.stats()
    assert st["sync_delay_ms"] == 8000 and st["viewer_n"] == 3 and st["viewer_on_time_pct"] == 66.7
    await p.stop()
    rows = await store.select("live_chunks", session_id="o1")
    assert rows[0]["timings"]["t_heard:ta-IN"] == now + 8000 and rows[0]["timings"]["late:ta-IN"] == 0
    # a session without a streamer keeps the old behaviour: its offset is only the viewer's slider default
    plain = LiveSession({"id": "o2", "target_langs": ["ta-IN"], "src_lang": "hi-IN", "offset_ms": 8000})
    assert LivePipeline(plain, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS()).sync_delay() == 0


async def test_a_phrase_is_never_stamped_before_the_end_of_the_one_before_it(tmp_path, monkeypatch):
    """The moment a phrase was spoken at is an estimate. A tail counted back too far used to land inside the
    phrase before it, so its dub was due while the earlier dub was still playing."""
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    sess = LiveSession({"id": "st1", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS())
    await p.start()
    first = p.assembler.make("first phrase", t_start_ms=1000, t_end_ms=3000, t_final_ms=3100)
    tail = p.assembler.make("its tail", t_start_ms=2200, t_end_ms=4000, t_final_ms=4100)   # counted back too far
    odd = p.assembler.make("odd one", t_start_ms=5000, t_end_ms=4500, t_final_ms=5100)     # ends before it starts
    for c in (first, tail, odd):
        p._dispatch(c)
    await p.stop()
    assert (first.t_speech_ms, tail.t_speech_ms) == (1000, 3000)
    assert p._starts[tail.seq] == 3000                      # what the dub's moment and the next phrase's room use
    assert odd.t_speech_end_ms >= odd.t_speech_ms == 5000

    was = p.s.live_stamp_fix
    p.s.__dict__["live_stamp_fix"] = False                  # the switch restores the stamps as they came
    try:
        sess2 = LiveSession({"id": "st2", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
        p2 = LivePipeline(sess2, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS())
        await p2.start()
        a = p2.assembler.make("first phrase", t_start_ms=1000, t_end_ms=3000, t_final_ms=3100)
        b = p2.assembler.make("its tail", t_start_ms=2200, t_end_ms=4000, t_final_ms=4100)
        p2._dispatch(a)
        p2._dispatch(b)
        await p2.stop()
        assert b.t_speech_ms == 2200
    finally:
        p.s.__dict__["live_stamp_fix"] = was


def test_the_tail_of_a_line_starts_when_its_first_word_was_heard():
    from app.live.assembler import PARTIAL_LAG_MS, Phraser

    ph = Phraser(min_words=2, max_words=3)
    assert ph.partial("u", "a b c", "a b c", 1000) == ("a b c", 1000 - PARTIAL_LAG_MS, 1000 - PARTIAL_LAG_MS)
    assert ph.tail_start("u") is None                       # no partial has shown a word after the phrase yet
    assert ph.partial("u", "a b c", "a b c d e", 1800) is None
    assert ph.tail_start("u") == 1800 - PARTIAL_LAG_MS      # "d" first showed up at 1800
    assert ph.final("u", "a b c d e.") == "d e."
    assert ph.tail_start("u") is None                       # the utterance is forgotten after its final


def test_phrases_share_their_line_at_an_even_pace_when_its_start_is_known():
    """A first partial brings several words at once. Stamping each word with the moment it showed up put a whole
    phrase in one instant; with the line's start known, the words heard so far are spread evenly instead."""
    from app.live.assembler import PARTIAL_LAG_MS, Phraser

    ph = Phraser(min_words=2, max_words=3)
    # six words heard by 2000 (spoken by 1400), the line began at 200: 200 ms a word
    assert ph.partial("u", "a b c", "a b c d e f", 2000, t0=200) == ("a b c", 200, 800)
    # the start given later is ignored: it is the next line's
    assert ph.partial("u", "a b c d e f", "a b c d e f g h", 2400, t0=999) == ("d e f", 800, 1400)
    assert ph.start_of("u") == 200
    ph.final("u", "a b c d e f g h.")
    assert ph.start_of("u") is None
    # a start that would mean an impossible pace is not believed: back to when the words showed up
    far = Phraser(min_words=2, max_words=3)
    assert far.partial("v", "a b c", "a b c", 100000, t0=0) == ("a b c", 100000 - PARTIAL_LAG_MS, 100000 - PARTIAL_LAG_MS)


async def test_a_line_keeps_its_own_start_when_the_next_line_has_already_begun(tmp_path, monkeypatch):
    """Prisma can report the next line's speech start before the previous line's final transcript. The finished
    line then began where its own audio began, and the newer start stays on record for the next line."""
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    sess = LiveSession({"id": "st3", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS())
    await p.start()
    p._t_start, p._t_end = 5000, 4000           # the next line began at 5000; this one ended at 4000
    p._on_stt(TranscriptEvent(kind="final", text="यह पूरी लाइन है।", utterance_id="a", audio_duration_ms=1500))
    await p.stop()
    seq = max(p._starts)
    assert p._starts[seq] == 4000 - 1500         # its end less its own length, not the next line's start
    assert p._t_start == 5000                    # still there for the line being spoken now


async def test_gpu_voice_asks_for_its_steps_per_voice():
    """A recorded voice and a voice learned from the stream each get their own number of denoising steps."""
    import httpx
    from app.config import Settings
    from app.providers.tts_gpu import GpuVoice
    seen: list[dict] = []

    def handle(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/ref":
            return httpx.Response(200, json={"ok": True})
        seen.append(json.loads(req.content))
        return httpx.Response(200, content=b"\x10\x20" * 2400, headers={"x-sample-rate": "24000", "x-format": "pcm"})

    s = Settings(gpu_voice_url="http://engine", gpu_voice_steps=16, gpu_voice_steps_stream=12, gpu_voice_format="pcm")
    gpu = GpuVoice(s, client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    await gpu.synth("voice-1", "a", "ta-IN")
    await gpu.set_ref("s1-v1", __file__, "text", consent_at="2026-11-21", steps=s.gpu_voice_steps_stream)
    await gpu.synth("s1-v1", "a", "ta-IN")
    await gpu.set_ref("s2-v1", __file__, "text", consent_at="2026-11-21", steps=0)
    await gpu.synth("s2-v1", "a", "ta-IN")
    assert [b.get("nfe") for b in seen] == [16, 12, None]


def test_a_slow_copied_voice_is_asked_to_speak_faster_up_to_a_limit():
    sess = LiveSession({"id": "pace", "target_langs": ["ta-IN", "pa-IN"], "src_lang": "hi-IN"})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS(), gpu=FakeGpu())
    assert p._pace_boost("ta-IN") == 1.0                 # nothing known yet
    p._note_gpu_pace("ta-IN", 6500, 10)                  # 650 ms a word
    p._note_gpu_pace("pa-IN", 3500, 10)                  # 350 ms a word: already fast enough
    p._note_gpu_pace("pa-IN", 2000, 3)                   # too short to say anything about pace
    assert abs(p._pace_boost("ta-IN") - 650 / p.s.gpu_voice_pace_ms) < 0.01
    assert p._pace_boost("pa-IN") == 1.0
    p._gpu_ms_per_word["ta-IN"] = 2000
    assert p._pace_boost("ta-IN") == p.s.gpu_voice_pace_max
    p.s = p.s.model_copy(update={"gpu_voice_pace_ms": 0})
    assert p._pace_boost("ta-IN") == 1.0                 # switched off


def test_phraser_cuts_latin_hinglish_at_clause_words_and_full_stops():
    """The GPU speech-to-text writes Hindi in Latin letters, with punctuation."""
    from app.live.assembler import Phraser
    ph = Phraser(min_words=6, max_words=12)
    got = ph.partial("u1", "kahin bhi tandoori khaoge ya fry khaoge usi oil ko baar baar badlate rahte hain aur pakaate", "", 1000)
    assert got and got[0] == "kahin bhi tandoori khaoge ya fry khaoge usi oil ko baar baar"   # no boundary: the 12-word limit
    got = ph.partial("u2", "Main ek grill chicken khud khaata hoon aur apne family mein", "", 2000)
    assert got and got[0] == "Main ek grill chicken khud khaata hoon"          # "hoon" ends a clause, "aur" opens one
    got = ph.partial("u3", "Is green chicken ki khaas baat. Yah bahut achha", "", 3000)
    assert got and got[0] == "Is green chicken ki khaas baat."                 # a full stop ends a clause


def test_phraser_waits_for_the_word_that_closes_the_sentence():
    from app.live.assembler import Phraser
    ph = Phraser(min_words=6, max_words=12)
    # "nahin" could end a clause, but the recogniser already hears "hai?" coming: no cut that leaves it alone.
    assert ph.partial("u1", "Anumaanjik jaankaari ke lie milta nahin", "Anumaanjik jaankaari ke lie milta nahin hai?", 1000) is None
    got = ph.partial("u1", "Anumaanjik jaankaari ke lie milta nahin hai?", "Anumaanjik jaankaari ke lie milta nahin hai? Aur", 1300)
    assert got and got[0] == "Anumaanjik jaankaari ke lie milta nahin hai?"
    # Nothing known beyond the settled words: cut as before.
    got = ph.partial("u2", "ise ham machine mein dedh ghante pakaate hain", "ise ham machine mein dedh ghante pakaate hain", 2000)
    assert got and got[0] == "ise ham machine mein dedh ghante pakaate hain"


async def test_gpu_stt_leaves_the_hosted_stream_once_the_engine_is_back(monkeypatch):
    from app.config import Settings
    from app.providers import stt_gpu
    from app.providers.base import TranscriptEvent as Ev

    class Hosted:
        async def stream(self, pcm_frames, lang, **kw):
            for i in range(50):
                yield Ev(kind="partial", text="a")
                yield Ev(kind="final", text=f"line {i}")

    monkeypatch.setattr(stt_gpu, "RETURN_CHECK_S", 0.0)
    stt = stt_gpu.GpuSTT(Settings(ai_mode="gpu", gpu_stt_url="http://127.0.0.1:1"), backup=Hosted())
    answers = iter([{"ok": False}, {"ok": False}, {"ok": True}])

    async def health():
        return next(answers, {"ok": True})
    stt.health = health

    async def frames():
        yield b"\x00" * 1024

    got = [ev.text async for ev in stt.stream(frames(), "hi-IN") if ev.kind == "final"]
    assert got == ["line 0", "line 1"]   # engine back after the third check: the stream ends at the next final


async def test_sessions_left_live_by_a_dead_server_are_closed_at_start(tmp_path, monkeypatch):
    from app import main
    store = LocalStore(tmp_path / "db.json")
    a = await store.insert("live_sessions", {"status": "live", "target_langs": ["ta-IN"]})
    b = await store.insert("live_sessions", {"status": "ended", "target_langs": ["ta-IN"]})
    monkeypatch.setattr(main, "get_store", lambda: store)
    assert await main.close_stale_sessions() == 1
    assert (await store.get("live_sessions", a["id"]))["status"] == "ended"
    assert (await store.get("live_sessions", b["id"]))["status"] == "ended"


def test_a_tail_does_not_repeat_the_words_just_given_out():
    from app.live.assembler import Phraser
    ph = Phraser(min_words=6, max_words=12)
    got = ph.partial("u1", "se iska answer lagao ye kisse paya jata hai", "", 1000)
    assert got and got[0].endswith("paya jata hai")
    # The final has one word fewer than the partials had: the words given out last are not a new tail.
    assert ph.final("u1", "iska answer lagao ye kisse paya jata hai? jata hai.") == ""
    got = ph.partial("u2", "haan bilkul theek hai sharing hi hoga", "", 2000)
    assert got
    assert ph.final("u2", "haan bilkul theek hai sharing hi hoga. sharing hi hoga chhatai ka kaam") == "chhatai ka kaam"
    got = ph.partial("u3", "ek do teen chaar paanch chhe hai", "", 3000)
    assert got and ph.final("u3", "ek do teen chaar paanch chhe hai aur saat aath") == "aur saat aath"   # a normal tail is untouched
