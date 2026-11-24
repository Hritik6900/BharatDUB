"""v1 Live phrase logic: dynamic phrase sizes, short lines joined to the next."""
import asyncio

import pytest

from app.config import get_settings
from app.live.assembler import Chunk, Phraser
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession
from app.providers.base import TranscriptEvent
from app.providers.mock import MockTTS
from app.v1.phrase import DynamicPhraser, ShortLineMerger, n_words, same_words

WORDS = "aaj hum ek naya game khelne wale hain aur ye bahut mazedaar hoga doston kyunki isme naye map aaye hain".split()


def grow(phraser: Phraser, words: list[str], uid: str = "u") -> list[str]:
    """Feed the utterance one word at a time, as settled text, and collect the phrases that come out."""
    out = []
    for i in range(1, len(words) + 1):
        text = " ".join(words[:i])
        cut = phraser.partial(uid, text, text, now_ms=1000 + 300 * i)
        if cut:
            out.append(cut[0])
    return out


def test_first_phrase_is_short_and_later_ones_are_long():
    got = grow(DynamicPhraser((4, 6), (8, 12)), WORDS)
    assert 4 <= len(got[0].split()) <= 6                      # early first audio
    assert all(8 <= len(p.split()) <= 12 for p in got[1:])    # then lines the voice speaks well
    v0 = grow(Phraser(6, 12), WORDS)
    assert len(got[0].split()) < len(v0[0].split())           # v0 waits for six words before its first phrase


def test_first_phrase_is_only_the_first_of_the_session():
    p = DynamicPhraser((4, 6), (8, 12))
    first = grow(p, WORDS[:7], uid="a")
    assert len(first) == 1 and p.given == 1
    p.reset()                                                 # a reconnect of the recogniser: still not "first"
    assert grow(p, WORDS[:7], uid="b") == []                  # seven words are not enough for a later phrase


def chunk(seq: int, text: str, start: int = 0, end: int = 0) -> Chunk:
    return Chunk(seq, text, start, end or start + 500, end or start + 600)


def test_short_line_waits_and_joins_the_next_line():
    m = ShortLineMerger(under_words=3, wait_ms=1500)
    assert m.push(chunk(1, "Kaise?", 1000), now_ms=1100) == []          # held
    assert m.poll(2000) is None                                          # still waiting
    out = m.push(chunk(2, "aaj hum naya game khelenge", 2200, 4000), now_ms=4100)
    assert len(out) == 1 and out[0].text == "Kaise? aaj hum naya game khelenge"
    assert out[0].seq == 2 and out[0].t_speech_ms == 1000 and out[0].t_speech_end_ms == 4000
    assert m.merged == 1 and m.held is None


def test_short_line_goes_out_alone_when_nothing_follows():
    m = ShortLineMerger(under_words=3, wait_ms=1500)
    m.push(chunk(1, "Batao.", 0), now_ms=100)
    assert m.poll(1500) is None
    alone = m.poll(1600)
    assert alone is not None and alone.text == "Batao." and m.alone == 1
    assert m.poll(5000) is None


def test_long_lines_pass_straight_through_and_two_short_ones_join():
    m = ShortLineMerger(under_words=3)
    assert [c.text for c in m.push(chunk(1, "ye teen shabd"), 0)] == ["ye teen shabd"]
    assert m.push(chunk(2, "haan"), 0) == []
    out = m.push(chunk(3, "theek hai"), 10)                              # joined: never held a second time
    assert [c.text for c in out] == ["haan theek hai"]
    assert n_words("hai? ...") == 1


def test_same_words_ignores_case_and_punctuation():
    assert same_words("Aaj hum khelenge.", "aaj hum khelenge")
    assert not same_words("aaj hum khelenge", "aaj hum nahi khelenge")


# ---------- in the pipeline ----------
class CountingLLM:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def translate_chunk(self, text, target, glossary, context, **kw):
        self.calls.append((target, text))
        await asyncio.sleep(0.01)
        return f"{target}:{text}"

    async def shorten(self, text, target, max_seconds, max_words=None):
        return " ".join(text.split()[:max_words or 3])


class NoSTT:
    async def stream(self, frames, lang, **kw):
        async for _ in frames:
            if False:
                yield None


