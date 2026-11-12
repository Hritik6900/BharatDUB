import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.shared.audio_utils import cache_key
from app.shared.srt import build_srt, srt_time
from app.studio.stages.fit import needed_speed, slots
from app.studio.stages.mix import duck_regions, gain_curve
from app.studio.stages.segment import fixed_windows, merge_segments


def test_merge_segments_merges_short_gaps_and_caps_length():
    assert merge_segments([(0, 1), (1.2, 2), (3, 4)]) == [(0, 2), (3, 4)]
    out = merge_segments([(0, 60)])
    assert out == [(0, 25), (25, 50), (50, 60)]
    assert merge_segments([(0, 0.1)]) == []  # too short to send


def test_fixed_windows():
    assert fixed_windows(45) == [(0, 20), (20, 40), (40, 45)]


def test_slots_and_speed():
    assert slots([1.0, 3.0, 7.0], 10.0) == [2.0, 4.0, 3.0]
    assert needed_speed(1.0, 2.0) == 1.0
    assert needed_speed(3.0, 2.0) == 1.5
    assert needed_speed(3.0, 0.0) == 1.0


def test_srt_format_and_label():
    assert srt_time(3725.5) == "01:02:05,500"
    s = build_srt([(0.5, 1.5, "hello"), (2, 3, "  ")])
    assert s == "1\n00:00:00,000 --> 00:00:02,000\nAI-dubbed by Bharat Dub\n\n2\n00:00:00,500 --> 00:00:01,500\nhello\n\n"


def test_cache_key_stable_and_sensitive():
    assert cache_key("a", 1, ["x"]) == cache_key("a", 1, ["x"])
    assert cache_key("a", 1) != cache_key("a", 2)


def test_ducking():
    regions = duck_regions([(100, 50), (120, 100), (500, 10)], 1000)
    assert regions == [(100, 220), (500, 510)]
    g = gain_curve(1000, regions, sr=1000)
    assert np.isclose(g[150], 10 ** (-6 / 20)) and g[0] == 1.0 and g[999] == 1.0


def test_create_job_validation():
    c = TestClient(app)
    files = {"file": ("a.mp4", b"x", "video/mp4")}
    r = c.post("/api/jobs", files=files, data={"target_langs": "ta-IN"})
    assert r.status_code == 400 and "own" in r.json()["detail"]
    r = c.post("/api/jobs", files=files, data={"target_langs": "xx-YY", "owns_video": "true"})
    assert r.status_code == 400
    r = c.post("/api/jobs", files={"file": ("a.txt", b"x", "text/plain")},
               data={"target_langs": "ta-IN", "owns_video": "true"})
    assert r.status_code == 400
    r = c.post("/api/jobs", files=files, data={"target_langs": "ta-IN", "owns_video": "true"})
    assert r.status_code == 400 and "read" in r.json()["detail"]  # not a real video


def test_voice_requires_consent_and_glossary_crud():
    c = TestClient(app)
    r = c.post("/api/voices", files={"sample": ("v.wav", b"x", "audio/wav")}, data={"consent_text": "I agree"})
    assert r.status_code == 403
    r = c.post("/api/glossary", json={"term": "Valorant"})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert any(t["term"] == "Valorant" for t in c.get("/api/glossary").json()["terms"])
    assert c.post("/api/glossary", json={"term": "Valorant"}).status_code == 409
    assert c.delete(f"/api/glossary/{tid}").status_code == 200
