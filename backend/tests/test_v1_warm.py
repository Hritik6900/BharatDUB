"""v1.1 session start (`V1_LIVE_WARMSTART`) and the one English voice (`V1_EN_SINGLE_VOICE`)."""
import asyncio
import base64

import numpy as np
import pytest

from app.config import VOICE_BY_LANG, Settings, get_settings
from app.db import LocalStore
from app.live.pipeline import LivePipeline, prefetch_stored_voice
from app.live.session import LiveSession
from app.providers.base import ProviderError
from app.providers.mock import MockLLM, MockTTS
from app.v1 import warm
from app.v1.flags import flags

TA, PA, EN = "ta-IN", "pa-IN", "en-IN"
CONSENT = "2026-11-24T00:00:00+00:00"
EMB = {"embedding": "e", "shape": [1, 768], "dtype": "torch.bfloat16"}
NEW_KEYS = ("open", "handover")


def voiced(f0: float, seconds: float = 2.0, amp: float = 6000.0) -> bytes:
    """A voice-like sound: a fundamental with falling harmonics, 16 kHz PCM16."""
    t = np.arange(int(16000 * seconds)) / 16000
    x = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 6))
    return (x / np.max(np.abs(x)) * amp).astype("<i2").tobytes()


def frames(pcm: bytes) -> list[bytes]:
    return [pcm[i:i + 1024] for i in range(0, len(pcm) - 1023, 1024)]


# ---------- the parts alone ----------
def test_pitch_of_a_low_and_a_high_voice_and_none_for_noise_or_silence():
    low, high = np.frombuffer(voiced(118), dtype="<i2")[:1024], np.frombuffer(voiced(214), dtype="<i2")[:1024]
    assert abs(warm.f0_hz(low) - 118) < 4 and abs(warm.f0_hz(high) - 214) < 8
    rng = np.random.default_rng(1)
    assert warm.f0_hz((rng.standard_normal(1024) * 3000).astype("<i2")) is None      # loud, no pitch
    assert warm.f0_hz((np.frombuffer(voiced(118), dtype="<i2")[:1024] * 0.01).astype("<i2")) is None   # a pause


def test_tracker_says_nothing_before_a_second_of_voice_then_male_or_female_and_stops_listening():
    tr = warm.PitchTracker()
    for f in frames(voiced(118, 0.5)):
        tr.add(f)
    assert tr.gender() is None and tr.median_hz() is None        # 7 windows: too little
    for f in frames(voiced(118, 1.0)):
        tr.add(f)
    assert tr.gender() == "male" and abs(tr.median_hz() - 118) < 4
    hi = warm.PitchTracker()
    for f in frames(voiced(214, 2.0) + b"\x00" * 32000):          # the silence adds nothing
        hi.add(f)
    assert hi.gender() == "female" and len(hi.f0s) in (31, 32)
    for f in frames(voiced(214, 12.0)):
        hi.add(f)
    assert hi.done and len(hi.f0s) == warm.MAX_WINDOWS


def test_stock_voice_nearest_to_the_speaker_and_what_is_said_where_a_language_has_one_gender():
    assert warm.pick_stock("bn-IN", "male") == {"voice": "Dhruva", "matched": True, "note": ""}
    assert warm.pick_stock("bn-IN", "female") == {"voice": "Kirra", "matched": True, "note": ""}
    for lang in (TA, "te-IN"):                                    # female voices only
        got = warm.pick_stock(lang, "male")
        assert got["voice"] == VOICE_BY_LANG[lang] and not got["matched"] and "female stock voices only" in got["note"]
    got = warm.pick_stock(PA, None)
    assert got["voice"] == VOICE_BY_LANG[PA] and not got["matched"] and "not known" in got["note"]


