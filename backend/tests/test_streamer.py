"""Streamer profile and voice (STREAMER_MODE.md, phase 1): consent first, a scored GPU voice, preview, delete."""
import io
import uuid

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from app.live.pipeline import GPU_CHECK_LINES
from app.main import app
from app.providers.base import STTResult

CONSENT = "I, Asha, agree that Bharat Dub may make a copy of my voice."


def recording(seconds: float = 12.0) -> bytes:
    t = np.arange(int(44100 * seconds)) / 44100
    buf = io.BytesIO()
    sf.write(buf, (np.sin(2 * np.pi * 220 * t) * 0.4).astype(np.float32), 44100, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class Clone:
    async def clone_embedding(self, wav_path, *, consent_at):
        assert consent_at
        return {"embedding": "e", "shape": [1, 768], "dtype": "torch.bfloat16"}

    async def synth(self, text, lang, voice):
        return b"RIFFgnani"


class Engine:
    """The GPU engine: the first cut makes a poor voice, the second a good one."""
    enabled = True

    def __init__(self):
        self.refs: list[str] = []

    def speaks(self, lang):
        return lang != "en-IN"

    async def set_ref(self, voice_id, wav_path, ref_text, *, consent_at):
        assert consent_at, "never without consent"
        self.refs.append(voice_id)
        return {"ok": True}

    async def synth(self, voice_id, text, lang, speed=None):
        return (b"\x10\x20" * 96000, 24000)   # 4 s: a natural pace for the check sentence


class Hears:
    def __init__(self):
        self.checks = 0

    async def transcribe(self, wav_path, lang="indic-auto", **kw):
        if "bd_gpu_check" not in wav_path:
            return STTResult(text="yeh meri awaaz ka namoona hai doston", latency_s=0.0)
        self.checks += 1
        line = GPU_CHECK_LINES["ta-IN"]
        return STTResult(text=line.split()[0] if self.checks == 1 else line, latency_s=0.0)


def setup(monkeypatch):
    engine, hears = Engine(), Hears()
    monkeypatch.setattr("app.shared.voices.get_tts", lambda: Clone())
    monkeypatch.setattr("app.streamer.routes.get_tts", lambda: Clone())
    monkeypatch.setattr("app.streamer.routes.get_gpu_voice", lambda: engine)
    monkeypatch.setattr("app.streamer.voice_ref.get_gpu_voice", lambda: engine)
    monkeypatch.setattr("app.streamer.voice_ref.get_stt", lambda: hears)
    return engine, hears


def test_streamer_voice_needs_consent_and_gets_the_best_scored_cut(monkeypatch):
    engine, hears = setup(monkeypatch)
    c = TestClient(app)
    handle = "asha_" + uuid.uuid4().hex[:6]
    r = c.post("/api/streamers", json={"handle": handle, "display_name": "Asha", "default_langs": ["ta-IN", "bn-IN"]})
    assert r.status_code == 201 and r.json()["voice"] is None
    sid = r.json()["id"]
    assert c.post("/api/streamers", json={"handle": handle, "display_name": "Other"}).status_code == 409
    assert c.post("/api/streamers", json={"handle": "a b", "display_name": "x"}).status_code == 400
    assert c.get(f"/api/streamers/@{handle}").json()["id"] == sid          # found by handle too

    files = {"sample": ("me.wav", recording(), "audio/wav")}
    r = c.post(f"/api/streamers/{sid}/voice", files=files, data={"consent_text": CONSENT})   # box not ticked
    assert r.status_code == 403 and not engine.refs
    assert c.post(f"/api/streamers/{sid}/voice/preview?lang=ta-IN").status_code == 403

    r = c.post(f"/api/streamers/{sid}/voice", files={"sample": ("me.wav", recording(), "audio/wav")},
               data={"consent_text": CONSENT, "consent": "true"})
    assert r.status_code == 201, r.text
    v = r.json()["voice"]
    assert v["gnani_clone"] and v["gpu_voice"] and v["consent_at"]
    assert v["ref_score"] == 1.0 and v["ref_cuts_tried"] == 2     # the poor first cut was replaced by a better one
    assert 3.5 <= v["ref_seconds"] <= 8 and v["ref_build_s"] >= 0

    r = c.post(f"/api/streamers/{sid}/voice/preview?lang=ta-IN")
    assert r.status_code == 200 and r.headers["x-engine"] == "gpu" and r.content[:4] == b"RIFF"
    assert engine.refs[-1] == f"voice-{v['id']}"                  # the stored voice, sent to the engine again
    r = c.post(f"/api/streamers/{sid}/voice/preview?lang=en-IN")  # English is not an engine language
    assert r.status_code == 400 or r.headers.get("x-engine") == "gnani"

    assert c.delete(f"/api/streamers/{sid}/voice").json() == {"deleted": True}
    assert c.get(f"/api/streamers/{sid}").json()["voice"] is None
    assert c.post(f"/api/streamers/{sid}/voice/preview?lang=ta-IN").status_code == 403


def test_streamer_profile_can_be_edited_and_deleted(monkeypatch):
    setup(monkeypatch)
    c = TestClient(app)
    handle = "edit_" + uuid.uuid4().hex[:6]
    sid = c.post("/api/streamers", json={"handle": handle, "display_name": "Typo", "default_langs": ["ta-IN"]}).json()["id"]
    r = c.patch(f"/api/streamers/{sid}", json={"display_name": " Asha ", "default_langs": ["bn-IN", "te-IN", "bn-IN"]})
    assert r.status_code == 200 and r.json()["display_name"] == "Asha" and r.json()["default_langs"] == ["bn-IN", "te-IN"]
    assert r.json()["handle"] == handle                                      # the handle never changes
    assert c.patch(f"/api/streamers/{sid}", json={"default_langs": ["xx-XX"]}).status_code == 400
    assert c.patch(f"/api/streamers/{sid}", json={"display_name": "   "}).status_code == 400
    assert c.get(f"/api/streamers/{sid}").json()["display_name"] == "Asha"   # a refused edit changed nothing

    assert c.delete(f"/api/streamers/{sid}").json() == {"deleted": True}
    assert c.get(f"/api/streamers/{sid}").status_code == 404
    assert c.post("/api/streamers", json={"handle": handle, "display_name": "Again"}).status_code == 201   # handle is free


def test_voice_sample_is_capped_even_when_the_microphone_is_quiet():
    import struct

    from app.live.pipeline import ENROL_MIN_RMS, speech_cut
    def frame(level: int) -> bytes:
        return struct.pack("<512h", *([level, -level] * 256))
    # 20 s where only every fourth frame is loud enough to count, the rest is quiet speech just under the bar
    loud, soft = frame(int(ENROL_MIN_RMS * 3) + 50), frame(max(1, int(ENROL_MIN_RMS * 0.9)))
    frames = [loud if i % 4 == 0 else soft for i in range(625)]
    cut = speech_cut(frames)
    assert cut is not None and len(cut) / 2 / 16000 <= 9.1


async def test_a_voice_sample_whose_text_no_longer_fits_the_file_is_read_again(tmp_path):
    """The engine takes its pace from the sample and its text together. When the stored text was written for a
    longer cut than the file on disk, the file is transcribed again and the profile corrected; when they belong
    together nothing is asked of the speech service."""
    from app.db import LocalStore
    from app.streamer.voice_ref import sample_text

    ref = tmp_path / "v_ref.wav"
    sf.write(str(ref), np.zeros(16000 * 9, dtype=np.float32), 16000, subtype="PCM_16")    # a 9 s cut
    store = LocalStore(tmp_path / "db.json")
    asked: list[str] = []

    class Hears:
        async def transcribe(self, path, lang):
            asked.append(lang)
            return STTResult(text="यह नौ सेकंड की आवाज़ है दोस्तों", detected_lang=lang, latency_s=0.1)

    old = await store.insert("voice_profiles", {"ref_path": ref.name, "ref_seconds": 15.7, "consent_at": "2026-11-14T00:00:00Z",
                                                "ref_text": "a much longer text that was written for a fifteen second cut"})
    assert await sample_text(old, ref, "hi-IN", stt=Hears(), store=store) == "यह नौ सेकंड की आवाज़ है दोस्तों"
    fixed = await store.get("voice_profiles", old["id"])
    assert fixed["ref_seconds"] == 9.0 and fixed["ref_text"].startswith("यह नौ")
    assert await sample_text(fixed, ref, "hi-IN", stt=Hears(), store=store) == fixed["ref_text"]
    assert asked == ["hi-IN"]                               # the second time the two belong together: no call
    gone = {**fixed, "ref_seconds": 3.0}
    assert await sample_text(gone, tmp_path / "missing.wav", stt=Hears(), store=store) == gone["ref_text"]
