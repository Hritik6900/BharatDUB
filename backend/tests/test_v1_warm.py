"""The one English voice of a session in manual mode (`V1_EN_SINGLE_VOICE`, `V1_EN_VOICE`). Auto mode: test_v1_auto.py.
The session-start tests of v1.1 went with `V1_LIVE_WARMSTART` in v1.2."""
import asyncio
import base64

import numpy as np

from app.config import VOICE_BY_LANG, Settings, get_settings
from app.db import LocalStore
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession
from app.providers.base import ProviderError
from app.providers.mock import MockLLM, MockTTS
from app.v1 import warm
from app.v1.flags import flags

TA, PA, EN = "ta-IN", "pa-IN", "en-IN"
CONSENT = "2026-11-24T00:00:00+00:00"
EMB = {"embedding": "e", "shape": [1, 768], "dtype": "torch.bfloat16"}
NEW_KEYS = ("open", "handover", "voice_fb", "unspoken", "script", "auto", "judged")


# ---------- the parts alone ----------
def test_english_voice_for_a_session_is_copy_or_stock_and_auto_is_the_measured_choice_stock():
    assert warm.en_mode("copy") == "copy" and warm.en_mode("stock") == "stock"
    assert warm.en_mode("auto") == "stock" and warm.en_mode("anything") == "stock"


def test_the_flag_exists_and_is_off_by_default_and_the_session_start_flag_is_gone():
    fresh = Settings(_env_file=None)
    assert fresh.v1_en_single_voice is False and fresh.v1_en_voice == "auto"
    assert not hasattr(fresh, "v1_live_warmstart") and "V1_LIVE_WARMSTART" not in flags()
    assert flags()["V1_EN_SINGLE_VOICE"] is False


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
    """v0's warm-up runs (first language only, no hosted line when our engine is coming), the stock voice is the
    language's usual one, English is chosen line by line, nothing new is stored or sent."""
    p, sess, llm, tts, gpu, store = setup(monkeypatch, tmp_path, [TA, PA], {"voice_from_stream": {"consent_at": CONSENT}},
                                          live_warmup=True)
    assert p._en_mode is None and p.warm_stats() == {} and p._meaning is None and not p._fallback
    qs = {lg: sess.bus.subscribe(lg) for lg in (TA, PA)}
    await p.start()
    await asyncio.sleep(0.4)
    assert [(text, lang) for text, lang, _ in llm.asked] == [("नमस्ते", TA)] and tts.said == [] and gpu.healths == 0
    await say(p, qs)
    assert {(lang, name) for lang, name, _ in tts.said} == {(TA, VOICE_BY_LANG[TA]), (PA, VOICE_BY_LANG[PA])}
    await p.stop()
    assert not [k for row in (await stored(store)).values() for k in row if k.split(":")[0] in NEW_KEYS]


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
    w = p.warm_stats()
    assert p._en_mode == "copy" and (w["en_voice"], w["en_lines_asked_again"], w["en_lines_then_spoken"]) == ("copy", 0, 0)
    assert w["en_voice_choice"]["why"] == "setting V1_EN_VOICE=copy" and sess.row["en_voice"]["voice"] == "copy"
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
    w = p.warm_stats()
    assert (w["en_voice"], w["en_lines_asked_again"], w["en_lines_then_spoken"]) == ("stock", 2, 1)
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


