"""v1.1 pitch kit: a recorded Live session (V1_LIVE_RECORD), the side-by-side renderer, the blind listening test."""
import asyncio
import importlib.util
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import LocalStore
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession
from app.main import app
from app.providers.mock import MockTTS
from app.shared.audio_utils import ffmpeg_bin
from app.v1 import listen, pitch, record
from app.v1.flags import FLAGS

TA = "ta-IN"
LINE = "அஆஇஈஉஊ அஆஇஈஉஊ அஆஇஈஉஊ"


@pytest.mark.parametrize("flag", ["v1_live_record", "v1_listen_test"])
def test_pitch_flags_default_off(flag):
    assert Settings.model_fields[flag].default is False and getattr(get_settings(), flag) is False and flag in FLAGS


# ---------- the recorder alone ----------
def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2"), w.getframerate()


def test_recorder_lays_phrases_on_the_session_clock(tmp_path):
    r = record.Recorder("s1", [TA], 1000, engine="gpu", src_lang="hi-IN", root=tmp_path)
    assert not (tmp_path / "s1").exists()                       # nothing before the session starts
    r.start()
    tone = (np.ones(500, dtype="<i2") * 700).tobytes()          # 0.5 s at 1000 Hz
    r.add(TA, 1, tone, start_ms=2000, text="one", late_ms=120, media_s=1.5, voice="copied", tempo=None)
    r.add(TA, 2, tone, start_ms=2300, text="two", voice="stock")   # would overlap: goes straight after the first
    r.skip(TA, 3, "late", t_speech_ms=4000)
    r.close()
    x, sr = read_wav(tmp_path / "s1" / f"dub_{TA}.wav")
    assert sr == 1000 and len(x) == 3000
    assert not x[:2000].any() and (x[2000:3000] == 700).all()
    rows = [json.loads(line) for line in (tmp_path / "s1" / "phrases.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0] == {"seq": 1, "lang": TA, "start_ms": 2000, "track_ms": 2000, "dur_ms": 500, "text": "one",
                       "late_ms": 120, "media_s": 1.5, "voice": "copied"}
    assert rows[1]["start_ms"] == 2300 and rows[1]["track_ms"] == 2500      # where it lies in the file
    assert rows[2] == {"seq": 3, "lang": TA, "skipped": "late", "t_speech_ms": 4000}
    meta = json.loads((tmp_path / "s1" / "session.json").read_text(encoding="utf-8"))
    assert meta["rows"] == 3 and meta["track_s"] == {TA: 3.0} and meta["src_lang"] == "hi-IN" and meta["engine"] == "gpu"
    r.add(TA, 4, tone, start_ms=9000)                           # after the end: ignored
    assert len(read_wav(tmp_path / "s1" / f"dub_{TA}.wav")[0]) == 3000


# ---------- in the pipeline ----------
class SilentSTT:
    async def stream(self, frames, lang, **kw):
        async for _ in frames:
            pass
        return
        yield  # pragma: no cover


class LineLLM:
    async def translate_chunk(self, text, target, glossary, context, **kw):
        return LINE

    async def shorten(self, text, target, max_seconds, max_words=None):
        return text


class NoGpu:
    enabled, capacity = False, 1

    def speaks(self, lang):
        return False


def make(monkeypatch, tmp_path, row: dict, **flags):
    s = get_settings()
    for k, v in {"live_warmup": False, "live_merge_max": 1, "v1_record_dir": str(tmp_path / "rec"), **flags}.items():
        monkeypatch.setattr(s, k, v)
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    sess = LiveSession({"id": "r1", "target_langs": [TA], "src_lang": "hi-IN", **row})
    return LivePipeline(sess, stt=SilentSTT(), llm=LineLLM(), tts=MockTTS(), gpu=NoGpu()), sess, store


async def run(p: LivePipeline, sess: LiveSession, n: int = 2, listen_in: bool = True) -> list[dict]:
    q = sess.bus.subscribe(TA if listen_in else "src")
    await p.start()
    p.set_media(0.0, True)
    for k in range(n):
        p._dispatch(p.assembler.make("ek do teen chaar paanch", t_start_ms=2000 * k, t_end_ms=2000 * k + 1500,
                                     t_final_ms=2000 * k + 1500))
    got, ended = [], 0
    while ended < n and listen_in:
        m = await asyncio.wait_for(q.get(), 10)
        got.append(m)
        ended += int(m["type"] == "audio" and m["last"])
    if not listen_in:
        await asyncio.sleep(0.5)
    await p.stop()
    return got


def shape(msgs: list[dict]) -> list[tuple]:
    """What a viewer was sent, without the sound itself and the clock."""
    return [(m["type"], m.get("seq"), m.get("last"), sorted(m)) for m in msgs if m["type"] in ("caption", "audio")]


async def test_nothing_is_written_unless_the_flag_and_the_session_both_say_so(monkeypatch, tmp_path):
    rec = tmp_path / "rec"
    # the session asked, the flag is off
    p, sess, _ = make(monkeypatch, tmp_path, {"record": True})
    assert p._rec is None and "recording" not in sess.public()
    off = await run(p, sess)
    assert not rec.exists()
    # the flag is on, the session did not ask
    p, sess, _ = make(monkeypatch, tmp_path, {}, v1_live_record=True)
    assert p._rec is None and "recording" not in sess.public()
    plain = await run(p, sess)
    assert not rec.exists()
    assert not list(tmp_path.rglob("*.wav")) and not list(tmp_path.rglob("phrases.jsonl"))
    # both: the viewer is sent the very same messages, and the dub is on disk
    p, sess, store = make(monkeypatch, tmp_path, {"record": True}, v1_live_record=True)
    assert p._rec is not None and sess.public()["recording"] is True
    kept = await run(p, sess)
    assert shape(off) == shape(plain) == shape(kept)
    d = rec / "r1"
    rows = [json.loads(line) for line in (d / "phrases.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["seq"] for r in rows] == [1, 2] and all(r["lang"] == TA and r["text"] == LINE for r in rows)
    t = {r["seq"]: r["timings"] for r in await store.select("live_chunks", session_id="r1")}
    sent = {}
    for m in kept:
        if m["type"] == "audio" and m["pcm_b64"]:
            sent[m["seq"]] = sent.get(m["seq"], 0) + len(m["pcm_b64"]) * 3 // 4
    x, sr = read_wav(d / f"dub_{TA}.wav")
    assert sr == get_settings().live_sample_rate
    for r in rows:
        assert r["start_ms"] == r["track_ms"] == t[r["seq"]][f"t_heard:{TA}"]      # where a viewer's player starts it
        assert r["late_ms"] == t[r["seq"]][f"late:{TA}"] and r["voice"] == "stock" and r["media_s"] >= 0
        assert r["first_audio_ms"] == t[r["seq"]][f"t_first_audio:{TA}"] - t[r["seq"]]["t_speech_end"]
        assert abs(r["dur_ms"] - sent[r["seq"]] / 2 / sr * 1000) < 2                # every byte that went out
    assert len(x) == round((rows[-1]["track_ms"] + rows[-1]["dur_ms"]) * sr / 1000)
    assert not x[: round(rows[0]["track_ms"] * sr / 1000)].any()
    assert json.loads((d / "session.json").read_text(encoding="utf-8"))["rows"] == 2
    # nothing of it in the trace or the store beyond the ask itself
    assert all("text" not in k and "rec" not in k for row in t.values() for k in row)


async def test_a_phrase_nobody_hears_is_noted_as_skipped(monkeypatch, tmp_path):
    p, sess, _ = make(monkeypatch, tmp_path, {"record": True}, v1_live_record=True)
    await run(p, sess, n=1, listen_in=False)
    d = tmp_path / "rec" / "r1"
    rows = [json.loads(line) for line in (d / "phrases.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["skipped"] == "unheard" and "text" not in rows[0]
    assert not list(d.glob("*.wav"))


def test_a_session_is_kept_only_when_asked_and_the_flag_is_on(monkeypatch):
    c = TestClient(app)
    body = {"target_langs": [TA]}
    plain = c.post("/api/live/sessions", json=body).json()
    asked_off = c.post("/api/live/sessions", json={**body, "record": True}).json()
    assert sorted(plain) == sorted(asked_off) and "recording" not in asked_off      # flag off: the ask is ignored
    monkeypatch.setattr(get_settings(), "v1_live_record", True)
    assert "recording" not in c.post("/api/live/sessions", json=body).json()        # flag on, not asked
    kept = c.post("/api/live/sessions", json={**body, "record": True}).json()
    assert kept["recording"] is True and c.get(f"/api/live/sessions/{kept['id']}").json()["recording"] is True
    assert not record.folder().exists()                                             # asking writes nothing yet


# ---------- the renderer ----------
ROWS = [
    {"seq": 1, "lang": TA, "start_ms": 8000, "track_ms": 8000, "dur_ms": 1000, "text": "ஒன்று {x}", "late_ms": 0,
     "media_s": 2.0, "hold_ms": 6000, "first_audio_ms": 2000, "voice": "stock"},
    {"seq": 2, "lang": TA, "start_ms": 10400, "track_ms": 10400, "dur_ms": 1000, "text": "இரண்டு", "late_ms": 400,
     "media_s": 4.0, "hold_ms": 6000, "first_audio_ms": 2600, "voice": "copied"},
    {"seq": 3, "lang": TA, "skipped": "late", "t_speech_ms": 6000, "media_s": 6.0},
    {"seq": 4, "lang": TA, "start_ms": 15500, "track_ms": 15500, "dur_ms": 1000, "text": "நான்கு", "late_ms": 1500,
     "media_s": 8.0, "hold_ms": 6000, "first_audio_ms": 3000, "voice": "copied"},
]


def test_numbers_on_the_picture_come_from_the_recording_only():
    st = pitch.stats(ROWS)
    assert st["phrases"] == 4 and st["spoken"] == 3 and st["skipped"] == {"late": 1} and st["copied"] == 2
    assert st["first_audio_p50_ms"] == 2600 and st["first_audio_n"] == 3
    assert st["on_time_pct"] == 33.3 and st["within_1s_pct"] == 66.7 and st["timed"] == 3 and st["late_max_ms"] == 1500
    lines = pitch.overlay_lines(st)
    assert lines == ["first audio 2.6 s (median, 3 phrases)", "on time 33.3% within 0.25 s, 66.7% within 1 s",
                     "3 of 4 phrases dubbed, 2 in the copied voice"]
    # a microphone session has no video moment: no on-time figure is made up
    mic = [{k: v for k, v in r.items() if k not in ("late_ms", "media_s", "first_audio_ms")} for r in ROWS]
    st = pitch.stats(mic)
    assert st["on_time_pct"] is None and st["first_audio_p50_ms"] is None
    assert pitch.overlay_lines(st) == ["3 of 4 phrases dubbed, 2 in the copied voice"]
    assert pitch.overlay_lines(pitch.stats([ROWS[2]])) == []


def test_a_phrase_lies_at_its_video_moment_plus_its_lateness():
    assert [at for _, at in pitch.place(ROWS)] == [2000, 4400, 9500]
    mic = [{k: v for k, v in r.items() if k not in ("late_ms", "media_s")} for r in ROWS]
    assert [at for _, at in pitch.place(mic, offset_ms=6000)] == [2000, 4400, 9500]


def test_the_dub_track_is_cut_and_laid_on_the_pictures_clock(tmp_path):
    sr = 1000
    x = np.zeros(17000, dtype="<i2")
    for k, r in enumerate([ROWS[0], ROWS[1], ROWS[3]], start=1):
        x[r["track_ms"]: r["track_ms"] + r["dur_ms"]] = 100 * k
    with wave.open(str(tmp_path / "t.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(x.tobytes())
    assert pitch.build_track(tmp_path / "t.wav", pitch.place(ROWS), tmp_path / "o.wav", 11000) == sr
    y, _ = read_wav(tmp_path / "o.wav")
    assert len(y) == 11000 and (y[2000:3000] == 100).all() and (y[4400:5400] == 200).all() and (y[9500:10500] == 300).all()
    assert not y[:2000].any() and not y[3000:4400].any() and not y[5400:9500].any()


def test_captions_file_holds_the_labels_the_numbers_and_one_caption_at_a_time():
    placed = [(ROWS[0], 2000), (ROWS[1], 2600), (ROWS[3], 9500)]
    ass = pitch.captions_ass(placed, 400, 720, 12000, lang=TA, src_lang="hi-IN", lines=["first audio 2.6 s"])
    assert "PlayResX: 800" in ass and "PlayResY: 720" in ass
    assert "Original (Hindi)" in ass and "Tamil: AI-dubbed live by Bharat Dub" in ass and "first audio 2.6 s" in ass
    assert "Dialogue: 1,0:00:02.00,0:00:02.60,Cap,,0,0,0,,ஒன்று (x)" in ass       # ends when the next begins; braces gone
    assert "Dialogue: 1,0:00:09.50,0:00:10.50,Now,,0,0,0,,this line +1.5 s" in ass
    assert "{" not in ass.split("[Events]")[1]


def test_stereo_choices():
    split = pitch.audio_graph("split", 6000, 30.0)
    assert "adelay=6000:all=1" in split and "join=inputs=2:channel_layout=stereo" in split
    assert "anullsink" in pitch.audio_graph("dub", 0, 30.0) and "adelay" not in pitch.audio_graph("dub", 0, 30.0)
    assert f"volume={pitch.UNDER}" in pitch.audio_graph("mix", 0, 30.0)
    with pytest.raises(ValueError):
        pitch.render(Path("."), Path("."), TA, stereo="surround")


def test_render_makes_a_side_by_side_video_from_a_recording(tmp_path):
    """The real thing, small: 3 s of test picture played twice with a 1 s lead, two dubbed phrases."""
    video = tmp_path / "src.mp4"
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x284:rate=10:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(video)], check=True)
    r = record.Recorder("s9", [TA], 8000, src_lang="hi-IN", root=tmp_path)
    r.start()
    tone = (np.sin(np.arange(8000) / 4) * 9000).astype("<i2").tobytes()      # 1 s
    r.add(TA, 1, tone, start_ms=8000, text="ஒன்று இரண்டு", late_ms=100, media_s=1.5, hold_ms=6000, first_audio_ms=2100, voice="copied")
    r.add(TA, 2, tone, start_ms=12000, text="மூன்று", late_ms=900, media_s=5.0, hold_ms=6000, first_audio_ms=2500, voice="stock")
    r.skip(TA, 3, "late")
    r.close()
    res = pitch.render(tmp_path / "s9", video, TA, stereo="split", lead_s=1.0, loops=2, gap_ms=500, height=284, fps=10)
    out = Path(res["out"])
    assert out == tmp_path / "s9" / f"pitch_{TA}_split.mp4" and out.stat().st_size == res["bytes"] > 5000
    assert res["size"] == "320x284"                                         # two panes of 160
    assert 7.9 <= res["duration_s"] <= 8.2                                  # 1 s lead + 2 x (3 s + 0.5 s gap)
    assert res["on_picture"] == ["first audio 2.3 s (median, 2 phrases)", "on time 50% within 0.25 s, 100% within 1 s",
                                 "2 of 3 phrases dubbed, 1 in the copied voice"]
    # left ear the original, right ear the dub: the dub's first phrase lies at 1.5 s + 0.1 s
    pcm = subprocess.run([ffmpeg_bin(), "-loglevel", "error", "-i", str(out), "-f", "s16le", "-ac", "2", "-ar", "8000", "-"],
                         check=True, capture_output=True).stdout
    a = np.frombuffer(pcm, dtype="<i2").reshape(-1, 2).astype(np.float64)

    def loud(ch: int, t0: float, t1: float) -> float:
        return float(np.sqrt((a[int(t0 * 8000): int(t1 * 8000), ch] ** 2).mean()))
    assert loud(1, 0.2, 1.4) < 50 < loud(1, 1.8, 2.4) and loud(1, 3.0, 5.6) < 50 < loud(1, 6.1, 6.7)
    assert loud(0, 0.1, 0.8) < 50 < loud(0, 1.3, 3.8) and loud(0, 4.2, 4.4) < 50 < loud(0, 4.8, 7.2)   # lead, pass, gap, pass
    with pytest.raises(ValueError):
        pitch.render(tmp_path / "s9", video, "bn-IN")                       # no such language in the recording


# ---------- the blind listening test ----------
def pairs_folder(root: Path, n: int = 3) -> Path:
    base = root / "listen" / "pairs"
    for sub in ("x", "y"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    pairs = []
    for k in range(1, n + 1):
        (base / "x" / f"{k}.wav").write_bytes(b"RIFF" + b"A" * (40 + k))
        (base / "y" / f"{k}.wav").write_bytes(b"RIFF" + b"B" * (80 + k))
        pairs.append({"id": f"p{k}", "a": f"x/{k}.wav", "b": f"y/{k}.wav", "system_a": "ours", "system_b": "theirs",
                      "lang": TA, "text": f"line {k}"})
    (base / "manifest.json").write_text(json.dumps({"name": "test set", "pairs": pairs}), encoding="utf-8")
    return base


@pytest.fixture
def listen_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "v1_listen_dir", str(tmp_path / "listen"))
    return tmp_path / "listen"


def test_listen_routes_are_404_and_write_nothing_with_the_flag_off(listen_dir, tmp_path):
    pairs_folder(tmp_path)
    c = TestClient(app)
    assert c.get("/api/v1/listen/pairs?listener=u1").status_code == 404
    assert c.get("/api/v1/listen/audio/p1/1?listener=u1").status_code == 404
    assert c.get("/api/v1/listen/summary").status_code == 404
    answer = {"listener": "u1", "pair": "p1", "rating_1": 4, "rating_2": 2, "prefer": "1"}
    assert c.post("/api/v1/listen/answers", json=answer).status_code == 404
    assert not (listen_dir / "results.jsonl").exists()


def test_listen_with_no_pairs_and_no_ratings(monkeypatch, listen_dir):
    monkeypatch.setattr(get_settings(), "v1_listen_test", True)
    c = TestClient(app)
    assert c.get("/api/v1/listen/pairs?listener=u1").json() == {"name": "", "total": 0, "done": 0, "pairs": []}
    s = c.get("/api/v1/listen/summary").json()
    assert s["note"] == "no ratings yet" and s["answers"] == 0 and s["systems"] == {}
    assert not listen_dir.exists()                                          # looking creates nothing


def test_listen_is_blind_shuffled_per_listener_and_counted_per_system(monkeypatch, listen_dir, tmp_path):
    monkeypatch.setattr(get_settings(), "v1_listen_test", True)
    pairs_folder(tmp_path, n=6)
    c = TestClient(app)
    q = c.get("/api/v1/listen/pairs?listener=u1").json()
    assert q["total"] == 6 and q["done"] == 0 and sorted(p["id"] for p in q["pairs"]) == [f"p{k}" for k in range(1, 7)]
    assert all(set(p) == {"id", "lang", "text"} for p in q["pairs"])        # no system, no file name
    assert "ours" not in json.dumps(q) and "theirs" not in json.dumps(q) and ".wav" not in json.dumps(q)
    assert c.get("/api/v1/listen/pairs?listener=bad id").status_code == 400

    def first_system(listener: str, pair: str) -> str:
        r = c.get(f"/api/v1/listen/audio/{pair}/1?listener={listener}")
        assert r.status_code == 200 and "content-disposition" not in r.headers
        other = c.get(f"/api/v1/listen/audio/{pair}/2?listener={listener}").content
        assert {r.content[4:5], other[4:5]} == {b"A", b"B"}
        return "ours" if r.content[4:5] == b"A" else "theirs"

    sides = {(u, f"p{k}"): first_system(u, f"p{k}") for u in ("u1", "u2", "u3", "u4") for k in range(1, 7)}
    assert set(sides.values()) == {"ours", "theirs"}                        # the sides are shuffled ...
    assert any(sides[("u1", f"p{k}")] != sides[("u2", f"p{k}")] for k in range(1, 7))   # ... differently per listener
    assert sides[("u1", "p1")] == first_system("u1", "p1")                  # ... and stay put for one listener
    assert c.get("/api/v1/listen/audio/p1/3?listener=u1").status_code == 404
    assert c.get("/api/v1/listen/audio/nope/1?listener=u1").status_code == 404

    def answer(listener: str, pair: str, ours: int, theirs: int, prefer: str) -> int:
        ours_first = sides[(listener, pair)] == "ours"
        side = {"ours": "1" if ours_first else "2", "theirs": "2" if ours_first else "1", "same": "same"}[prefer]
        body = {"listener": listener, "pair": pair, "rating_1": ours if ours_first else theirs,
                "rating_2": theirs if ours_first else ours, "prefer": side}
        return c.post("/api/v1/listen/answers", json=body).status_code

    assert answer("u1", "p1", 5, 2, "ours") == 200
    assert answer("u1", "p2", 4, 4, "same") == 200
    assert answer("u2", "p1", 3, 4, "theirs") == 200
    assert answer("u2", "p2", 1, 1, "theirs") == 200
    assert answer("u2", "p2", 4, 3, "ours") == 200                          # changed their mind: the last one counts
    bad = {"listener": "u1", "pair": "p1", "rating_1": 6, "rating_2": 1, "prefer": "1"}
    assert c.post("/api/v1/listen/answers", json=bad).status_code == 422
    assert c.post("/api/v1/listen/answers", json={**bad, "rating_1": 3, "prefer": "left"}).status_code == 400
    assert c.post("/api/v1/listen/answers", json={**bad, "rating_1": 3, "pair": "nope"}).status_code == 404
    s = c.get("/api/v1/listen/summary").json()
    assert s["answers"] == 4 and s["listeners"] == 2 and s["pairs"] == 6 and s["pairs_rated"] == 2 and s["note"] == ""
    assert s["same"] == 1 and s["stated"] == 3 and s["set"] == "test set"
    assert s["systems"]["ours"]["n"] == 4 and s["systems"]["ours"]["mean_rating"] == 4.0          # 5, 4, 3, 4
    assert s["systems"]["theirs"]["mean_rating"] == 3.25                                           # 2, 4, 4, 3
    assert s["systems"]["ours"]["preference_pct"] == 66.7 and s["systems"]["theirs"]["preference_pct"] == 33.3
    q = c.get("/api/v1/listen/pairs?listener=u1").json()
    assert q["done"] == 2 and len(q["pairs"]) == 4 and "p1" not in [p["id"] for p in q["pairs"]]
    assert len((listen_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 5      # every answer is kept


def test_manifest_leaves_out_what_cannot_be_played_blind(monkeypatch, listen_dir, tmp_path):
    base = pairs_folder(tmp_path, n=1)
    (tmp_path / "outside.wav").write_bytes(b"RIFFxxxx")
    man = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    ok = man["pairs"][0]
    man["pairs"] += [{**ok, "id": "p1"},                                       # the same id twice
                     {**ok, "id": "gone", "b": "y/404.wav"},                   # a clip that is not there
                     {**ok, "id": "out", "a": "../../outside.wav"},            # a path out of the pairs folder
                     {**ok, "id": "same", "system_b": "ours"},                 # one system against itself
                     {**ok, "id": "bad id"}, {"id": "empty"}]
    (base / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    assert [p["id"] for p in listen.manifest()["pairs"]] == ["p1"]
    (base / "manifest.json").write_text("not json", encoding="utf-8")
    assert listen.manifest() == {"name": "", "pairs": []}


def test_pairs_folder_is_built_from_two_folders_of_same_named_clips(monkeypatch, listen_dir, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "make_listen_pairs", Path(__file__).resolve().parents[2] / "scripts" / "v1" / "make-listen-pairs.py")
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    a, b = tmp_path / "f5", tmp_path / "other"
    a.mkdir(), b.mkdir()
    for name in ("ta-IN_001.wav", "ta-IN_002.wav", "only_a.wav"):
        (a / name).write_bytes(b"RIFF" + b"A" * 50)
    for name in ("ta-IN_001.wav", "ta-IN_002.wav", "only_b.wav", "notes.txt"):
        (b / name).write_bytes(b"RIFF" + b"B" * 50)
    out = listen_dir / "pairs"
    res = mk.build(a, b, out, "indicf5", "other", texts={"ta-IN_001": "முதல் வரி"}, name="f5 against other")
    assert res["pairs"] == 2 and res["only_in_a"] == ["only_a.wav"] and res["only_in_b"] == ["only_b.wav"]
    assert sorted(f.name for f in (out / "a").iterdir()) == ["0001.wav", "0002.wav"]      # no name gives the system away
    got = listen.manifest()
    assert got["name"] == "f5 against other" and [p["id"] for p in got["pairs"]] == ["p0001", "p0002"]
    assert got["pairs"][0]["lang"] == TA and got["pairs"][0]["text"] == "முதல் வரி" and got["pairs"][1]["text"] == ""
    assert got["pairs"][0]["files"]["indicf5"].read_bytes()[4:5] == b"A"
    with pytest.raises(ValueError):
        mk.build(a, b, out, "indicf5", "other")                                # would overwrite: needs --add
    assert mk.build(a, b, out, "indicf5", "third", add=True)["pairs"] == 4
    assert [p["id"] for p in listen.manifest()["pairs"]] == ["p0001", "p0002", "p0003", "p0004"]
    with pytest.raises(ValueError):
        mk.build(a, b, tmp_path / "o2", "same", "same")
