"""The viewers' hold coming back down after it grew (`LIVE_SYNC_EASE`, app/v1/hold.py)."""
from collections import deque

from app.db import LocalStore
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession
from app.providers.mock import MockLLM, MockTTS
from app.v1.hold import Ease
from tests.test_live import SilentSTT

EARLY = -3000     # a phrase whose sound was ready 3 s before its moment


def run(e: Ease, hold: int, t: int, until: int, late: int = EARLY, every: int = 1000) -> tuple[int, int]:
    """A phrase every `every` ms, each `late` ms after its moment; returns the hold and the clock at the end."""
    while t < until:
        t += every
        e.note(late, t)
        hold = e.next(hold, t)
    return hold, t


def test_nothing_moves_at_the_normal_value():
    e = Ease(6000)
    assert run(e, 6000, 0, 120_000) == (6000, 120_000) and e.steps == []


def test_waits_for_a_calm_spell_then_goes_down_in_small_steps_to_the_normal_value_and_stops():
    e = Ease(6000, step_ms=250, every_ms=5000, calm_ms=20000)
    e.trouble(0)                                         # the hold has just grown to 8 s
    hold, t = run(e, 8000, 0, 19_000)
    assert hold == 8000                                  # 19 s without a late phrase: not yet
    hold, t = run(e, hold, t, 20_000)
    assert hold == 7750                                  # first step after 20 s
    hold, t = run(e, hold, t, 24_000)
    assert hold == 7750                                  # the next one not before 5 s later
    hold, t = run(e, hold, t, 25_000)
    assert hold == 7500
    hold, t = run(e, hold, t, 300_000)
    assert hold == 6000                                  # all the way back, and never under it
    assert [h for _, h in e.steps] == [7750, 7500, 7250, 7000, 6750, 6500, 6250, 6000]
    assert all(b - a >= 5000 for (a, _), (b, _) in zip(e.steps, e.steps[1:]))


def test_the_last_step_ends_on_the_normal_value_not_under_it():
    e = Ease(6000, step_ms=400, every_ms=0, calm_ms=0, min_phrases=1)
    hold, _ = run(e, 6500, 0, 10_000)
    assert hold == 6000 and [h for _, h in e.steps] == [6100, 6000]


def test_a_late_phrase_stops_it_and_the_wait_starts_again():
    e = Ease(6000)
    e.trouble(0)
    hold, t = run(e, 9000, 0, 30_000)
    assert hold == 8250                                  # steps at 20, 25 and 30 s
    e.note(300, t + 500)                                 # one phrase after its moment
    hold, t = run(e, hold, t + 500, t + 19_500)
    assert hold == 8250                                  # nothing for the next 20 s
    hold, t = run(e, hold, t, t + 2000)
    assert hold == 8000


def test_a_phrase_without_enough_in_hand_counts_as_late():
    e = Ease(6000, step_ms=250, spare_ms=500)
    e.trouble(0)
    hold, _ = run(e, 8000, 0, 120_000, late=-700)        # ready 0.7 s early: one step less would leave 0.45 s
    assert hold == 8000 and e.steps == []
    e2 = Ease(6000, step_ms=250, spare_ms=500)
    assert run(e2, 8000, 0, 21_000, late=-750)[0] == 7750   # 0.75 s early is enough


def test_no_phrases_no_step():
    e = Ease(6000)
    e.trouble(0)
    assert e.next(8000, 500_000) == 8000                 # silence since the trouble: no evidence
    hold, t = run(e, 8000, 500_000, 503_000)
    assert hold == 7750                                  # three phrases in time, long after the trouble
    assert e.next(hold, t + 60_000) == 7750              # and no further step without another phrase


def test_one_phrase_in_several_languages_counts_once():
    e = Ease(6000, calm_ms=0, every_ms=0)
    e.trouble(0)
    for _ in range(5):
        e.note(EARLY, 100, key=7)
    assert e.next(8000, 100) == 8000                     # one phrase, however many languages
    e.note(EARLY, 200, key=8)
    e.note(EARLY, 300, key=9)
    assert e.next(8000, 300) == 7750
    e.note(EARLY, 400, key=10)
    e.note(200, 400, key=10)                             # the same phrase late in another language
    assert e.next(7750, 400) == 7750


