"""Shared HTTP plumbing: timeouts, one retry (plus 429 backoff), and the Gnani concurrency gate.

Gnani accounts may allow only 1 active request at a time (429 RATE_LIMITED, no Retry-After),
so every Gnani REST call goes through `gnani_gate()`.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from app.providers.base import ProviderError

log = logging.getLogger("providers")

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
MAX_429_RETRIES = 4

_gate: asyncio.Semaphore | None = None
_gate_size = 0


def gnani_gate(size: int) -> asyncio.Semaphore:
    global _gate, _gate_size
    if _gate is None or _gate_size != size:
        _gate, _gate_size = asyncio.Semaphore(max(1, size)), size
    return _gate


def describe_error(resp: httpx.Response) -> str:
    """Short, key-free summary of an error body."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300]
    if isinstance(body, dict):
        err = body.get("error") or body.get("detail") or body
        if isinstance(err, dict):
            return str(err.get("message") or err.get("type") or err.get("error_code") or err)[:300]
        return str(err)[:300]
    return str(body)[:300]


async def request_with_retry(
    send: Callable[[], Awaitable[httpx.Response]],
    *,
    what: str,
    retries: int = 1,
    backoff_s: float = 0.6,
) -> httpx.Response:
    """Run `send` with one retry on transient errors; 429 gets extra backed-off attempts."""
    attempt, rate_limited = 0, 0
    while True:
        try:
            resp = await send()
        except (httpx.TimeoutException, httpx.TransportError) as e:
            if attempt >= retries:
                raise ProviderError(f"{what}: {type(e).__name__}", retryable=True) from e
            attempt += 1
            await asyncio.sleep(backoff_s * attempt)
            continue
        if resp.status_code < 400:
            return resp
        msg = f"{what}: HTTP {resp.status_code} {describe_error(resp)}"
        if resp.status_code == 429 and rate_limited < MAX_429_RETRIES:
            rate_limited += 1
            log.warning("%s rate limited, backing off (%d)", what, rate_limited)
            await asyncio.sleep(backoff_s * 2 ** rate_limited)
            continue
        if resp.status_code in RETRYABLE_STATUS and attempt < retries:
            attempt += 1
            await asyncio.sleep(backoff_s * attempt)
            continue
        raise ProviderError(msg, status=resp.status_code, retryable=resp.status_code in RETRYABLE_STATUS)