def test_fade_level_and_the_step_towards_another_level():
    pcm = (np.ones(2400) * 8000).astype("<i2").tobytes()          # 0.1 s at 24 kHz
    out = np.frombuffer(warm.fade(pcm, 24000, 50, out=True), dtype="<i2")
    assert out[0] == 8000 and out[1199] == 8000 and abs(int(out[-1])) < 20 and 5000 < out[1800] < 6200   # equal power
    head = np.frombuffer(warm.fade(pcm, 24000, 50, out=False), dtype="<i2")
    assert abs(int(head[0])) < 20 and head[-1] == 8000
    assert warm.fade(b"\x01\x00", 24000, 50, out=True) == b"\x01\x00"
    assert warm.level(pcm) == 8000 and warm.level(b"\x00\x00" * 500) == 0.0
    half = np.frombuffer(warm.toward(pcm, 8000, 2000, 0.5), dtype="<i2")
    assert 3900 < half[0] < 4100                                  # half the way in dB: 8000 -> 4000 on the way to 2000
    assert np.frombuffer(warm.toward(pcm, 8000, 100, 1.0), dtype="<i2")[0] > 3900    # never more than 6 dB
    assert warm.toward(pcm, 8000, 0, 0.5) == pcm and warm.toward(pcm, 0, 2000, 0.5) == pcm
    assert np.max(np.frombuffer(warm.toward((np.ones(100) * 30000).astype("<i2").tobytes(), 3000, 6000, 1.0), dtype="<i2")) <= 32000


def test_english_voice_for_a_session_is_copy_or_stock_and_auto_is_the_measured_choice_stock():
    assert warm.en_mode("copy") == "copy" and warm.en_mode("stock") == "stock"
    assert warm.en_mode("auto") == "stock" and warm.en_mode("anything") == "stock"


def test_both_flags_exist_and_are_off_by_default():
    fresh = Settings(_env_file=None)
    assert fresh.v1_live_warmstart is False and fresh.v1_en_single_voice is False and fresh.v1_en_voice == "auto"
    assert flags()["V1_LIVE_WARMSTART"] is False and flags()["V1_EN_SINGLE_VOICE"] is False


# ---------- in the pipeline ----------
class SilentSTT:
    async def stream(self, frames, lang, **kw):
        async for _ in frames:
            pass
        return
        yield  # pragma: no cover


class RecLLM(MockLLM):
    def __init__(self) -> None:
        self.asked: list[tuple[str, str, dict]] = []

    async def translate_chunk(self, text, target, glossary, context, **kw):
        self.asked.append((text, target, kw))
        return f"{target} {text}"


class RecTTS(MockTTS):
    """Remembers which voice said what; a voice named in `dead` makes nothing."""

    def __init__(self) -> None:
        super().__init__(24000)
        self.said: list[tuple[str, str, str]] = []      # (language, "clone" or the stock voice's name, text)
        self.dead: set[str] = set()

    async def synth_stream(self, text, lang, voice, *, sample_rate=None, speed=1.0):
        name = "clone" if voice["kind"] == "clone" else voice["voice"]
        self.said.append((lang, name, text))
        if name in self.dead:
            raise ProviderError("tts: HTTP 400 unknown voice", status=400)
        async for chunk in super().synth_stream(text, lang, voice, sample_rate=sample_rate):
            yield chunk


class RecGpu:
    """Our voice engine: speaks the Indian languages once it has a voice; three processes."""
    enabled, capacity = True, 3

    def __init__(self) -> None:
        self.refs: list[str] = []
        self.lines: list[tuple[str, str]] = []
        self.healths = 0

    def speaks(self, lang):
        return lang != EN

    async def set_ref(self, session_id, wav_path, ref_text, *, consent_at, steps=None):
        assert consent_at, "never a copy without consent"
        self.refs.append(session_id)
        return {"ok": True}

    async def synth(self, session_id, text, lang, speed=None):
        self.lines.append((lang, text))
        return (np.ones(12000) * 12000).astype("<i2").tobytes(), 24000     # 0.5 s, louder than the stock tone

    async def health(self):
        self.healths += 1
        return [{"ok": True}] * 3


