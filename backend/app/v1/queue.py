"""A small job queue: Redis when `REDIS_URL` is set (it survives a restart of the backend and is shared by more
than one backend process), else a list inside this process. Used for HQ Studio jobs that wait for a batch run."""
from typing import Any

from app.config import get_settings


class JobQueue:
    def __init__(self, name: str, url: str | None = None) -> None:
        self.key = f"bharatdb:v1:{name}"
        self.url = get_settings().redis_url if url is None else url
        self._local: list[str] = []
        self._redis: Any = None

    def _r(self) -> Any:
        if self._redis is None:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.url, decode_responses=True, socket_timeout=3, socket_connect_timeout=3)
        return self._redis

    async def push(self, job_id: str) -> None:
        if self.url:
            try:
                await self._r().rpush(self.key, job_id)
                return
            except Exception:  # noqa: BLE001 - Redis is down: the job still waits, in this process
                pass
        if job_id not in self._local:
            self._local.append(job_id)

    async def take_all(self) -> list[str]:
        """Every waiting job, oldest first; the queue is empty afterwards."""
        out: list[str] = []
        if self.url:
            try:
                r = self._r()
                async with r.pipeline(transaction=True) as p:
                    p.lrange(self.key, 0, -1)
                    p.delete(self.key)
                    out = list((await p.execute())[0])
            except Exception:  # noqa: BLE001
                out = []
        out += [j for j in self._local if j not in out]
        self._local = []
        return list(dict.fromkeys(out))

    async def size(self) -> int:
        n = len(self._local)
        if self.url:
            try:
                n += int(await self._r().llen(self.key))
            except Exception:  # noqa: BLE001
                pass
        return n
