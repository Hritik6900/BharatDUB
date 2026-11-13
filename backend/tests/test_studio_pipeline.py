"""Studio end to end with fake providers and a generated test video (needs ffmpeg)."""
import shutil
from pathlib import Path

import pytest

from app.config import get_settings
from app.db import LocalStore
from app.shared import audio_utils as au
from app.studio.runner import StudioRunner
from app.studio.stages import segment
from tests.fakes import FakeLLM, FakeSTT, FakeTTS

def _has_ffmpeg() -> bool:
    try:
        return bool(shutil.which("ffmpeg") or au.ffmpeg_bin())
    except au.FFmpegError:
        return False


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not installed")

SEGS = [(0.5, 2.0), (2.4, 4.0), (5.0, 8.0)]


def make_video(path: Path, seconds: int = 10) -> Path:
    au.run([au.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"testsrc=size=160x120:rate=10:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], what="make video")
    return path


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(segment, "vad", lambda audio: list(SEGS))
    s = get_settings().model_copy(update={"studio_separate": False, "llm_model": "fake"})
    store = LocalStore(tmp_path / "db.json")
    stt, llm, tts = FakeSTT(), FakeLLM(), FakeTTS()
    return StudioRunner(store=store, stt=stt, llm=llm, tts=tts, settings=s), stt, llm, tts, tmp_path


async def new_job(r: StudioRunner, tmp: Path, name: str = "reel.mp4", lang: str = "ta-IN") -> str:
    upload = make_video(tmp / f"upload_{name}")
    job = await r.create_job(upload, name, [lang])
    await r.run(job["id"])
    return job["id"]


async def test_full_pipeline_outputs_cache_and_partial_rerender(rig):
    r, stt, llm, tts, tmp = rig
    job_id = await new_job(r, tmp)
    job = await r.store.get("jobs", job_id)
    assert job["status"] == "done", job.get("error")
    assert job["src_lang"] == "hi-IN"
    timings = job["stage_timings"]
    for st in ("extract", "separate", "segment", "transcribe", "translate", "voice", "fit", "mix", "render"):
        assert st in timings
    assert timings["_usage"]["stt_calls"] == 3

    renders = await r.store.select("renders", job_id=job_id)
    assert [x["lang"] for x in renders] == ["ta-IN"]
    mp4 = r.job_dir(job_id) / "out" / renders[0]["mp4_path"]
    info = au.probe(mp4)
    assert info["has_video"] and info["has_audio"] and abs(info["duration"] - 10) < 0.5
    srt = (r.job_dir(job_id) / "out" / renders[0]["srt_path"]).read_text(encoding="utf-8")
    assert srt.startswith("1\n00:00:00,000 --> 00:00:02,000\nAI-dubbed by Bharat Dub")
    assert "00:00:00,500 --> 00:00:02,000\nta-IN namaste line src_000" in srt

    # Same video again: STT and TTS fully cached.
    stt_before, tts_before = stt.calls, tts.calls
    job2 = await new_job(r, tmp, "again.mp4")
    assert (await r.store.get("jobs", job2))["status"] == "done"
    assert stt.calls == stt_before and tts.calls == tts_before

    # Edit one line: exactly one new TTS call, output re-rendered with the new text.
    segs = await r.spoken_segments(job_id)
    tr = (await r.store.select("translations", segment_id=segs[1]["id"], lang="ta-IN"))[0]
    before = tts.calls
    updated = await r.edit_line(job_id, tr["id"], "puthiya vari")
    assert tts.calls == before + 1 and tts.texts[-1] == "puthiya vari"
    assert updated["edited"] is True
    srt = (r.job_dir(job_id) / "out" / renders[0]["srt_path"]).read_text(encoding="utf-8")
    assert "puthiya vari" in srt

    # Re-render another language: no STT, edited ta-IN line is kept.
    stt_before = stt.calls
    await r.render_langs(job_id, ["bn-IN", "ta-IN"])
    assert stt.calls == stt_before
    assert {x["lang"] for x in await r.store.select("renders", job_id=job_id)} == {"ta-IN", "bn-IN"}
    tr_after = await r.store.get("translations", tr["id"])
    assert tr_after["text"] == "puthiya vari"


async def test_too_long_line_is_shortened(rig, monkeypatch):
    r, stt, llm, tts, tmp = rig

    async def long_batch(lines, target, glossary):
        return ["x" * 80 for _ in lines]  # 4.8 s of audio for ~1.5 s slots
    monkeypatch.setattr(llm, "translate_batch", long_batch)
    job_id = await new_job(r, tmp, "long.mp4", lang="te-IN")  # te-IN: not in the translate cache yet
    assert (await r.store.get("jobs", job_id))["status"] == "done"
    assert llm.shorten_calls >= 1
    trs = await r.store.select("translations", lang="te-IN")
    assert all(t["fit_speed"] <= 1.35 for t in trs)


async def test_rejects_long_video(rig):
    r, *_, tmp = rig
    from app.studio.stages.extract import IngestError

    r.s = r.s.model_copy(update={"max_video_seconds": 5})
    with pytest.raises(IngestError, match="limit is 5 s"):
        await r.create_job(make_video(tmp / "long.mp4", 8), "long.mp4", ["ta-IN"])


async def test_clone_requires_consent(rig):
    r, *_ = rig
    from app.studio.runner import Ctx

    job = await r.store.insert("jobs", {"source_path": "x", "target_langs": ["ta-IN"]})
    p = await r.store.insert("voice_profiles", {"embedding": {"embedding": "e", "shape": [1, 768], "dtype": "d"}})
    await r.store.update("jobs", job["id"], {"voice_profile_id": p["id"]})
    ctx = Ctx(job["id"], r.job_dir(job["id"]))
    assert (await r.voice_spec(ctx, "ta-IN")) == {"kind": "stock", "voice": "Asmita"}
    await r.store.update("voice_profiles", p["id"], {"consent_at": "2026-11-13T00:00:00Z"})
    assert (await r.voice_spec(ctx, "ta-IN"))["kind"] == "clone"


async def test_voice_from_video_creates_profile_only_with_consent(rig):
    r, _, _, tts, tmp = rig
    calls = []
    orig = tts.clone_embedding

    async def spy(wav_path, *, consent_at):
        calls.append(consent_at)
        return await orig(wav_path, consent_at=consent_at)

    tts.clone_embedding = spy
    # No consent recorded at upload: nothing is cloned, the stock voice is used.
    plain = await r.create_job(make_video(tmp / "a.mp4"), "a.mp4", ["ta-IN"])
    await r.run(plain["id"])
    assert not calls and not (await r.store.get("jobs", plain["id"])).get("voice_profile_id")

    consent = {"consent_at": "2026-11-13T10:00:00Z", "consent_text": "mine"}
    job = await r.create_job(make_video(tmp / "b.mp4"), "b.mp4", ["ta-IN"], None, consent)
    await r.run(job["id"])
    done = await r.store.get("jobs", job["id"])
    assert done["status"] == "done", done.get("error")
    speech = sum(e - s for s, e in SEGS)
    if speech >= 5:
        assert calls == ["2026-11-13T10:00:00Z"]
        profile = await r.store.get("voice_profiles", done["voice_profile_id"])
        assert profile["consent_at"] == consent["consent_at"] and profile["display_name"] == "Voice from b"
        from app.studio.runner import Ctx
        assert (await r.voice_spec(Ctx(job["id"], r.job_dir(job["id"])), "ta-IN"))["kind"] == "clone"
    else:
        assert not calls and any("too little" in w for w in done["stage_timings"]["_warnings"])