def setup(monkeypatch, tmp_path, langs, row=None, **flags_on):
    s = get_settings()
    for k, v in {"live_warmup": False, "live_merge_max": 1, "live_sync_adapt": False, **flags_on}.items():
        monkeypatch.setattr(s, k, v)
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    sess = LiveSession({"id": "w1", "target_langs": langs, "src_lang": "hi-IN", **(row or {})})
    llm, tts, gpu = RecLLM(), RecTTS(), RecGpu()
    return LivePipeline(sess, stt=SilentSTT(), llm=llm, tts=tts, gpu=gpu), sess, llm, tts, gpu, store


async def say(p: LivePipeline, qs: dict, text: str = "ek do teen chaar paanch", ago_ms: int = 0) -> dict[str, list[dict]]:
    """One phrase, spoken `ago_ms` ago, through the pipeline; each language's messages up to the end of its audio."""
    now = p.sess.now_ms() - ago_ms
    chunk = p.assembler.make(text, t_start_ms=now, t_end_ms=now + 400, t_final_ms=now + 400)
    p._dispatch(chunk)
    out: dict[str, list[dict]] = {}
    for lang, q in qs.items():
        got = out.setdefault(lang, [])
        while True:
            m = await asyncio.wait_for(q.get(), 10)
            if m.get("seq") == chunk.seq:
                got.append(m)
                if m["type"] == "audio" and m["last"]:
                    break
    return out


def pcm_of(msgs: list[dict]) -> np.ndarray:
    return np.frombuffer(b"".join(base64.b64decode(m["pcm_b64"]) for m in msgs if m["type"] == "audio" and m["pcm_b64"]), dtype="<i2")


async def stored(store: LocalStore) -> dict[int, dict]:
    return {r["seq"]: r["timings"] for r in await store.select("live_chunks", session_id="w1")}


async def profile_with_copy(store: LocalStore) -> str:
    return (await store.insert("voice_profiles", {"display_name": "me", "consent_at": CONSENT, "embedding": EMB}))["id"]


async def test_flags_off_the_start_and_the_voices_are_v0s(monkeypatch, tmp_path):
    """Nothing listens for pitch, v0's warm-up runs (first language only, no hosted line when our engine is coming),
    the stock voice is the language's usual one, English is chosen line by line, nothing new is stored or sent."""
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [TA, PA], {"voice_from_stream": {"consent_at": CONSENT}},
                                          live_warmup=True)
    assert p._pitch is None and p._en_mode is None and p.warm_stats() == {}
    qs = {lg: sess.bus.subscribe(lg) for lg in (TA, PA)}
    await p.start()
    for f in frames(voiced(118)):
        p.feed(f)                                                  # a male speaker changes nothing
    await asyncio.sleep(0.4)
    assert [(text, lang) for text, lang, _ in llm.asked] == [("नमस्ते", TA)] and tts.said == [] and gpu.healths == 0
    await say(p, qs)
    assert {(lang, name) for lang, name, _ in tts.said} == {(TA, VOICE_BY_LANG[TA]), (PA, VOICE_BY_LANG[PA])}
    await p.stop()
    assert not [k for row in (await stored(store)).values() for k in row if k.split(":")[0] in NEW_KEYS]
    assert sess.prefetch is None


async def test_flags_off_english_in_a_gpu_session_is_still_chosen_line_by_line(monkeypatch, tmp_path):
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [EN], {"engine": "gpu"})
    sess.row["voice_profile_id"] = await profile_with_copy(store)
    qs = {EN: sess.bus.subscribe(EN)}
    await p.start()
    p.set_media(0.0, True)
    await say(p, qs, ago_ms=5000)           # 1 s before it is due: a stock voice (v0's rule, the mix the flag removes)
    await say(p, qs)                        # 6 s before it is due: the copy
    assert [name for _, name, _ in tts.said] == [VOICE_BY_LANG[EN], "clone"]
    await p.stop()


