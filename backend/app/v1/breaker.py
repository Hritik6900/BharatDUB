"""Circuit breakers for our GPU endpoints, and the link-stall detector (`V1_BREAKER`).

The laptop reaches the GPU machine through a tunnel, and that link stalls (24 Nov 2026: every GPU service
unreachable at once for 2 min, 44 min and 3 h). Without a breaker every phrase waits for the dead endpoint's
timeout before the next provider is asked. With one:

  closed     calls go through. A call that times out, or two failed calls within `v1_breaker_window_s` (10 s),
             open the circuit.
  open       for `v1_breaker_open_s` (30 s) the endpoint is not called at all: the caller gets `CircuitOpen` at
             once and its usual fallback answers (hosted translation, hosted speech-to-text, a hosted voice).
  half-open  after that, one try is let through. It answers: closed. It fails: open for another 30 s.
             While the detector below is running the try is its health probe, and calls stay refused until it
             has answered: no phrase of a live session is spent on testing a dead endpoint. A probe costs
             nothing, so after a failed one the detector simply probes again on its next round (5 s) instead of
             waiting another 30 s: the endpoint is back in use within seconds of the link returning.
             Without the detector (a Studio job with no session live) the first call is the try.

One breaker per endpoint (provider name + host:port), shared by every provider object that calls it.

`LinkWatch` asks every GPU endpoint for its health every few seconds while a Live session runs. When all of them
fail in the same round it is the link, not a model: every circuit is opened at once, so no phrase pays a timeout to
find out.

With the flag off no breaker is attached and the providers run the code they always ran.
"""
import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from urllib.parse import urlsplit

import httpx

from app.config import Settings, get_settings
from app.providers.base import ProviderError
from app.v1 import mode as v1mode

log = logging.getLogger("bharatdub.breaker")
T = TypeVar("T")
PROBE_STUCK_S = 20.0     # a half-open probe that never came back (its caller was cancelled) frees its turn
GPU_PROVIDERS = ("whisper_gpu", "gemma", "big_llm", "indicf5", "indicf5_v1", "maya", "mio")   # ours; hosted ones get none
REF_TIMEOUT_FACTOR = 3   # sending a voice sample may take this many times a line's limit

EVENTS: deque[dict[str, Any]] = deque(maxlen=300)   # opens and closes, newest last; `id` only grows
_next_id = 0
_breakers: dict[str, "Breaker"] = {}


class CircuitOpen(ProviderError):
    """The endpoint is not being called right now; the caller's fallback answers."""


def _event(name: str, event: str, **fields: Any) -> None:
    global _next_id
    _next_id += 1
    rec = {"id": _next_id, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "name": name, "event": event, **fields}
    EVENTS.append(rec)
    (log.info if event == "close" else log.warning)("circuit %s: %s %s", event, name, fields or "")
    from app.v1 import trace
    if trace.enabled():
        trace.event("circuit", name=name, event=event, **fields)


