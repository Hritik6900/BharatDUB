"""Postgres store for `V1_STORE=postgres`: the same methods as `LocalStore`, rows kept as JSON documents.

One table for everything (`v1_rows`: table name, id, document), so the shapes stay those of the JSON store and
nothing else in the code changes. Not run against a real server when it was written (no database on the build
machine): see docs/v1/NEEDS_APPROVAL.md before switching it on.
"""
import asyncio
import json
import uuid
from typing import Any

from app.db import Row, now_iso

INT_ID_TABLES = ("live_chunks", "chat_messages")
SCHEMA = """
create table if not exists v1_rows (
  n bigserial unique,
  tbl text not null,
  id text not null,
  data jsonb not null,
  primary key (tbl, id)
);
create index if not exists v1_rows_data on v1_rows using gin (data jsonb_path_ops);
"""


def _defaults(table: str, row: Row) -> Row:
    """The same defaults the JSON store gives a new row."""
    row = dict(row)
    if table in ("jobs", "renders", "live_sessions", "chat_messages", "voice_profiles", "streamers"):
        row.setdefault("created_at", now_iso())
    if table == "jobs":
        row.setdefault("status", "queued")
        row.setdefault("stage_timings", {})
        row.setdefault("credits_used", 0)
    if table == "translations":
        row.setdefault("edited", False)
    return row


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: Any = None
        self._lock = asyncio.Lock()

    async def _c(self) -> Any:
        if self._conn is None or self._conn.closed:
            import psycopg
            self._conn = await psycopg.AsyncConnection.connect(self._dsn, autocommit=True)
            await self._conn.execute(SCHEMA)
        return self._conn

    async def _run(self, sql: str, args: tuple[Any, ...] = (), fetch: bool = True) -> list[tuple[Any, ...]]:
        async with self._lock:
            cur = await (await self._c()).execute(sql, args)
            return list(await cur.fetchall()) if fetch and cur.description else []

    @staticmethod
    def _key(id: Any) -> str:
        return str(id)

    async def insert(self, table: str, row: Row) -> Row:
        return (await self.insert_many(table, [row]))[0]

    async def insert_many(self, table: str, rows: list[Row]) -> list[Row]:
        out: list[Row] = []
        for r in rows:
            r = _defaults(table, r)
            if table in INT_ID_TABLES and "id" not in r:
                got = await self._run("select nextval(pg_get_serial_sequence('v1_rows','n'))")
                r["id"] = int(got[0][0])
            r.setdefault("id", str(uuid.uuid4()))
            await self._run("insert into v1_rows (tbl, id, data) values (%s, %s, %s::jsonb)",
                            (table, self._key(r["id"]), json.dumps(r, ensure_ascii=False)), fetch=False)
            out.append(r)
        return out

    async def get(self, table: str, id: Any) -> Row | None:
        got = await self._run("select data from v1_rows where tbl = %s and id = %s", (table, self._key(id)))
        return dict(got[0][0]) if got else None

    async def update(self, table: str, id: Any, fields: Row) -> Row | None:
        got = await self._run("update v1_rows set data = data || %s::jsonb where tbl = %s and id = %s returning data",
                              (json.dumps(fields, ensure_ascii=False), table, self._key(id)))
        return dict(got[0][0]) if got else None

    async def select(self, table: str, *, order: str | None = None, desc: bool = False,
                     limit: int | None = None, **eq: Any) -> list[Row]:
        got = await self._run("select data from v1_rows where tbl = %s and data @> %s::jsonb order by n",
                              (table, json.dumps(eq, ensure_ascii=False)))
        rows = [dict(g[0]) for g in got]
        if order:
            rows.sort(key=lambda r: (r.get(order) is None, r.get(order)), reverse=desc)
        return rows[:limit] if limit else rows

    async def select_in(self, table: str, column: str, values: list[Any], **eq: Any) -> list[Row]:
        if not values:
            return []
        got = await self._run(
            "select data from v1_rows where tbl = %s and data @> %s::jsonb and data ->> %s = any(%s) order by n",
            (table, json.dumps(eq, ensure_ascii=False), column, [str(v) for v in values]))
        return [dict(g[0]) for g in got]

    async def delete(self, table: str, **eq: Any) -> int:
        got = await self._run("delete from v1_rows where tbl = %s and data @> %s::jsonb returning id",
                              (table, json.dumps(eq, ensure_ascii=False)))
        if got and table == "jobs":      # the same cascade as the JSON store
            await self._run("delete from v1_rows s where s.tbl in ('segments','renders') and not exists "
                            "(select 1 from v1_rows j where j.tbl = 'jobs' and j.id = s.data ->> 'job_id')", fetch=False)
        if got and table in ("jobs", "segments"):
            await self._run("delete from v1_rows t where t.tbl = 'translations' and not exists "
                            "(select 1 from v1_rows s where s.tbl = 'segments' and s.id = t.data ->> 'segment_id')",
                            fetch=False)
        return len(got)