async def test_warm_start_asks_every_language_and_every_engine_before_the_first_phrase(monkeypatch, tmp_path):
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [TA, PA, EN], {"voice_from_stream": {"consent_at": CONSENT}},
                                          v1_live_warmstart=True, live_warmup=True)
    await p.start()
    for _ in range(100):
        if "total" in p.warm_ms:
            break
        await asyncio.sleep(0.02)
    assert sorted((lang, kw.get("native", False)) for _, lang, kw in llm.asked) == [(EN, False), (PA, True), (TA, True)]
    # No voice is on our engines yet: they are asked how they are (their connections open), no line is made there,
    # and the hosted voice says one short line per language, the ones our engine takes over later included.
    assert gpu.healths == 1 and gpu.lines == []
    assert [(lang, name) for lang, name, _ in tts.said] == [(TA, VOICE_BY_LANG[TA]), (PA, VOICE_BY_LANG[PA]), (EN, VOICE_BY_LANG[EN])]
    calls = p.warm_stats()["warm"]["calls_ms"]
    assert set(calls) == {"translate:ta-IN", "translate:pa-IN", "translate:en-IN", "engines", "voice:ta-IN", "voice:pa-IN",
                          "voice:en-IN", "total"} and all(isinstance(v, int) for v in calls.values())
    assert p._stock_pick == {}                                    # a warm-up line never fixes the session's voice
    await p.stop()


async def test_warm_start_with_a_stored_voice_speaks_one_short_line_per_language_on_every_engine(monkeypatch, tmp_path):
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [TA, PA], v1_live_warmstart=True)
    p.gpu_ready, p._gpu_sid, p._gpu_stored = True, "voice-1", True
    await p.start()
    for _ in range(100):
        if "total" in p.warm_ms:
            break
        await asyncio.sleep(0.02)
    assert len(gpu.lines) == 3 and {lang for lang, _ in gpu.lines} == {TA, PA}     # three processes, both languages
    assert all(len(text.split()) == 2 for _, text in gpu.lines) and tts.said == []  # the hosted voice has nothing to say here
    assert isinstance(p.warm_ms["engine_lines"], int)
    await p.stop()


async def test_a_failing_warm_up_call_is_noted_and_stops_nothing(monkeypatch, tmp_path):
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [PA], {"voice_from_stream": {"consent_at": CONSENT}},
                                          v1_live_warmstart=True)
    tts.dead = {VOICE_BY_LANG[PA]}

    async def down():
        raise ProviderError("gpu: ConnectError", retryable=True)
    gpu.health = down
    await p.start()
    for _ in range(100):
        if "total" in p.warm_ms:
            break
        await asyncio.sleep(0.02)
    assert p.warm_ms["voice:pa-IN"] == "failed: ProviderError" and p.warm_ms["engines"] == "failed: ProviderError"
    assert p.running and isinstance(p.warm_ms["translate:pa-IN"], int)
    await p.stop()


async def test_stock_voice_follows_the_speakers_pitch_is_kept_and_says_so_where_there_is_no_such_voice(monkeypatch, tmp_path):
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [TA, "bn-IN"], v1_live_warmstart=True)
    gpu.enabled = False                                          # a stock session: no copied voice at all
    qs = {lg: sess.bus.subscribe(lg) for lg in (TA, "bn-IN")}
    await p.start()
    for _ in range(100):
        if "total" in p.warm_ms:
            break
        await asyncio.sleep(0.02)
    tts.said.clear()
    for f in frames(voiced(118)):
        p.feed(f)
    await say(p, qs)
    assert {(lang, name) for lang, name, _ in tts.said} == {(TA, "Asmita"), ("bn-IN", "Dhruva")}
    w = p.warm_stats()["warm"]
    assert w["speaker"] == "male" and abs(w["f0_hz"] - 118) < 4
    assert w["stock_voice"]["bn-IN"]["matched"] is True and w["stock_voice"][TA]["matched"] is False
    assert "female stock voices only" in w["stock_voice"][TA]["note"] and w["opening_stock_lines"] == {}
    p._pitch = warm.PitchTracker()                               # even if the pitch were heard differently later
    for f in frames(voiced(214)):
        p.feed(f)
    tts.said.clear()
    await say(p, qs)
    assert {(lang, name) for lang, name, _ in tts.said} == {(TA, "Asmita"), ("bn-IN", "Dhruva")}   # the voice is kept
    await p.stop()
    assert not [k for row in (await stored(store)).values() for k in row if k.split(":")[0] in NEW_KEYS]


