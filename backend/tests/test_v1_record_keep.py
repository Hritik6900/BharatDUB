"""Kept Live recordings: deleted by themselves after `V1_RECORD_KEEP_DAYS`, deletable one by one, listed."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import get_settings
from app.v1 import record

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "v1_record_dir", str(tmp_path / "rec"))
    monkeypatch.setattr(s, "v1_record_keep_days", 30)
    return tmp_path / "rec"


def make(root, sid: str, *, ended_days_ago: float | None = None, started_days_ago: float | None = None, langs=("ta-IN",)):
    """A recording as the Recorder leaves it: session.json, one track per language, phrases.jsonl."""
    d = root / sid
    d.mkdir(parents=True)
    meta = {"session": sid, "langs": list(langs), "sample_rate": 8000, "engine": "gpu", "rows": 2}
    if started_days_ago is not None:
        meta["started_at"] = (NOW - timedelta(days=started_days_ago)).isoformat(timespec="seconds")
    if ended_days_ago is not None:
        meta["ended_at"] = (NOW - timedelta(days=ended_days_ago)).isoformat(timespec="seconds")
    (d / "session.json").write_text(json.dumps(meta), encoding="utf-8")
    for lg in langs:
        (d / f"dub_{lg}.wav").write_bytes(b"RIFF" + b"\x00" * 100)
    (d / "phrases.jsonl").write_text('{"seq": 1}\n', encoding="utf-8")
    return d


def test_the_default_is_thirty_days_and_recording_stays_opt_in():
    fields = type(get_settings()).model_fields
    assert fields["v1_record_keep_days"].default == 30 and fields["v1_live_record"].default is False


def test_a_recording_older_than_the_limit_is_deleted_and_a_younger_one_stays(root):
    old = make(root, "old-one", started_days_ago=31.1, ended_days_ago=31)
    edge = make(root, "edge", started_days_ago=30.2, ended_days_ago=29.9)     # began 30 days ago, ended inside them
    new = make(root, "new-one", ended_days_ago=1)
    assert record.sweep(now=NOW) == ["old-one"]
    assert not old.exists() and edge.exists() and new.exists()
    assert record.sweep(now=NOW) == []                                         # nothing left to do
    assert sorted(record.sweep(now=NOW + timedelta(days=30))) == ["edge", "new-one"]   # both gone 30 days on
    assert not edge.exists() and not new.exists() and root.exists()


def test_a_recording_that_never_got_its_end_is_aged_from_its_start_or_its_files(root):
    crashed = make(root, "crashed", started_days_ago=45)                       # the backend died while recording
    bare = make(root, "bare")
    (bare / "session.json").write_text("not json", encoding="utf-8")
    stamp = (NOW - timedelta(days=40)).timestamp()
    for f in bare.iterdir():
        os.utime(f, (stamp, stamp))
    fresh = make(root, "fresh")
    (fresh / "session.json").unlink()                                          # no file about it at all, written just now
    assert sorted(record.sweep(now=NOW)) == ["bare", "crashed"]
    assert fresh.exists()


def test_zero_days_means_never_by_itself_and_another_number_is_that_number(root, monkeypatch):
    make(root, "old-one", ended_days_ago=400)
    monkeypatch.setattr(get_settings(), "v1_record_keep_days", 0)
    assert record.sweep(now=NOW) == [] and (root / "old-one").exists()
    assert record.listing()[0]["deleted_after"] is None
    make(root, "week", ended_days_ago=8)
    make(root, "days", ended_days_ago=6)
    monkeypatch.setattr(get_settings(), "v1_record_keep_days", 7)
    assert sorted(record.sweep(now=NOW)) == ["old-one", "week"] and (root / "days").exists()


def test_a_session_being_recorded_now_and_anything_that_is_not_a_recording_are_left_alone(root):
    make(root, "live-one", started_days_ago=31)                                # a very long session, still open
    (root / "notes.txt").write_text("x", encoding="utf-8")
    odd = root / "has space"
    odd.mkdir()
    assert record.sweep(now=NOW, skip={"live-one"}) == []
    assert (root / "live-one").exists() and (root / "notes.txt").exists() and odd.exists()


def test_no_folder_no_error_and_nothing_is_created(root):
    assert record.sweep(now=NOW) == [] and record.listing() == [] and not root.exists()
    assert record.delete("nothing") is False and not root.exists()


def test_the_sweep_runs_with_the_flag_off(root):
    assert get_settings().v1_live_record is False                              # what was kept earlier must still go
    make(root, "old-one", ended_days_ago=31)
    assert record.sweep(now=NOW) == ["old-one"]


async def test_the_backend_sweeps_at_start_and_in_its_half_hourly_round(root, monkeypatch):
    make(root, "old-one", ended_days_ago=90)
    make(root, "new-one", ended_days_ago=0)
    assert await main.sweep_old_recordings() == 1
    assert not (root / "old-one").exists() and (root / "new-one").exists()
    make(root, "older", ended_days_ago=90)
    with TestClient(main.app):                                                 # the app's start runs the sweeper's first round
        pass
    assert not (root / "older").exists() and (root / "new-one").exists()


def test_list_and_delete_over_the_api(root):
    make(root, "s-old", started_days_ago=10.01, ended_days_ago=10, langs=("ta-IN", "pa-IN"))
    make(root, "s-new", ended_days_ago=1)
    c = TestClient(main.app)
    got = c.get("/api/v1/recordings").json()
    assert got["keep_days"] == 30 and got["recording_allowed"] is False
    assert [r["session"] for r in got["recordings"]] == ["s-new", "s-old"]     # newest first
    row = got["recordings"][1]
    assert row["langs"] == ["ta-IN", "pa-IN"] and row["files"] == 4 and row["bytes"] > 200 and row["phrases"] == 2
    ended = datetime.fromisoformat(row["ended_at"])
    assert datetime.fromisoformat(row["deleted_after"]) == ended + timedelta(days=30)
    assert "text" not in json.dumps(got)                                       # names, sizes and dates only
    assert c.delete("/api/v1/recordings/s-old").json() == {"deleted": True}
    assert not (root / "s-old").exists() and (root / "s-new").exists()
    assert c.delete("/api/v1/recordings/s-old").status_code == 404             # already gone
    assert [r["session"] for r in c.get("/api/v1/recordings").json()["recordings"]] == ["s-new"]


def test_delete_takes_a_recording_name_and_never_a_path(root, tmp_path):
    make(root, "keep-me", ended_days_ago=1)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f.txt").write_text("x", encoding="utf-8")
    c = TestClient(main.app)
    for bad in ("..", "%2e%2e", "..%2Foutside", "keep-me%2F..", "a b", "x" * 65):
        assert c.delete(f"/api/v1/recordings/{bad}").status_code in (404, 405), bad
    assert record.delete("../outside") is False and record.delete("") is False and record.delete("..") is False
    assert (outside / "f.txt").exists() and (root / "keep-me").exists()


def test_a_session_that_is_still_recording_cannot_be_deleted(root, monkeypatch):
    make(root, "busy", ended_days_ago=None, started_days_ago=0)
    monkeypatch.setattr(record, "_open_now", lambda: {"busy"})
    c = TestClient(main.app)
    assert c.delete("/api/v1/recordings/busy").status_code == 409 and (root / "busy").exists()
    monkeypatch.setattr(record, "_open_now", lambda: set())
    assert c.delete("/api/v1/recordings/busy").status_code == 200 and not (root / "busy").exists()


async def test_deleting_a_voice_profile_leaves_recordings_alone(root, tmp_path, monkeypatch):
    """What the code does today, written down: a recording does not say whose voice it holds (session.json has no
    voice or streamer id), and deleting a voice touches the sample and the embedding only."""
    from app.db import LocalStore
    from app.shared import voices
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr(voices, "get_store", lambda: store)
    v = await store.insert("voice_profiles", {"display_name": "x", "consent_at": "2026-11-01T00:00:00+00:00", "embedding": {"e": 1}})
    d = make(root, "spoken-in-that-voice", ended_days_ago=1)
    assert "voice" not in json.loads((d / "session.json").read_text(encoding="utf-8"))
    assert await voices.delete_voice(v["id"]) == {"deleted": True}
    assert d.exists() and (await store.get("voice_profiles", v["id"]))["embedding"] is None
