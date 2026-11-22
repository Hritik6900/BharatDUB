"""The Postgres store against a real database, and the waiting-jobs queue.

The store test runs only when `TEST_POSTGRES_DSN` points at a database that may be written to (it uses and then
removes rows of its own tables' names prefixed `t_`): there was none on the machine this was written on, so it
has not run yet. It does the same things to the JSON store and expects the same answers.

  TEST_POSTGRES_DSN=postgresql://bharatdb:<password>@127.0.0.1:5440/bharatdb python -m pytest tests/test_v1_store.py -q
"""
import os

import pytest

from app.db import LocalStore
from app.v1.queue import JobQueue

DSN = os.environ.get("TEST_POSTGRES_DSN", "")


async def exercise(store) -> dict:
    """The calls the app makes, in one go; returns what they gave back."""
    job = await store.insert("jobs", {"source_path": "a.mp4", "target_langs": ["ta-IN"]})
    segs = await store.insert_many("segments", [{"job_id": job["id"], "idx": i, "src_text": f"line {i}"} for i in range(3)])
    tr = await store.insert("translations", {"segment_id": segs[1]["id"], "lang": "ta-IN", "text": "x"})
    chunk = await store.insert("live_chunks", {"session_id": "s", "seq": 1, "timings": {}})
    updated = await store.update("translations", tr["id"], {"text": "y", "edited": True})
    out = {
        "job_defaults": (job["status"], job["stage_timings"], "created_at" in job),
        "translation_default": tr["edited"], "updated": (updated["text"], updated["edited"]),
        "chunk_id_is_int": isinstance(chunk["id"], int),
        "get": (await store.get("segments", segs[2]["id"]))["src_text"],
        "missing": await store.get("segments", "no-such-id"),
        "select_order": [s["idx"] for s in await store.select("segments", order="idx", desc=True, job_id=job["id"])],
        "select_limit": len(await store.select("segments", limit=2, job_id=job["id"])),
        "select_in": sorted(s["idx"] for s in await store.select_in("segments", "id", [segs[0]["id"], segs[2]["id"]])),
        "select_in_eq": len(await store.select_in("translations", "segment_id", [s["id"] for s in segs], lang="bn-IN")),
        "update_missing": await store.update("jobs", "no-such-id", {"status": "done"}),
    }
    out["deleted"] = await store.delete("jobs", id=job["id"])
    out["cascade"] = (len(await store.select("segments", job_id=job["id"])), await store.get("translations", tr["id"]))
    await store.delete("live_chunks", session_id="s")
    return out


EXPECTED = {
    "job_defaults": ("queued", {}, True), "translation_default": False, "updated": ("y", True),
    "chunk_id_is_int": True, "get": "line 2", "missing": None, "select_order": [2, 1, 0], "select_limit": 2,
    "select_in": [0, 2], "select_in_eq": 0, "update_missing": None, "deleted": 1, "cascade": (0, None),
}


async def test_json_store_baseline(tmp_path):
    assert await exercise(LocalStore(tmp_path / "db.json")) == EXPECTED


@pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_DSN is not set")
async def test_postgres_store_gives_the_same_answers():
    from app.v1.store_pg import PostgresStore
    assert await exercise(PostgresStore(DSN)) == EXPECTED


async def test_queue_without_redis_keeps_jobs_in_order():
    q = JobQueue("test", url="")
    for j in ("a", "b", "a", "c"):
        await q.push(j)
    assert await q.size() == 3
    assert await q.take_all() == ["a", "b", "c"]
    assert await q.take_all() == [] and await q.size() == 0


async def test_queue_falls_back_when_redis_is_down():
    q = JobQueue("test", url="redis://127.0.0.1:1/0")     # nothing listens there
    await q.push("a")
    assert await q.take_all() == ["a"]