class Breaker:
    def __init__(self, name: str, *, fails: int = 2, window_s: float = 10.0, open_s: float = 30.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.name, self.fails, self.window_s, self.open_s, self.clock = name, max(1, fails), window_s, open_s, clock
        self._failed: deque[float] = deque(maxlen=self.fails)
        self._opened_at: float | None = None     # not None = open or half-open
        self._down_since: float | None = None    # when it first opened, across failed retries
        self._probe_at: float | None = None      # a half-open probe is under way since then
        self.opens = 0                           # times it opened (retries that failed not counted)
        self.retries = 0                         # half-open probes that failed
        self.watched = False                     # the detector is running: it does the half-open try, calls do not
        self.last_reason = ""

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        return "half_open" if self.clock() - self._opened_at >= self.open_s else "open"

    def blocked(self) -> bool:
        """A call would be refused now. Does not take the half-open turn."""
        st = self.state
        if st == "closed":
            return False
        if st == "open" or self.watched:
            return True
        return self._probing()

    def _probing(self) -> bool:
        return self._probe_at is not None and self.clock() - self._probe_at < PROBE_STUCK_S

    def probe_turn(self) -> bool:
        """The detector asks for the half-open try. True = it has it, and must report `ok()` or `fail()`."""
        if self.state != "half_open" or self._probing():
            return False
        self._probe_at = self.clock()
        return True

    def allow(self) -> bool:
        """May this call go out? In half-open the first caller gets the one turn."""
        if self.blocked():
            return False
        if self._opened_at is not None:
            self._probe_at = self.clock()
        return True

    def release(self) -> None:
        """The call ended without a verdict (cancelled): give the half-open turn back."""
        self._probe_at = None

    def ok(self) -> None:
        self._failed.clear()
        self._probe_at = None
        if self._opened_at is None:
            return
        down = self.clock() - (self._down_since or self._opened_at)
        self._opened_at = self._down_since = None
        _event(self.name, "close", down_s=round(down, 1), retries=self.retries)
        self.retries = 0

    def fail(self, reason: str = "", *, timed_out: bool = False) -> None:
        now = self.clock()
        self.last_reason = reason[:160]
        if self._opened_at is not None:
            if self.state == "half_open":         # the retry failed
                self._probe_at = None
                self.retries += 1
                if not self.watched:              # a call was spent on it: open for another full turn, quietly
                    self._opened_at = now
                    _event(self.name, "reopen", reason=self.last_reason, retries=self.retries)
            return
        self._failed.append(now)
        enough = len(self._failed) >= self.fails and now - self._failed[0] <= self.window_s
        if timed_out or enough:
            self.trip(reason or "failed")

    def trip(self, reason: str) -> None:
        """Open now, whatever the count (a timeout, or the detector saw the whole link go)."""
        if self._opened_at is not None:
            return
        self._opened_at = self._down_since = self.clock()
        self._probe_at = None
        self._failed.clear()
        self.opens += 1
        self.last_reason = reason[:160]
        _event(self.name, "open", reason=self.last_reason, open_s=self.open_s)

    def snapshot(self) -> dict[str, Any]:
        st = self.state
        out: dict[str, Any] = {"name": self.name, "state": st, "opens": self.opens}
        if st != "closed":
            out["down_s"] = round(self.clock() - (self._down_since or self._opened_at or 0.0), 1)
            out["reason"] = self.last_reason
        return out


# ---------- the registry ----------
def enabled(settings: Settings | None = None) -> bool:
    return bool(v1mode.on("breaker", settings or get_settings()))


def name_for(provider: str, url: str) -> str:
    """`gemma 127.0.0.1:9020`: what the endpoint is and where."""
    return f"{provider} {urlsplit(url).netloc or url}"


def get(name: str) -> Breaker:
    if name not in _breakers:
        s = get_settings()
        _breakers[name] = Breaker(name, fails=s.v1_breaker_fails, window_s=s.v1_breaker_window_s,
                                  open_s=s.v1_breaker_open_s)
    return _breakers[name]


def attach(provider: str, obj: Any) -> Any:
    """Give a GPU provider object its breaker(s). With the flag off the object is returned untouched."""
    if not enabled() or obj is None or provider not in GPU_PROVIDERS:
        return obj
    if hasattr(obj, "urls") and hasattr(obj, "breakers"):          # a voice engine client: one breaker per engine
        obj.breakers = [get(name_for(provider, u)) for u in obj.urls]
    elif hasattr(obj, "breaker") and getattr(obj, "url", ""):      # our speech-to-text
        obj.breaker = get(name_for(provider, obj.url))
    elif hasattr(obj, "breaker") and getattr(getattr(obj, "s", None), "llm_base_url", ""):   # our translation model
        obj.breaker = get(name_for(provider, obj.s.llm_base_url))
    return obj


def snapshot() -> list[dict[str, Any]]:
    return [b.snapshot() for b in _breakers.values()]


def events(after: int = 0) -> list[dict[str, Any]]:
    return [e for e in EVENTS if e["id"] > after]


def last_id() -> int:
    """The id of the newest event; ids start again at 1 when the backend restarts."""
    return _next_id


def reset() -> None:
    """Tests only."""
    global _next_id
    _breakers.clear()
    EVENTS.clear()
    _next_id = 0


# ---------- running a call through a breaker ----------
def verdict(e: BaseException) -> str:
    """What a failed call says about the endpoint: `timeout`, `fail`, or `answered` (it is there; the request
    was the problem, e.g. HTTP 400 or 403)."""
    if isinstance(e, TimeoutError) or "Timeout" in type(e).__name__ or "Timeout" in str(e):
        return "timeout"
    if isinstance(e, ProviderError):
        return "answered" if e.status is not None and e.status < 500 and e.status not in (408, 429) else "fail"
    if isinstance(e, (httpx.HTTPError, OSError)):
        return "fail"
    return "answered"


async def call(br: Breaker | None, send: Callable[[], Awaitable[T]], timeout: float | None = None) -> T:
    """Run `send` through `br`. Without a breaker this is `await send()` and nothing else."""
    if br is None:
        return await send()
    if not br.allow():
        raise CircuitOpen(f"{br.name}: circuit open ({br.last_reason or 'not answering'})", retryable=True)
    try:
        out = await (asyncio.wait_for(send(), timeout) if timeout else send())
    except asyncio.CancelledError:
        br.release()
        raise
    except Exception as e:  # noqa: BLE001 - judged, then passed on
        kind = verdict(e)
        if kind == "answered":
            br.ok()
            raise
        br.fail(f"{type(e).__name__}: {str(e)[:100]}" if str(e) else type(e).__name__, timed_out=kind == "timeout")
        if isinstance(e, TimeoutError) and not isinstance(e, ProviderError):
            raise ProviderError(f"{br.name}: no answer in {timeout:g} s", retryable=True) from e
        raise
    br.ok()
    return out


# ---------- the link-stall detector ----------
def targets(s: Settings | None = None) -> list[tuple[str, str]]:
    """(breaker name, health address) of every GPU endpoint this backend calls for a Live phrase."""
    s = s or get_settings()
    out: list[tuple[str, str]] = []
    for u in [u.strip().rstrip("/") for u in s.gpu_voice_url.split(",") if u.strip()]:
        out.append((name_for("indicf5", u), u + "/health"))
    for provider, url, path in (("whisper_gpu", s.gpu_stt_url, "/health"), ("gemma", s.gpu_llm_url, "/models"),
                                ("mio", s.gpu_mio_url, "/health"),
                                ("indicf5_v1", s.v1_tts_server_url if v1mode.on("tts_server", s) else "", "/health")):
        if url:
            out.append((name_for(provider, url), url.rstrip("/") + path))
    return out


class LinkWatch:
    def __init__(self, probe: Callable[[str], Awaitable[str]] | None = None,
                 targets_: list[tuple[str, str]] | None = None, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self.targets = targets(self.s) if targets_ is None else targets_
        self._probe = probe or self._http
        self._client: httpx.AsyncClient | None = None
        self.stalled_since: float | None = None
        self.users = 0
        self._task: asyncio.Task[None] | None = None

    async def _http(self, url: str) -> str:
        """`` = answers, else why not (`timeout` or the error's name)."""
        if self._client is None:
            self._client = httpx.AsyncClient()
        try:
            await self._client.get(url, timeout=httpx.Timeout(self.s.v1_link_probe_timeout_s))
            return ""      # any HTTP answer: the endpoint is reachable
        except httpx.TimeoutException:
            return "timeout"
        except httpx.HTTPError as e:
            return type(e).__name__

    async def round(self) -> dict[str, str]:
        """One look at every endpoint; opens, closes and the link verdict follow from it."""
        probing = {name: get(name).probe_turn() for name, _ in self.targets}
        got = await asyncio.gather(*(self._probe(url) for _, url in self.targets))
        res = {name: why for (name, _), why in zip(self.targets, got)}
        down = [n for n, why in res.items() if why]
        if len(res) >= 2 and len(down) == len(res):
            if self.stalled_since is None:
                self.stalled_since = time.monotonic()
                _event("link", "link_stall", services=len(down), reason=", ".join(sorted(set(res.values()))))
            for name in down:       # the link, not a model: nobody else should pay a timeout to learn it
                get(name).trip(f"link stall ({res[name]})")
        elif self.stalled_since is not None and len(down) < len(res):
            _event("link", "link_back", down_s=round(time.monotonic() - self.stalled_since, 1),
                   answering=len(res) - len(down), services=len(res))
            self.stalled_since = None
        for name, why in res.items():
            br = get(name)
            if not why:
                if probing[name]:
                    br.ok()
            elif probing[name] or br.state == "closed":
                br.fail(f"health: {why}", timed_out=why == "timeout")
        return res

    async def _loop(self) -> None:
        while True:
            try:
                await self.round()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - a detector never takes anything down
                log.warning("link watch: %s", e)
            await asyncio.sleep(self.s.v1_link_probe_every_s)

    def start(self) -> None:
        self.users += 1
        if self._task is None and self.targets:
            self._task = asyncio.create_task(self._loop())
            self._watched(True)

    def stop(self) -> None:
        self.users = max(0, self.users - 1)
        if self.users == 0 and self._task is not None:
            self._task.cancel()
            self._task = None
            self._watched(False)     # nobody probes any more: the next call is the half-open try again

    def _watched(self, on: bool) -> None:
        for name, _ in self.targets:
            get(name).watched = on


_watch: LinkWatch | None = None


def watch() -> LinkWatch:
    global _watch
    if _watch is None:
        _watch = LinkWatch()
    return _watch
