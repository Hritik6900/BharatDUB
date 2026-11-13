"""Per-session, per-language pub/sub for watch sockets. Keeps a short caption history for late joiners."""
import asyncio
from collections import defaultdict, deque
from typing import Any

ALL = "*"


class Bus:
    def __init__(self, history: int = 20) -> None:
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self.history: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=history))

    def subscribe(self, lang: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=2000)
        self._subs[lang].add(q)
        return q

    def unsubscribe(self, lang: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs[lang].discard(q)

    def publish(self, lang: str, msg: dict[str, Any], *, to_all: bool = True) -> None:
        if msg.get("type") in ("caption", "source"):
            self.history[lang].append(msg)
        targets = set(self._subs.get(lang, ()))
        if to_all and lang != ALL:
            targets |= self._subs.get(ALL, set())
        for q in targets:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:  # slow viewer: drop rather than block the pipeline
                pass

    def broadcast(self, msg: dict[str, Any]) -> None:
        for subs in list(self._subs.values()):
            for q in list(subs):
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    pass

    def listeners(self, lang: str) -> int:
        """Viewers tuned to this language (the console's `*` feed does not play audio)."""
        return len(self._subs.get(lang, ()))

    def viewer_count(self) -> int:
        return sum(len(s) for k, s in self._subs.items() if k != ALL)