def pipeline(monkeypatch, **flags) -> tuple[LivePipeline, CountingLLM, asyncio.Queue]:
    s = get_settings()
    for k, v in flags.items():
        monkeypatch.setattr(s, k, v)
    sess = LiveSession({"id": "v1s", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    llm = CountingLLM()
    p = LivePipeline(sess, stt=NoSTT(), llm=llm, tts=MockTTS())
    p.running = True
    return p, llm, sess.bus.subscribe("ta-IN")


async def captions(q: asyncio.Queue, wait: float = 0.1) -> list[str]:
    await asyncio.sleep(wait)
    out = []
    while not q.empty():
        m = q.get_nowait()
        if m.get("type") == "caption":
            out.append(m["text"])
    return out


async def test_pipeline_joins_a_one_word_line_to_the_next(monkeypatch):
    p, llm, q = pipeline(monkeypatch, v1_phrase_dynamic=True)
    p._on_stt(TranscriptEvent(kind="final", text="Kaise?", utterance_id="a", audio_duration_ms=400))
    assert await captions(q) == [] and llm.calls == []                   # held, nothing translated yet
    p._on_stt(TranscriptEvent(kind="final", text="aaj hum naya game khelenge.", utterance_id="b", audio_duration_ms=2000))
    assert await captions(q) == ["ta-IN:Kaise? aaj hum naya game khelenge."]
    assert p._merger.merged == 1


async def test_pipeline_without_the_flag_sends_the_short_line_alone(monkeypatch):
    p, llm, q = pipeline(monkeypatch, v1_phrase_dynamic=False)
    assert p._merger is None and type(p.phraser) is Phraser
    p._on_stt(TranscriptEvent(kind="final", text="Kaise?", utterance_id="a", audio_duration_ms=400))
    assert await captions(q) == ["ta-IN:Kaise?"]


async def test_late_line_is_shortened_not_skipped(monkeypatch):
    p, llm, q = pipeline(monkeypatch, v1_live_late_shorten=True)
    text = "ஒன்று இரண்டு மூன்று நான்கு ஐந்து ஆறு ஏழு எட்டு ஒன்பது பத்து"
    assert await p._shorter("ta-IN", text, late_by=5000, limit=4000) == "ஒன்று இரண்டு மூன்று நான்கு"
    assert await p._shorter("ta-IN", text, late_by=9000, limit=4000) is None    # far too late: skipped as before
    assert await p._shorter("ta-IN", "மூன்று சொற்கள் மட்டும்", late_by=5000, limit=4000) is None   # nothing to shorten


def test_stock_default_and_session_glossary(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.db import LocalStore
    from app.main import app
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.routes.get_store", lambda: store)
    monkeypatch.setattr("app.live.session.get_store", lambda: store)
    s = get_settings()
    c = TestClient(app)
    body = {"target_langs": ["ta-IN"], "voice_from_stream": True, "voice_consent": True, "glossary": ["Valorant", " ", "Ace"]}
    r = c.post("/api/live/sessions", json=body)
    assert r.status_code == 201 and r.json()["voice_from_stream"] is True       # flag off: as v0
    row = store._db["live_sessions"][-1]
    assert row["glossary"] == ["Valorant", "Ace"]
    monkeypatch.setattr(s, "v1_live_stock_default", True)
    r = c.post("/api/live/sessions", json=body)
    assert r.status_code == 201 and r.json()["voice_from_stream"] is False      # no streamer profile: stock voices
    assert c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "voice_from_stream": True}).status_code == 201


@pytest.mark.parametrize("flag", ["v1_phrase_dynamic"])
def test_flags_default_off(flag):
    assert getattr(get_settings(), flag) is False


def test_removed_flags_are_gone_and_an_env_file_that_still_sets_them_is_read(tmp_path):
    """v1.1 WS6 took V1_SPEC_TRANSLATE and V1_LLM_PREFIX_CACHE out. An env file written before that must still load."""
    from app.config import Settings
    from app.v1.flags import FLAGS, flags
    env = tmp_path / ".env"
    env.write_text("\n".join(["V1_SPEC_TRANSLATE=true", "V1_SPEC_STABLE_MS=250", "V1_LLM_PREFIX_CACHE=true",
                              "V1_PHRASE_DYNAMIC=false", ""]))
    s = Settings(_env_file=env)
    for name in ("v1_spec_translate", "v1_spec_stable_ms", "v1_llm_prefix_cache"):
        assert not hasattr(s, name) and name not in FLAGS
    assert "V1_SPEC_TRANSLATE" not in flags(s) and "V1_LLM_PREFIX_CACHE" not in flags(s)
    assert not any(flags(s)[k] for k in flags(s) if k != "V1_STORE")      # the unknown names switch nothing on
