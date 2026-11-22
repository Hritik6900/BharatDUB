"""v1 Live phrase logic: dynamic phrase sizes, short lines joined to the next, translation started ahead."""
import asyncio

import pytest

from app.config import get_settings
from app.live.assembler import Chunk, Phraser
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession
from app.providers.base import TranscriptEvent
from app.providers.mock import MockTTS
from app.v1.phrase import DynamicPhraser, ShortLineMerger, SpecTracker, n_words, rest_of, same_words

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
    assert rest_of(p, "b", " ".join(WORDS[:7])) == " ".join(WORDS[:7])


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


def test_spec_starts_only_after_the_words_stood_still():
    s = SpecTracker(stable_ms=300)
    assert s.observe("aaj hum", 1000) is False             # first sight
    assert s.observe("aaj hum khelenge", 1300) is False    # changed: the clock starts again
    assert s.observe("aaj hum khelenge", 1600) is False    # partials come 300 ms apart: 300 ms still is ordinary
    assert s.wait_ms() == 450                              # a gap and a half
    assert s.due(1700) is False
    assert s.due(1760) is True                             # the speaker paused: no new partial for 460 ms
    s.begin({"ta-IN": DummyTask()})
    assert s.due(2500) is False                            # already running
    assert s.observe("ok", 2600) is False and s.tasks is None and s.dropped == 1   # the words moved on: dropped


def test_spec_needs_two_words_and_fires_between_partials():
    s = SpecTracker(stable_ms=300)
    s.observe("haan", 0)
    assert s.due(5000) is False                            # one word is not worth a call
    s.observe("haan bilkul", 5100)
    assert s.due(5300) is False and s.due(5400) is True    # no partial needed to notice the pause


class DummyTask:
    def __init__(self):
        self.cancelled_ = False

    def cancel(self):
        self.cancelled_ = True


def test_spec_is_used_for_the_same_words_and_dropped_for_others():
    s = SpecTracker(stable_ms=0, min_words=1)
    s.observe("aaj hum khelenge", 0)
    assert s.observe("aaj hum khelenge", 10)
    t = DummyTask()
    s.begin({"ta-IN": t})
    assert s.take("Aaj hum khelenge.") == {"ta-IN": t} and s.used == 1 and not t.cancelled_
    s.observe("phir milte hain", 20)
    s.observe("phir milte hain", 30)
    t2 = DummyTask()
    s.begin({"ta-IN": t2})
    assert s.take("phir milenge") is None and t2.cancelled_ and s.dropped == 1
    assert s.take("anything") is None                      # nothing running: nothing to use


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


async def test_pipeline_uses_the_translation_started_ahead(monkeypatch):
    p, llm, q = pipeline(monkeypatch, v1_spec_translate=True, v1_spec_stable_ms=50)
    for _ in range(3):   # the same words in three partials, 60 ms apart: they stand still
        p._on_stt(TranscriptEvent(kind="partial", text="aaj hum khelenge", stable_text="", utterance_id="a"))
        await asyncio.sleep(0.06)
    assert llm.calls == [("ta-IN", "aaj hum khelenge")] and p._spec.started == 1    # translated ahead, once
    p._on_stt(TranscriptEvent(kind="final", text="Aaj hum khelenge.", utterance_id="a", audio_duration_ms=900))
    assert await captions(q) == ["ta-IN:aaj hum khelenge"]                           # the early translation is the caption
    assert len(llm.calls) == 1 and p._spec.used == 1                                 # no second call


async def test_pipeline_translates_again_when_the_final_differs(monkeypatch):
    p, llm, q = pipeline(monkeypatch, v1_spec_translate=True, v1_spec_stable_ms=50)
    for _ in range(3):
        p._on_stt(TranscriptEvent(kind="partial", text="aaj hum khelenge", stable_text="", utterance_id="a"))
        await asyncio.sleep(0.06)
    p._on_stt(TranscriptEvent(kind="final", text="Aaj hum nahi khelenge.", utterance_id="a", audio_duration_ms=900))
    assert await captions(q) == ["ta-IN:Aaj hum nahi khelenge."]                     # the final's own words
    assert p._spec.dropped == 1 and llm.calls[-1] == ("ta-IN", "Aaj hum nahi khelenge.")


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


@pytest.mark.parametrize("flag", ["v1_phrase_dynamic", "v1_spec_translate"])
def test_flags_default_off(flag):
    assert getattr(get_settings(), flag) is False
