"""Viewer chat: any language in, translated into the streamer's language, out to console + OBS overlay."""
import asyncio
from collections import defaultdict, deque
from typing import Any

from app.config import DEFAULT_GLOSSARY
from app.db import get_store, now_iso
from app.providers import get_llm

MAX_LEN = 200
STREAMER_LANG = "hi-IN"


class ChatHub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self.history: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=50))

    def subscribe(self, sid: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subs[sid].add(q)
        return q

    def unsubscribe(self, sid: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs[sid].discard(q)

    async def post(self, sid: str, viewer_lang: str, text: str, name: str = "") -> dict[str, Any]:
        text = " ".join(text.split())[:MAX_LEN]
        translated = text
        if viewer_lang != STREAMER_LANG:
            try:
                translated = await asyncio.wait_for(
                    get_llm().translate_chunk(text, STREAMER_LANG, DEFAULT_GLOSSARY, []), 8)
            except Exception:  # noqa: BLE001 - show the original rather than drop the message
                translated = text
        row = await get_store().insert("chat_messages", {"session_id": sid, "viewer_lang": viewer_lang,
                                                         "text": text, "translated_text": translated})
        msg = {"type": "chat", "id": row.get("id"), "viewer_lang": viewer_lang, "name": name[:24],
               "text": text, "translated": translated, "at": row.get("created_at") or now_iso()}
        self.history[sid].append(msg)
        for q in list(self._subs.get(sid, ())):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass
        return msg


chat = ChatHub()
