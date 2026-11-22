"""Studio HQ with fake providers: text steps, versions and scoring, flagged lines, the swap, phase batching."""
import io
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.config import get_settings
from app.db import LocalStore
from app.providers.base import ProviderError
from app.shared import audio_utils as au
from app.studio.runner import StudioRunner
from app.studio.stages import segment
from app.v1.hq import finish
from app.v1.hq import runner as hq
from app.v1.hq import text as hqtext
from app.v1.hq import voice as hqvoice
from tests.fakes import FakeLLM, FakeSTT, FakeTTS
from tests.test_studio_pipeline import SEGS, make_video


def _has_ffmpeg() -> bool:
    try:
        return bool(shutil.which("ffmpeg") or au.ffmpeg_bin())
    except au.FFmpegError:
        return False


needs_ffmpeg = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not installed")


def tone(seconds: float, sr: int = 44100, hz: float = 220.0) -> bytes:
    t = np.arange(int(sr * seconds)) / sr
    buf = io.BytesIO()
    sf.write(buf, 0.3 * np.sin(2 * np.pi * hz * t).astype(np.float32), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class WordLLM(FakeLLM):
    async def shorten(self, text, target, max_seconds, max_words=None):
        self.shorten_calls += 1
        return " ".join(text.split()[: max_words or 3])


class FakeStages:
    """The six steps with scripted answers. `checks` are the back-check scores handed out in order."""

    mode, engine = "studio_hq", "cloud"

    def __init__(self, settings, own: bool = False, checks: list[float] | None = None, seconds_per_word: float = 0.3,
                 lists: dict[str, list[str]] | None = None) -> None:
        self.own, self.checks, self.spw = own, list(checks or []), seconds_per_word
        self.lists = {"transcribe": ["prisma"], "translate": ["gemma"], "review": ["gemma"], "speak": ["timbre"],
                      "score": ["prisma"], "diarize": ["none"], "candidates": [], **(lists or {})}
        self.fallbacks: list[dict[str, str]] = []
        self.used: dict[str, str] = {}
        self.spoken: list[tuple[str, float]] = []
        self.chats: list[str] = []
        self.llm_obj = WordLLM()
        outer = self

        class R:
            s = settings

            def timeout(self, stage):
                return 5.0

            def provider(self, kind, name):
                class P:
                    async def transcribe(self, path, lang, **kw):
                        from app.providers.base import STTResult
                        return STTResult(text=f"doosri sunwai {Path(path).stem}")
                return P()
        self.r = R()
        del outer

    def names(self, stage):
        return list(self.lists.get(stage, []))

    def own_voice(self, lang, voice):
        return self.own

    def llm(self, stage="translate"):
        return self.llm_obj

    async def chat(self, system, user, *, stage="translate", max_tokens=3000, temperature=0.2):
        self.chats.append(stage + ":" + system[:40])
        items = json.loads(user)
        if "recognisers disagree" in system:
            return json.dumps([it["heard"][-1] for it in items])
        if "Clean each line" in system:
            return json.dumps([str(x)[3:] if str(x).startswith("um ") else str(x) for x in items])
        if "`max_words`: how many" in system:
            return json.dumps([" ".join(("dub " + it["line"]).split()[: it["max_words"]]) for it in items])
        if "You review" in system:
            return json.dumps([it["dub"].replace("galat", "sahi") for it in items])
        if "cannot read digits" in system:
            return json.dumps([x.replace("5", "paanch") for x in items])
        raise AssertionError("unexpected prompt: " + system[:60])

    async def speak(self, text, lang, voice, *, speed=1.0):
        self.spoken.append((text, speed))
        self.used["speak"] = "indicf5" if self.own else "timbre"
        # every take sounds a little different, as a real voice engine does
        return tone(max(0.2, len(text.split()) * self.spw / speed), hz=200.0 + 7 * len(self.spoken))

    async def score(self, wav, text, lang, ref_wav=None):
        check = self.checks.pop(0) if self.checks else 1.0
        from app.v1.qa import HEARD_RULE
        return {"heard": text, "backcheck": check, "similarity": 0.4 if ref_wav else None, "by": "prisma", "rule": HEARD_RULE}

    async def diarize(self, wav):
        return []


# ---------- text steps ----------
async def test_text_steps_keep_the_lines_when_an_answer_is_unusable():
    s = get_settings()
    st = FakeStages(s)
    lines = ["um aaj hum khelenge", "phir milte hain"]
    assert await hqtext.cleanup(st, lines, []) == ["aaj hum khelenge", "phir milte hain"]
    merged = await hqtext.merge_hearings(st, [{"a": "aaj ham khelenge", "b": "aaj hum khelenge"}, {"a": "phir milte hain"}],
                                         ["aaj ham khelenge", "phir milte hain"], [])
    assert merged == ["aaj hum khelenge", "phir milte hain"]          # only the line that was heard two ways is asked about
    out = await hqtext.translate_timed(st, lines, [3, 2], "ta-IN", [], native=False)
    assert out == ["dub um aaj", "dub phir"]                           # the word limit reached the model
    final, changed = await hqtext.review(st, lines, ["yeh galat hai", "theek"], [5, 5], "ta-IN", [], False)
    assert final == ["yeh sahi hai", "theek"] and changed == 1
    spoken, n = await hqtext.normalise(st, ["score 5 hai", "koi ank nahi"], "ta-IN", False)
    assert spoken == ["score paanch hai", "koi ank nahi"] and n == 1

    class Broken(FakeStages):
        async def chat(self, *a, **k):
            return "sorry, here you go: not json"
    bad = Broken(s)
    assert await hqtext.cleanup(bad, lines, []) == lines
    assert await hqtext.translate_timed(bad, lines, [3, 2], "ta-IN", [], False) is None
    assert await hqtext.review(bad, lines, ["a", "b"], [3, 3], "ta-IN", [], False) == (["a", "b"], 0)
    assert await hqtext.normalise(bad, ["score 5 hai"], "ta-IN", False) == (["score 5 hai"], 0)


def test_word_limit_follows_the_time_a_line_has():
    assert hqtext.word_limit(slot_s=4.0, speech_s=3.0, src_words=8, pace_ms=450) == 8      # 3.75 s at 450 ms a word
    assert hqtext.word_limit(slot_s=2.0, speech_s=3.0, src_words=8, pace_ms=450) == 4      # the slot is the limit
    assert hqtext.word_limit(slot_s=0.3, speech_s=0.3, src_words=1, pace_ms=450) == 2      # never under two
    assert hqtext.acceptable("வணக்கம் game", "ta-IN", native=False)
    assert not hqtext.acceptable("வணக்கம் game", "ta-IN", native=True)                     # our engine reads no Latin
    assert not hqtext.acceptable("नमस्ते", "ta-IN", native=False)


# ---------- versions and scoring ----------
@pytest.fixture
def hq_settings(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "v1_studio_hq", True)
    monkeypatch.setattr(s, "v1_fit_115", True)
    monkeypatch.setattr(s, "data_dir", str(tmp_path / "data"))   # its own cache: nothing left behind for other tests
    return s


VOICE = {"kind": "stock", "voice": "Asmita"}
CLONE = {"kind": "clone", "embedding": {"embedding": "x", "shape": [], "dtype": "gpu-ref", "ref_path": "r.wav",
                                         "ref_text": "namaste", "consent_at": "2026-11-23T00:00:00Z"}}


async def test_a_line_that_passes_is_spoken_once(hq_settings):
    st = FakeStages(hq_settings, checks=[0.95])
    best, made, flagged = await hqvoice.best_line(st, "ek do teen char", "ta-IN", VOICE, 3.0, None, hq_settings, {})
    assert not flagged and len(made) == 1 and best.passed and best.backcheck == 0.95 and best.speed == 1.0
    assert len(st.spoken) == 1


async def test_own_voice_makes_more_versions_until_one_passes(hq_settings):
    st = FakeStages(hq_settings, own=True, checks=[0.4, 0.6, 0.97])
    usage: dict = {}
    best, made, flagged = await hqvoice.best_line(st, "line alpha beta gamma", "ta-IN", CLONE, 3.0, None, hq_settings, usage)
    assert not flagged and [v.backcheck for v in made] == [0.4, 0.6, 0.97] and best.idx == 2
    assert usage["tts_calls"] == 3 and usage["score_calls"] == 3


async def test_a_stock_voice_is_not_asked_twice_for_the_same_words(hq_settings):
    st = FakeStages(hq_settings, own=False, checks=[0.5])
    best, made, flagged = await hqvoice.best_line(st, "line delta epsilon zeta", "ta-IN", VOICE, 3.0, None, hq_settings, {})
    assert flagged and len(made) == 1 and "heard back" in best.why[0]      # the same voice would say the same thing


async def test_a_line_too_long_for_its_slot_is_sped_by_the_engine_then_shortened(hq_settings):
    st = FakeStages(hq_settings, own=True, seconds_per_word=0.5)
    text = "one two three four five six seven eight"                       # 4.0 s for a 2.0 s slot
    best, made, flagged = await hqvoice.best_line(st, text, "ta-IN", CLONE, 2.0, None, hq_settings, {})
    assert st.spoken[1] == (text, 1.5)                                     # duration control: the engine at its limit
    assert len(made) == 3                                                  # no further takes of the same words: they would be as long
    assert best.text != text and len(best.text.split()) < 8                # still too long: fewer words
    assert best.speed <= 1.15 and not flagged
    assert hqvoice.limits(hq_settings)[0] == 1.15


async def test_a_line_that_never_passes_is_flagged_with_the_best_version(hq_settings):
    st = FakeStages(hq_settings, own=True, checks=[0.3, 0.5, 0.45, 0.2])
    best, made, flagged = await hqvoice.best_line(st, "line eta theta iota", "ta-IN", CLONE, 3.0, None, hq_settings, {})
    assert flagged and len(made) == hq_settings.v1_hq_nbest and best.backcheck == 0.5
    assert all("alts" not in v.public() and "heard" not in v.public() for v in made)


async def test_an_unchecked_line_is_spoken_and_reported_not_failed(hq_settings):
    class NoScorer(FakeStages):
        async def score(self, *a, **k):
            from app.v1.stages import StageFailed
            raise StageFailed("score", ["prisma: down"])
    st = NoScorer(hq_settings)
    best, made, flagged = await hqvoice.best_line(st, "line kappa lambda mu", "ta-IN", VOICE, 3.0, None, hq_settings, {})
    assert not flagged and best.backcheck is None and best.why == ["not checked: no scorer answered"]


async def test_first_voice_failure_is_an_error(hq_settings):
    class Mute(FakeStages):
        async def speak(self, *a, **k):
            raise ProviderError("voice is down")
    with pytest.raises(ProviderError):
        await hqvoice.best_line(Mute(hq_settings), "line nu xi omicron", "ta-IN", VOICE, 3.0, None, hq_settings, {})


# ---------- the mix ----------
def test_sidechain_gain_follows_the_voice():
    sr = 16000
    voice = np.concatenate([np.zeros(sr), 0.3 * np.sin(2 * np.pi * 200 * np.arange(sr) / sr), np.zeros(sr)]).astype(np.float32)
    g = finish.sidechain_gain(voice, sr, duck_db=-9.0)
    low = 10 ** (-9 / 20)
    assert g[: sr // 2].min() > 0.99                       # silence: the background is untouched
    assert abs(g[sr + sr // 2] - low) < 0.02               # under the voice: down by 9 dB
    assert g[-1] > 0.95                                    # and back up after it


# ---------- whole jobs ----------
@pytest.fixture
def rig(tmp_path, monkeypatch, hq_settings):
    monkeypatch.setattr(segment, "vad", lambda audio: list(SEGS))
    s = hq_settings.model_copy(update={"studio_separate": False, "llm_model": "fake", "v1_trace": False})
    store = LocalStore(tmp_path / "db.json")
    r = StudioRunner(store=store, stt=FakeSTT(), llm=FakeLLM(), tts=FakeTTS(), settings=s)
    made: list[FakeStages] = []

    def stages(job_id, engine, **kw):
        made.append(FakeStages(s, **kw))
        return made[-1]
    return r, tmp_path, made, stages, monkeypatch


@needs_ffmpeg
async def test_hq_job_end_to_end_flags_and_swap(rig):
    r, tmp, made, stages, monkeypatch = rig
    # Line 2 fails its check twice (own voice), then passes on the third version.
    monkeypatch.setattr(hq, "stages_for", lambda job_id, engine: stages(job_id, engine, own=True,
                        checks=[1.0, 0.3, 0.4, 0.95, 1.0], lists={"transcribe": ["prisma", "whisper_gpu"]}))
    job = await r.create_job(make_video(tmp / "u.mp4"), "reel.mp4", ["ta-IN"], quality="hq")
    await r.run(job["id"])
    job = await r.store.get("jobs", job["id"])
    assert job["status"] == "done", job.get("error")
    st = made[0]
    assert [c.split(":")[0] for c in st.chats] == ["translate", "translate", "translate", "review", "translate"]   # merge, clean, translate, review, numbers as words
    segs = await r.spoken_segments(job["id"])
    assert all(s.get("hearings") == {"whisper_gpu": f"doosri sunwai src_{s['idx']:03}"} for s in segs)
    assert segs[0]["src_text"].startswith("doosri sunwai") and segs[0]["src_text_raw"].startswith("namaste line")
    trs = [(await r.store.select("translations", segment_id=s["id"], lang="ta-IN"))[0] for s in segs]
    assert [t["flagged"] for t in trs] == [False, False, False]
    assert len(trs[1]["alts"]) == 3 and trs[1]["picked"] == 2 and trs[1]["qa"]["backcheck"] == 0.95
    assert all(t["fit_speed"] <= 1.15 for t in trs)
    for stage in ("hear_again", "speakers", "clean", "translate", "voice", "fit", "mix", "render"):
        assert stage in job["stage_timings"], stage
    renders = await r.store.select("renders", job_id=job["id"])
    mp4 = r.job_dir(job["id"]) / "out" / renders[0]["mp4_path"]
    assert au.probe(mp4)["has_audio"]

    # The editor's swap: use the first version of line 2 instead; no new voice call, the language is rendered again.
    before = len(st.spoken)
    row = await r.pick_version(job["id"], trs[1]["id"], 0)
    assert row["picked"] == 0 and row["picked_by_hand"] and row["qa"]["backcheck"] == 0.3 and len(st.spoken) == before
    with pytest.raises(KeyError):
        await r.pick_version(job["id"], trs[1]["id"], 9)

    # A standard job on the same runner goes the v0 way: no HQ fields, no HQ stages.
    plain = await r.create_job(make_video(tmp / "p.mp4"), "plain.mp4", ["ta-IN"])
    await r.run(plain["id"])
    pj = await r.store.get("jobs", plain["id"])
    assert pj["status"] == "done" and "hear_again" not in pj["stage_timings"]
    pseg = (await r.spoken_segments(plain["id"]))[0]
    assert "alts" not in (await r.store.select("translations", segment_id=pseg["id"], lang="ta-IN"))[0]


@needs_ffmpeg
async def test_hq_flag_off_means_the_v0_path(rig):
    r, tmp, made, stages, monkeypatch = rig
    r.s = r.s.model_copy(update={"v1_studio_hq": False})
    job = await r.create_job(make_video(tmp / "u.mp4"), "reel.mp4", ["ta-IN"], quality="hq")
    await r.run(job["id"])
    assert (await r.store.get("jobs", job["id"]))["status"] == "done" and made == []


@needs_ffmpeg
async def test_hq_batch_runs_phase_by_phase(rig):
    r, tmp, made, stages, monkeypatch = rig
    order: list[tuple[str, str]] = []
    for name in ("phase_a", "phase_b", "phase_c"):
        real = getattr(hq, name)

        async def spy(runner, ctx, *a, _real=real, _name=name, **k):
            order.append((_name, ctx.job_id))
            return await _real(runner, ctx, *a, **k)
        monkeypatch.setattr(hq, name, spy)
    monkeypatch.setattr(hq, "stages_for", lambda job_id, engine: stages(job_id, engine))
    a = await r.create_job(make_video(tmp / "a.mp4"), "a.mp4", ["ta-IN"], quality="hq")
    b = await r.create_job(make_video(tmp / "b.mp4", seconds=9), "b.mp4", ["ta-IN"], quality="hq")
    out = await r.run_hq_batch([a["id"], b["id"]])
    assert out == {a["id"]: "done", b["id"]: "done"}
    assert [p for p, _ in order] == ["phase_a", "phase_a", "phase_b", "phase_b", "phase_c", "phase_c"]
    for j in (a, b):
        assert (await r.store.get("jobs", j["id"]))["status"] == "done"
