"""The v1 model servers in stub mode (no model, no GPU), called through the backend's own clients."""
import asyncio
import os
import sys
from pathlib import Path

import httpx
import numpy as np
import pytest
import soundfile as sf

os.environ["V1_STUB"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gpu_engine_v1"))

import maya_server  # noqa: E402
import qa_server  # noqa: E402
import transcribe_server  # noqa: E402
import tts_server  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.providers.stt_indic import IndicTranscribeSTT  # noqa: E402
from app.providers.tts_gnani import ConsentRequired  # noqa: E402
from app.providers.tts_gpu_v1 import IndicF5V1Voice, MayaVoice  # noqa: E402
from app.v1.qa import QAClient  # noqa: E402


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://server")


@pytest.fixture
def wav(tmp_path) -> Path:
    p = tmp_path / "ref.wav"
    t = np.arange(16000 * 3) / 16000
    sf.write(p, 0.2 * np.sin(2 * np.pi * 200 * t).astype(np.float32), 16000)
    return p


async def test_batching_voice_server_speaks_and_batches(wav, tmp_path, monkeypatch):
    monkeypatch.setattr(tts_server, "REF_DIR", tmp_path)
    await tts_server.startup()
    s = get_settings().model_copy(update={"v1_tts_server_url": "http://server"})
    voice = IndicF5V1Voice(s, client(tts_server.app))
    assert voice.enabled and voice.capacity == 4 and voice.speaks("ta-IN") and not voice.speaks("en-IN")
    with pytest.raises(ConsentRequired):
        await voice.set_ref("s1", str(wav), "namaste doston", consent_at=None)      # consent gates cloning here too
    await voice.set_ref("s1", str(wav), "namaste doston", consent_at="2026-11-23T00:00:00Z")
    pcm, rate = await voice.synth("s1", "வணக்கம் நண்பர்களே", "ta-IN")
    assert rate == 24000 and len(pcm) > 24000 * 2 * 0.3
    fast, _ = await voice.synth("s1", "வணக்கம் நண்பர்களே", "ta-IN", speed=1.5)
    assert len(fast) < len(pcm)                                                       # the speed parameter is honoured
    await asyncio.gather(*(voice.synth("s1", f"வரி எண் {i}", "ta-IN") for i in range(4)))
    h = (await voice.health())[0]
    assert h["ok"] and h["stub"] and h["largest_batch"] >= 2 and h["batch_errors"] == 0
    with pytest.raises(Exception):
        await voice.synth("nobody", "x", "ta-IN")                                     # no sample for that session


async def test_maya_server_takes_a_voice_and_speaks_english_too(wav, tmp_path, monkeypatch):
    monkeypatch.setattr(maya_server, "REF_DIR", tmp_path)
    s = get_settings().model_copy(update={"v1_maya_url": "http://server"})
    voice = MayaVoice(s, client(maya_server.app))
    assert voice.speaks("en-IN") and voice.speaks("pa-IN")
    await voice.set_ref("m1", str(wav), "namaste doston", consent_at="2026-11-23T00:00:00Z")
    pcm, rate = await voice.synth("m1", "Hello friends, welcome back", "en-IN")
    assert rate == 24000 and len(pcm) > 10000
    assert (await voice.health())[0]["ok"]


async def test_transcribe_server_answers_the_stt_client(wav):
    s = get_settings().model_copy(update={"v1_transcribe_url": "http://server"})
    res = await IndicTranscribeSTT(s, client(transcribe_server.app)).transcribe(str(wav), "ta-IN")
    assert res.text and res.detected_lang == "ta-IN"
    assert (await client(transcribe_server.app).get("/health")).json()["stub"] is True


async def test_qa_server_scores_and_diarizes(wav):
    s = get_settings().model_copy(update={"v1_qa_url": "http://server"})
    qa = QAClient(s, client(qa_server.app))
    got = await qa.score(wav, "வணக்கம் நண்பர்களே", "ta-IN", ref_wav=wav)
    assert got["backcheck"] == 1.0 and got["similarity"] == 0.5 and got["heard"]
    assert (await qa.score(wav, "வணக்கம்", "ta-IN"))["similarity"] is None            # no sample, no similarity
    segs = await qa.diarize(wav)
    assert len(segs) == 1 and segs[0]["speaker"] == "S1" and segs[0]["end"] == pytest.approx(3.0, abs=0.1)


def test_words_heard_matches_the_backend_scoring():
    from app.v1.qa import heard_share as words_heard
    assert words_heard("পি সি আর ব্যবহার হয়", "পিসিআর ব্যবহার হয়") == 1.0      # spelled apart, heard as one word
    assert words_heard("ஒன்று இரண்டு மூன்று", "ஒன்று மூன்று") == pytest.approx(2 / 3)
    for said, heard in (("ஒன்று இரண்டு மூன்று", "ஒன்று மூன்று"), ("aaj hum khelenge", "aaj ham khelenge yaar"), ("", "x"),
                        ("পি সি আর ব্যবহার হয়", "পিসিআর ব্যবহার হয়")):
        assert qa_server.words_heard(said, heard) == words_heard(said, heard)


async def test_qa_server_gpu_endpoint_reads_the_card_and_knows_none_in_stub_mode(monkeypatch):
    async with client(qa_server.app) as c:
        assert (await c.get("/gpu")).json() == {"stub": True, "gpus": [], "processes": []}
    import common
    rows = {"gpu": [["NVIDIA A100-SXM4-40GB", "35533", "5427", "40960", "19", "51", "110.5"]],
            "compute-apps": [["4242", "/opt/venv/bin/python3", "13414"], ["4243", "python", "[N/A]"]]}
    monkeypatch.setattr(common, "STUB", False)
    monkeypatch.setattr(common, "_smi", lambda query, fields: rows[query])
    got = common.gpu_summary()
    assert got["gpus"] == [{"name": "NVIDIA A100-SXM4-40GB", "used_gb": 34.7, "free_gb": 5.3, "total_gb": 40.0,
                            "util_pct": 19.0, "temp_c": 51.0, "power_w": 110.5}]
    assert got["processes"] == [{"pid": 4242, "name": "python3", "used_gb": 13.1},
                                {"pid": 4243, "name": "python", "used_gb": None}]
