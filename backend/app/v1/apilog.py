"""API call log (`V1_API_LOG`): one record per outbound request to a provider, with its measurements.

Every REST call a provider makes goes through `providers.http.request_with_retry`; with the flag on, each attempt
is appended to `<log dir>/api/<YYYY-MM-DD>/<test>.jsonl`, where <test> is the Live session or Studio job the call
was made for (`live_<id>`, `job_<id>`) or `other`. The log dir is `V1_LOG_DIR`, by default `logs/` at the top of
the repository.

A record holds what was called and how it went, never what was said: no request or reply body, no header, no
query string, so no key and no text can end up in it.

  ts          when the answer (or the failure) arrived, UTC
  test        the session or job
  api         the provider call, as the code names it (llm.chat, gpu_voice.tts, tts.synth, stt.transcribe ...)
  method, host, path
  status      HTTP status; null when no answer came
  ms          from sending the request to having the answer
  attempt     0 for the first try, 1 and up for retries (a 429 back-off counts)
  bytes_out, bytes_in
  ok          status under 400
  error       the kind of failure when no answer came (ReadTimeout, ConnectError ...)

Not in this log: the realtime speech-to-text socket and streamed stock voice, which are one long connection and
not a call per line. Their timing per phrase is in the trace (`V1_TRACE`).
"""
import json
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import BACKEND_DIR, get_settings
from app.v1 import mode as v1mode

TEST: ContextVar[str] = ContextVar("v1_api_test", default="other")
_lock = threading.Lock()


def enabled() -> bool:
    return bool(v1mode.on("api_log", get_settings()))


def log_dir() -> Path:
    s = get_settings()
    return Path(s.v1_log_dir) if s.v1_log_dir else BACKEND_DIR.parent / "logs"


def set_test(kind: str, ident: str) -> None:
    """Name the session or job that the calls made from here on (this task and the tasks it starts) belong to."""
    TEST.set(f"{kind}_{str(ident)[:8]}")


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def record(what: str, resp: Any, t0: float, attempt: int, error: str = "") -> None:
    """Append one attempt. Never raises: a log must not break a stream or a job."""
    if not enabled():
        return
    try:
        now = datetime.now(timezone.utc)
        rec: dict[str, Any] = {"ts": now.isoformat(timespec="milliseconds"), "test": TEST.get(), "api": what,
                               "method": None, "host": None, "path": None, "status": None,
                               "ms": int((time.perf_counter() - t0) * 1000), "attempt": attempt,
                               "bytes_out": None, "bytes_in": None, "ok": False, "error": error or None}
        if resp is not None:
            req = resp.request
            host = req.url.host + (f":{req.url.port}" if req.url.port else "")
            size_in = _int(resp.headers.get("content-length"))
            if size_in is None:
                try:
                    size_in = len(resp.content)
                except Exception:  # noqa: BLE001  a streamed reply that was not read
                    size_in = None
            rec.update(method=req.method, host=host, path=req.url.path, status=resp.status_code,
                       bytes_out=_int(req.headers.get("content-length")), bytes_in=size_in,
                       ok=resp.status_code < 400)
        folder = log_dir() / "api" / f"{now:%Y-%m-%d}"
        with _lock:
            folder.mkdir(parents=True, exist_ok=True)
            with open(folder / f"{rec['test']}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=True) + "\n")
    except Exception:  # noqa: BLE001
        pass