def pipeline(tmp_path, monkeypatch, **settings):
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: LocalStore(tmp_path / "db.json"))
    sess = LiveSession({"id": "h1", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS())
    if settings:
        p.s = p.s.model_copy(update=settings)
    clock = [0]
    sess.now_ms = lambda: clock[0]
    p.running = True
    p.set_media(5.0, True)
    return p, clock


def stall(p, clock) -> None:
    """Phrases keep arriving after their moment until the hold has grown by 3 s."""
    base = p._sync_delay
    while p._sync_delay < base + 3000:
        clock[0] += 1000
        p._media.append((clock[0], 5.0 + clock[0] / 1000, True))
        p._note_late(2500)


def calm(p, clock, seconds: int, late: int = EARLY) -> None:
    for _ in range(seconds):
        clock[0] += 1000
        p._media.append((clock[0], 5.0 + clock[0] / 1000, True))   # the console keeps reporting
        p._note_late(late)


async def test_the_hold_of_a_session_grows_in_a_stall_and_eases_back_to_normal(tmp_path, monkeypatch):
    p, clock = pipeline(tmp_path, monkeypatch)
    base = p.sync_delay()
    assert base == p.s.live_sync_delay_ms and p.s.live_sync_ease is True
    stall(p, clock)
    assert p.sync_delay() == base + 3000 and len(p.sync_grown) == 3
    seen = [p.sync_delay()]
    for _ in range(120):
        calm(p, clock, 1)
        seen.append(p.sync_delay())
    assert seen[19] == base + 3000                       # nothing for the first 19 s
    assert all(0 <= a - b <= p.s.live_sync_ease_step_ms for a, b in zip(seen, seen[1:]))   # only down, a small step at a time
    assert seen[-1] == base and min(seen) == base        # back at the normal value, never under it
    p._late["ta-IN"] = deque([0])                        # the numbers a session reports need one spoken phrase
    assert p.stats()["sync_eased"] == 12 and p.stats()["sync_grown"] == 3
    sent = []
    p.sess.bus.broadcast = sent.append
    p.set_media(200.0, True)
    assert sent[-1]["type"] == "sync" and sent[-1]["delay_ms"] == base    # what viewers are told


async def test_the_hold_does_not_ease_while_phrases_are_late_and_grows_again_when_they_are(tmp_path, monkeypatch):
    p, clock = pipeline(tmp_path, monkeypatch)
    base = p.sync_delay()
    stall(p, clock)
    calm(p, clock, 60, late=200)                         # just after their moment: not late enough to grow the hold
    assert p.sync_delay() == base + 3000                 # ... and not early enough to give any of it back
    calm(p, clock, 30)
    assert p.sync_delay() == base + 3000 - 3 * p.s.live_sync_ease_step_ms
    eased = p.sync_delay()
    calm(p, clock, 3, late=2500)                         # the link stalls again
    assert p.sync_delay() == eased + p.s.live_sync_grow_step_ms
    calm(p, clock, 19)
    assert p.sync_delay() == eased + p.s.live_sync_grow_step_ms   # the wait started again


async def test_kill_switch_off_the_hold_only_grows(tmp_path, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "live_sync_ease", False)
    p, clock = pipeline(tmp_path, monkeypatch)
    base = p.sync_delay()
    stall(p, clock)
    calm(p, clock, 300)
    assert p._ease is None and p.sync_delay() == base + 3000 and "sync_eased" not in p.stats()


async def test_a_streamers_youtube_offset_is_never_eased(tmp_path, monkeypatch):
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: LocalStore(tmp_path / "db.json"))
    sess = LiveSession({"id": "h2", "target_langs": ["ta-IN"], "src_lang": "hi-IN", "streamer_id": "s1", "offset_ms": 8000})
    p = LivePipeline(sess, stt=SilentSTT(), llm=MockLLM(), tts=MockTTS())
    p.running = True
    for _ in range(200):
        p._note_late(EARLY)
    assert p.sync_delay() == 8000 and p._ease is None
