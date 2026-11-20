"""Persistence. SupabaseStore when SUPABASE_* is set, else LocalStore (a JSON file, for dev and tests).

Both expose the same async methods over the tables in supabase/migrations/0001_init.sql.
"""
import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app.config import get_settings

Row = dict[str, Any]
TABLES = ("jobs", "segments", "translations", "renders", "voice_profiles", "glossary_terms",
          "live_sessions", "live_chunks", "chat_messages", "streamers")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store(Protocol):
    async def insert(self, table: str, row: Row) -> Row: ...
    async def insert_many(self, table: str, rows: list[Row]) -> list[Row]: ...
    async def get(self, table: str, id: Any) -> Row | None: ...
    async def update(self, table: str, id: Any, fields: Row) -> Row | None: ...
    async def select(self, table: str, *, order: str | None = None, desc: bool = False,
                     limit: int | None = None, **eq: Any) -> list[Row]: ...
    async def select_in(self, table: str, column: str, values: list[Any], **eq: Any) -> list[Row]: ...
    async def delete(self, table: str, **eq: Any) -> int: ...


class LocalStore:
    """Single-process JSON store. Good enough for one machine; not for concurrency across processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._db: dict[str, list[Row]] = {t: [] for t in TABLES}
        if path.exists():
            self._db.update(json.loads(path.read_text(encoding="utf-8")))
        self._seq = max((r.get("id", 0) for r in self._db["live_chunks"] + self._db["chat_messages"]
                         if isinstance(r.get("id"), int)), default=0)

    def _flush(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._db, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def _new_id(self, table: str) -> Any:
        if table in ("live_chunks", "chat_messages"):
            self._seq += 1
            return self._seq
        return str(uuid.uuid4())

    def _defaults(self, table: str, row: Row) -> Row:
        row = dict(row)
        row.setdefault("id", self._new_id(table))
        if table in ("jobs", "renders", "live_sessions", "chat_messages", "voice_profiles", "streamers"):
            row.setdefault("created_at", now_iso())
        if table == "jobs":
            row.setdefault("status", "queued")
            row.setdefault("stage_timings", {})
            row.setdefault("credits_used", 0)
        if table == "translations":
            row.setdefault("edited", False)
        return row

    @staticmethod
    def _match(row: Row, eq: Row) -> bool:
        return all(row.get(k) == v for k, v in eq.items())

    async def insert(self, table: str, row: Row) -> Row:
        return (await self.insert_many(table, [row]))[0]

    async def insert_many(self, table: str, rows: list[Row]) -> list[Row]:
        with self._lock:
            out = [self._defaults(table, r) for r in rows]
            self._db[table].extend(out)
            self._flush()
            return [dict(r) for r in out]

    async def get(self, table: str, id: Any) -> Row | None:
        with self._lock:
            return next((dict(r) for r in self._db[table] if r["id"] == id), None)

    async def update(self, table: str, id: Any, fields: Row) -> Row | None:
        with self._lock:
            for r in self._db[table]:
                if r["id"] == id:
                    r.update(fields)
                    self._flush()
                    return dict(r)
            return None

    async def select(self, table: str, *, order: str | None = None, desc: bool = False,
                     limit: int | None = None, **eq: Any) -> list[Row]:
        with self._lock:
            rows = [dict(r) for r in self._db[table] if self._match(r, eq)]
        if order:
            rows.sort(key=lambda r: (r.get(order) is None, r.get(order)), reverse=desc)
        return rows[:limit] if limit else rows

    async def select_in(self, table: str, column: str, values: list[Any], **eq: Any) -> list[Row]:
        vals = set(values)
        with self._lock:
            return [dict(r) for r in self._db[table] if r.get(column) in vals and self._match(r, eq)]

    async def delete(self, table: str, **eq: Any) -> int:
        with self._lock:
            before = len(self._db[table])
            self._db[table] = [r for r in self._db[table] if not self._match(r, eq)]
            n = before - len(self._db[table])
            if n:
                self._cascade(table)
                self._flush()
            return n

    def _cascade(self, table: str) -> None:
        if table == "jobs":
            ids = {r["id"] for r in self._db["jobs"]}
            self._db["segments"] = [r for r in self._db["segments"] if r["job_id"] in ids]
            self._db["renders"] = [r for r in self._db["renders"] if r["job_id"] in ids]
        if table in ("jobs", "segments"):
            seg_ids = {r["id"] for r in self._db["segments"]}
            self._db["translations"] = [r for r in self._db["translations"] if r["segment_id"] in seg_ids]


class SupabaseStore:
    def __init__(self) -> None:
        from supabase import create_client

        s = get_settings()
        self.client = create_client(s.supabase_url, s.supabase_service_key.get_secret_value())

    async def _run(self, fn: Any) -> Any:
        return await asyncio.to_thread(fn)

    async def insert(self, table: str, row: Row) -> Row:
        return (await self.insert_many(table, [row]))[0]

    async def insert_many(self, table: str, rows: list[Row]) -> list[Row]:
        if not rows:
            return []
        res = await self._run(lambda: self.client.table(table).insert(rows).execute())
        return res.data

    async def get(self, table: str, id: Any) -> Row | None:
        res = await self._run(lambda: self.client.table(table).select("*").eq("id", id).limit(1).execute())
        return res.data[0] if res.data else None

    async def update(self, table: str, id: Any, fields: Row) -> Row | None:
        res = await self._run(lambda: self.client.table(table).update(fields).eq("id", id).execute())
        return res.data[0] if res.data else None

    async def select(self, table: str, *, order: str | None = None, desc: bool = False,
                     limit: int | None = None, **eq: Any) -> list[Row]:
        def q() -> Any:
            b = self.client.table(table).select("*")
            for k, v in eq.items():
                b = b.eq(k, v)
            if order:
                b = b.order(order, desc=desc)
            if limit:
                b = b.limit(limit)
            return b.execute()
        return (await self._run(q)).data

    async def select_in(self, table: str, column: str, values: list[Any], **eq: Any) -> list[Row]:
        if not values:
            return []

        def q() -> Any:
            b = self.client.table(table).select("*").in_(column, values)
            for k, v in eq.items():
                b = b.eq(k, v)
            return b.execute()
        return (await self._run(q)).data

    async def delete(self, table: str, **eq: Any) -> int:
        def q() -> Any:
            b = self.client.table(table).delete()
            for k, v in eq.items():
                b = b.eq(k, v)
            return b.execute()
        return len((await self._run(q)).data or [])


@lru_cache
def get_store() -> Store:
    s = get_settings()
    if s.use_supabase:
        return SupabaseStore()
    return LocalStore(s.data_path / "local_db.json")