async def test_a_matched_voice_that_makes_nothing_gives_way_to_the_usual_one(monkeypatch, tmp_path):
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [PA], v1_live_warmstart=True)
    gpu.enabled = False
    tts.dead = {"Zayan"}
    q = {PA: sess.bus.subscribe(PA)}
    await p.start()
    for f in frames(voiced(118)):
        p.feed(f)
    first = await say(p, q)
    assert len(pcm_of(first[PA])) == 0 and tts.said[-1][1] == "Zayan"
    second = await say(p, q)
    assert len(pcm_of(second[PA])) > 0 and tts.said[-1][1] == VOICE_BY_LANG[PA]
    assert "did not answer" in p.warm_stats()["warm"]["stock_voice"][PA]["note"]
    await p.stop()


async def test_the_change_from_the_opening_stock_voice_to_the_copied_one_is_softened(monkeypatch, tmp_path):
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [PA], {"voice_from_stream": {"consent_at": CONSENT}},
                                          v1_live_warmstart=True, live_trim_silence=False)
    q = {PA: sess.bus.subscribe(PA)}
    await p.start()
    p.set_media(0.0, True)
    opening = pcm_of((await say(p, q, ago_ms=4500))[PA])          # due in 1.5 s, no voice yet: a stock voice
    assert tts.said[-1][0] == PA and len(opening) and np.max(np.abs(opening[-24:])) < 400     # ends in a fade
    assert np.max(np.abs(opening[: len(opening) // 2])) > 3000
    stock_level = p._stock_level[PA]
    p.gpu_ready, p._gpu_sid = True, "v"                           # the copied voice has arrived
    lines = [pcm_of((await say(p, q))[PA]) for _ in range(3)]
    assert len(gpu.lines) == 3
    assert np.max(np.abs(lines[0][:24])) < 400                    # the first copied line begins with a fade
    levels = [float(np.median(np.abs(x[len(x) // 2:]))) for x in lines]
    assert stock_level < levels[0] < levels[1] < levels[2] and abs(levels[2] - 12000) < 100   # in two steps from the stock voice's level
    assert np.max(np.abs(lines[1][:24])) > 3000 and np.max(np.abs(lines[2][:24])) > 11000     # later lines are whole
    await p.stop()
    t = await stored(store)
    assert [t[k].get("open:pa-IN") for k in sorted(t)] == [1, None, None, None]
    assert [t[k].get("handover:pa-IN") for k in sorted(t)] == [None, 1, 2, None]
    w = p.warm_stats()["warm"]
    assert w["opening_stock_lines"] == {PA: 1} and w["softened_lines"] == {PA: 2}


async def test_an_opening_line_waits_for_the_copied_voice_only_while_a_sample_is_on_its_way(monkeypatch, tmp_path):
    async def first_line(flag: bool, busy: bool) -> tuple[int, str]:
        p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [PA], {"voice_from_stream": {"consent_at": CONSENT}},
                                              v1_live_warmstart=flag)
        q = {PA: sess.bus.subscribe(PA)}
        await p.start()
        p.set_media(0.0, True)
        await asyncio.sleep(0.3)             # the warm-up's own hosted line is out of the way
        tts.said.clear()
        p._gpu_busy = busy
        t0 = sess.now_ms()
        await say(p, q, ago_ms=1800)         # due in 4.2 s; a line for our engine would have to start in 2 s
        took = sess.now_ms() - t0
        await p.stop()
        return took, tts.said[0][1]

    took, voice = await first_line(False, False)
    assert took >= 1950 and voice == VOICE_BY_LANG[PA]      # v0: waits for a voice that is not even being made
    took, voice = await first_line(True, False)
    assert took < 1500 and voice == VOICE_BY_LANG[PA]        # warm start: the stock voice speaks at once
    took, voice = await first_line(True, True)
    assert took >= 1950 and voice == VOICE_BY_LANG[PA]      # a sample is on its way: the line still waits for it


async def test_a_streamers_stored_voice_is_sent_when_the_session_is_made_and_not_again_at_its_start(monkeypatch, tmp_path):
    from app.shared import voices
    monkeypatch.setattr(voices, "voices_dir", lambda: tmp_path)
    (tmp_path / "ref.wav").write_bytes(b"RIFF")

    async def text_of(p, path, lang, stt=None):
        return p["ref_text"]
    monkeypatch.setattr("app.streamer.voice_ref.sample_text", text_of)

    async def run(flag: bool) -> tuple[RecGpu, LiveSession, LivePipeline]:
        p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [PA], {"streamer_id": "st1", "voice_mode": "clone"},
                                              v1_live_warmstart=flag)
        prof = await store.insert("voice_profiles", {"display_name": "me", "consent_at": CONSENT, "ref_path": "ref.wav",
                                                     "ref_text": "yeh meri awaaz hai dosto", "embedding": None})
        sess.row["voice_profile_id"] = prof["id"]
        monkeypatch.setattr("app.live.pipeline.get_gpu_voice", lambda *a: gpu)
        monkeypatch.setattr("app.live.pipeline.get_stt", lambda *a: SilentSTT())
        prefetch_stored_voice(sess)
        await asyncio.sleep(0.05)
        return gpu, sess, p

    gpu, sess, p = await run(False)
    assert sess.prefetch is None and gpu.refs == []                # flag off: nothing before the start
    await p.start()
    assert len(gpu.refs) == 1 and p.gpu_ready and p._gpu_stored
    await p.stop()

    gpu, sess, p = await run(True)
    assert len(gpu.refs) == 1 and sess.prefetch is not None        # on its way before any sound
    await p.start()
    assert len(gpu.refs) == 1 and p.gpu_ready and p._gpu_stored and "stored_voice_ahead" in p.warm_ms
    await p.stop()

    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [PA], {"streamer_id": "st1", "voice_mode": "clone"},
                                          v1_live_warmstart=True)
    prof = await store.insert("voice_profiles", {"display_name": "x", "consent_at": None, "ref_path": "ref.wav",
                                                 "ref_text": "yeh meri awaaz hai dosto", "embedding": None})
    sess.row["voice_profile_id"] = prof["id"]
    monkeypatch.setattr("app.live.pipeline.get_gpu_voice", lambda *a: gpu)
    monkeypatch.setattr("app.live.pipeline.get_stt", lambda *a: SilentSTT())
    prefetch_stored_voice(sess)
    await p.start()
    assert gpu.refs == [] and not p.gpu_ready                      # no consent on record: nothing is sent, ahead or not
    await p.stop()


async def english(monkeypatch, tmp_path, setting: str, copy_at_start: bool, **more):
    row = {"engine": "gpu"} if copy_at_start else {"engine": "gpu", "voice_from_stream": {"consent_at": CONSENT}}
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [EN, PA], row, v1_en_single_voice=True,
                                          v1_en_voice=setting, **more)
    if copy_at_start:
        sess.row["voice_profile_id"] = await profile_with_copy(store)
    qs = {EN: sess.bus.subscribe(EN)}
    await p.start()
    p.set_media(0.0, True)
    return p, sess, tts, qs


def en_voices(tts: RecTTS) -> list[str]:
    return [name for lang, name, _ in tts.said if lang == EN]


async def test_one_english_voice_the_copy_for_every_line_also_one_with_no_time_to_spare(monkeypatch, tmp_path):
    p, sess, tts, qs = await english(monkeypatch, tmp_path, "copy", True)
    assert p._en_mode == "copy" and p.warm_stats() == {"en_voice": "copy", "en_lines_asked_again": 0, "en_lines_then_spoken": 0}
    await say(p, qs, ago_ms=5000)           # 1 s before it is due: v0 would take a stock voice here
    await say(p, qs, ago_ms=4500)
    await say(p, qs)
    assert en_voices(tts) == ["clone", "clone", "clone"]
    await p.stop()


async def test_one_english_voice_the_stock_voice_for_every_line_also_one_with_time_for_the_copy(monkeypatch, tmp_path):
    p, sess, tts, qs = await english(monkeypatch, tmp_path, "stock", True)
    assert p._en_mode == "stock"
    await say(p, qs, ago_ms=5000)
    await say(p, qs)                        # 6 s before it is due: v0 would take the copy here
    assert en_voices(tts) == [VOICE_BY_LANG[EN]] * 2
    await p.stop()


async def test_auto_keeps_the_one_stock_voice_with_a_copy_from_the_start_and_with_one_learned_later(monkeypatch, tmp_path):
    p, sess, tts, qs = await english(monkeypatch, tmp_path, "auto", True)
    assert p._en_mode == "stock"
    await say(p, qs)                        # 6 s before it is due and the copy is there: the stock voice all the same
    assert en_voices(tts) == [VOICE_BY_LANG[EN]]
    await p.stop()
    p, sess, tts, qs = await english(monkeypatch, tmp_path, "auto", False)
    assert p._en_mode == "stock" and p._copy_coming
    await say(p, qs)
    p.voice, p._copy_coming = {"kind": "clone", "embedding": EMB}, False      # the copy has been learned meanwhile
    await say(p, qs)
    assert en_voices(tts) == [VOICE_BY_LANG[EN]] * 2                             # and the session keeps its one voice
    await p.stop()


async def test_copy_asked_for_on_a_voice_still_to_be_learned_opens_in_stock_and_changes_once(monkeypatch, tmp_path):
    p, sess, tts, qs = await english(monkeypatch, tmp_path, "copy", False, v1_en_copy_lead_ms=5500)
    t0 = sess.now_ms()
    await say(p, qs)                        # waits 0.5 s for the copy (until 5.5 s before it is due), then a stock voice
    assert sess.now_ms() - t0 >= 450 and en_voices(tts) == [VOICE_BY_LANG[EN]]
    p.voice, p._copy_coming = {"kind": "clone", "embedding": EMB}, False
    await say(p, qs, ago_ms=3000)           # little time to spare: the copy all the same
    await say(p, qs)
    assert en_voices(tts) == [VOICE_BY_LANG[EN], "clone", "clone"]
    await p.stop()


async def test_with_the_ladder_a_copy_that_stops_answering_steps_english_down_to_stock_and_comes_back(monkeypatch, tmp_path):
    p, sess, tts, qs = await english(monkeypatch, tmp_path, "copy", True, v1_live_degrade=True, v1_degrade_probe_ms=600000)
    await say(p, qs)
    assert en_voices(tts) == ["clone"] and p.rung()[0] == 0
    tts.dead = {"clone"}
    await say(p, qs)                        # the copy fails, also when asked once more: the stock voice says this line (the ladder's rule)
    await say(p, qs)                        # two lines in a row: the copy is down
    assert en_voices(tts)[1:] == ["clone", "clone", VOICE_BY_LANG[EN]] * 2 and p.rung()[0] == 1
    tts.said.clear()
    p._playhead.clear()                     # (the test speaks faster than a viewer listens)
    await say(p, qs)                        # down: the copy is asked once more (the probe), the stock voice says the line
    await say(p, qs)                        # ... and from then on the stock voice is asked directly
    await say(p, qs)
    assert en_voices(tts) == ["clone", "clone", VOICE_BY_LANG[EN], VOICE_BY_LANG[EN], VOICE_BY_LANG[EN]]
    tts.dead, tts.said = set(), []
    p._ladder._tried.clear()                # the next probe is due
    p._playhead.clear()
    await say(p, qs)
    await say(p, qs)
    assert en_voices(tts) == ["clone", "clone"] and p.rung()[0] == 0
    await p.stop()


class RefusingTTS(RecTTS):
    """Refuses every line whose number is in `refuse` (counted from 0), as the hosted service does with a 502."""

    def __init__(self, refuse: set[int]) -> None:
        super().__init__()
        self.refuse, self.n = refuse, -1

    async def synth_stream(self, text, lang, voice, *, sample_rate=None, speed=1.0):
        self.n += 1
        if self.n in self.refuse:
            self.said.append((lang, "refused", text))
            raise ProviderError("tts.synth_stream: synthesis_error", status=502, retryable=True)
        async for chunk in super().synth_stream(text, lang, voice, sample_rate=sample_rate, speed=speed):
            yield chunk


async def test_an_english_line_the_hosted_voice_refuses_is_asked_once_more_in_the_same_voice(monkeypatch, tmp_path):
    p, sess, tts, qs = await english(monkeypatch, tmp_path, "stock", True)
    p.tts = tts = RefusingTTS({0, 2, 3})
    first = await say(p, qs, ago_ms=3000)       # refused once: the second try speaks it
    assert len(pcm_of(first[EN])) > 0 and en_voices(tts) == ["refused", VOICE_BY_LANG[EN]]
    second = await say(p, qs)                   # refused twice: this line has no audio, and nothing else is tried
    assert len(pcm_of(second[EN])) == 0 and en_voices(tts)[2:] == ["refused", "refused"]
    assert p.warm_stats() == {"en_voice": "stock", "en_lines_asked_again": 2, "en_lines_then_spoken": 1}
    await p.stop()
    t = await stored(store := LocalStore(tmp_path / "db.json"))
    assert [t[k].get("tts_retry:en-IN") for k in sorted(t)] == [1, 1] and store is not None


async def test_without_the_english_flag_a_refused_line_is_left_out_as_in_v0(monkeypatch, tmp_path):
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [EN], {"engine": "gpu"})
    p.tts = tts = RefusingTTS({0})
    qs = {EN: sess.bus.subscribe(EN)}
    await p.start()
    p.set_media(0.0, True)
    got = await say(p, qs, ago_ms=3000)
    assert len(pcm_of(got[EN])) == 0 and [name for _, name, _ in tts.said] == ["refused"]
    await p.stop()
    assert not [k for row in (await stored(store)).values() for k in row if k.startswith("tts_retry")]


async def test_the_english_flag_does_nothing_outside_a_gpu_engine_session_or_without_english(monkeypatch, tmp_path):
    p, *_ = setup(monkeypatch, tmp_path, [EN], {}, v1_en_single_voice=True)
    await p.start()
    assert p._en_mode is None and p.warm_stats() == {}
    await p.stop()
    p, *_ = setup(monkeypatch, tmp_path, [PA], {"engine": "gpu"}, v1_en_single_voice=True)
    await p.start()
    assert p._en_mode is None
    await p.stop()


@pytest.mark.parametrize("lang", sorted(VOICE_BY_LANG))
def test_every_language_has_a_stock_voice_for_either_speaker(lang):
    for gender in ("male", "female", None):
        assert warm.pick_stock(lang, gender)["voice"]
