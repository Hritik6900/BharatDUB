"""`GET /api/v1/health`: one answer for the status page. Green or red per v1 service and per shared GPU server,
plus the GPU's memory when it can be read. Every check runs at the same time with a short timeout, so one slow
server does not hold the page."""
import asyncio
import shutil
import time
from typing import Any

import httpx
from fastapi import APIRouter

from app.config import Settings, get_settings
from app.v1.flags import flags

router = APIRouter()
TIMEOUT_S = 3.0


async def _get(client: httpx.AsyncClient, name: str, kind: str, url: str, path: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    out: dict[str, Any] = {"name": name, "kind": kind, "url": url, "ok": False}
    try:
        r = await client.get(url.rstrip("/") + path, timeout=TIMEOUT_S)
        out["ok"] = r.status_code == 200
        if out["ok"] and r.headers.get("content-type", "").startswith("application/json"):
            body = r.json()
            if isinstance(body, dict):
                out["info"] = {k: v for k, v in body.items() if k in ("gpu_gb", "voices", "model", "nfe", "stub",
                                                                      "streams", "decode_ms_avg", "device")}
        if not out["ok"]:
            out["error"] = f"HTTP {r.status_code}"
    except (httpx.HTTPError, ValueError) as e:
        out["error"] = type(e).__name__
    out["ms"] = round((time.perf_counter() - t0) * 1000)
    return out


def servers(s: Settings) -> list[tuple[str, str, str, str]]:
    """(name, kind, url, health path) for every model server this backend is configured to call."""
    out: list[tuple[str, str, str, str]] = []
    for i, u in enumerate([u.strip() for u in s.gpu_voice_url.split(",") if u.strip()], 1):
        out.append((f"voice {i} (IndicF5)", "shared", u, "/health"))
    if s.gpu_separate_url:
        out.append(("separation (Demucs)", "shared", s.gpu_separate_url, "/health"))
    if s.gpu_llm_url:
        out.append(("translation (Gemma)", "shared", s.gpu_llm_url, "/models"))
    if s.gpu_stt_url:
        out.append(("speech-to-text (Whisper)", "shared", s.gpu_stt_url, "/health"))
    for name, url, path in (("voice server v1 (batching)", s.v1_tts_server_url, "/health"),
                            ("Maya 2", s.v1_maya_url, "/health"),
                            ("Indic Transcribe", s.v1_transcribe_url, "/health"),
                            ("big translation model", s.v1_big_llm_url, "/models"),
                            ("QA (back-check, similarity)", s.v1_qa_url, "/health")):
        if url:
            out.append((name, "v1", url, path))
    return out


async def gpu_memory() -> dict[str, Any] | None:
    """Used, free and total GPU memory in GB from `nvidia-smi` (read-only), when this machine has a GPU.
    The card's name is given with it: on a laptop this is the laptop's own card, not the model servers' one."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        p = await asyncio.create_subprocess_exec(
            exe, "--query-gpu=name,memory.used,memory.free,memory.total", "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        raw, _ = await asyncio.wait_for(p.communicate(), 4)
        name, *nums = [x.strip() for x in raw.decode().splitlines()[0].split(",")]
        used, free, total = (round(int(x) / 1024, 1) for x in nums)
        return {"name": name, "used_gb": used, "free_gb": free, "total_gb": total}
    except (OSError, ValueError, IndexError, TimeoutError):
        return None


async def _store_ok() -> dict[str, Any]:
    from app.db import get_store
    s = get_settings()
    out: dict[str, Any] = {"name": f"store ({s.v1_store})", "kind": "v1", "ok": False}
    t0 = time.perf_counter()
    try:
        await get_store().select("glossary_terms", limit=1)
        out["ok"] = True
    except Exception as e:  # noqa: BLE001 - a status page reports, it does not raise
        out["error"] = type(e).__name__
    out["ms"] = round((time.perf_counter() - t0) * 1000)
    return out


async def _redis_ok(url: str) -> dict[str, Any]:
    out: dict[str, Any] = {"name": "queue (Redis)", "kind": "v1", "ok": False}
    t0 = time.perf_counter()
    try:
        import redis.asyncio as redis
        r = redis.from_url(url, socket_timeout=TIMEOUT_S, socket_connect_timeout=TIMEOUT_S)
        out["ok"] = bool(await r.ping())
        await r.aclose()
    except Exception as e:  # noqa: BLE001
        out["error"] = type(e).__name__
    out["ms"] = round((time.perf_counter() - t0) * 1000)
    return out


async def _hosted(client: httpx.AsyncClient, name: str, url: str, configured: bool) -> dict[str, Any]:
    """Reachable = the service answers at all (any HTTP status); no key is sent and nothing is billed."""
    out: dict[str, Any] = {"name": name, "kind": "hosted", "ok": False, "configured": configured}
    if not configured or not url:
        out["error"] = "not configured"
        return out
    t0 = time.perf_counter()
    try:
        await client.get(url, timeout=TIMEOUT_S)
        out["ok"] = True
    except httpx.HTTPError as e:
        out["error"] = type(e).__name__
    out["ms"] = round((time.perf_counter() - t0) * 1000)
    return out


async def report() -> dict[str, Any]:
    s = get_settings()
    async with httpx.AsyncClient() as client:
        jobs: list[Any] = [_get(client, *row) for row in servers(s)]
        jobs.append(_store_ok())
        if s.redis_url:
            jobs.append(_redis_ok(s.redis_url))
        jobs.append(_hosted(client, "hosted speech and voice", s.gnani_base, bool(s.gnani_api_key.get_secret_value())))
        jobs.append(_hosted(client, "hosted translation", s.llm_base_url, bool(s.llm_base_url and s.llm_model)))
        checks, gpu = await asyncio.gather(asyncio.gather(*jobs), gpu_memory())
    reported = [c["info"]["gpu_gb"] for c in checks if isinstance(c.get("info", {}).get("gpu_gb"), (int, float))]
    needed = [c for c in checks if c["kind"] != "hosted" or c.get("configured")]
    return {"ok": all(c["ok"] for c in needed), "version": "v1", "checks": list(checks), "flags": flags(s),
            "gpu": gpu, "gpu_reported_gb": round(sum(reported), 2) if reported else None,
            "mock_providers": s.mock_providers}


@router.get("/api/v1/health")
async def health() -> dict[str, Any]:
    return await report()


@router.get("/api/v1/flags")
async def get_flags() -> dict[str, Any]:
    return flags()


@router.get("/api/v1/routing")
async def routing() -> dict[str, Any]:
    """Which provider does which step: what the routing file says and what is configured now."""
    from app.v1.router import RoutingError, get_router
    try:
        return {"router_on": get_settings().v1_router, "ok": True, "steps": get_router().describe()}
    except RoutingError as e:
        return {"router_on": get_settings().v1_router, "ok": False, "error": str(e)}


@router.post("/api/v1/warmup")
async def warmup(lang: str = "ta-IN", engine: str = "") -> dict[str, Any]:
    """One small request through every service a session would use, so the first real line is not the slow one.
    Each step is timed; a service that is not configured is skipped, not failed."""
    from app.config import VOICE_BY_LANG
    from app.providers import engine_of, get_gpu_voice, get_llm, get_tts
    s = get_settings()
    eng = engine_of(engine or ("gpu" if s.gpu_mode_ready else "cloud"))
    steps: list[dict[str, Any]] = []

    async def step(name: str, call: Any, *, skip: str = "", limit: float = 25.0) -> None:
        if skip:
            steps.append({"step": name, "ok": False, "skipped": True, "note": skip})
            return
        t0 = time.perf_counter()
        try:
            note = await asyncio.wait_for(call(), limit)
            steps.append({"step": name, "ok": True, "ms": round((time.perf_counter() - t0) * 1000), "note": note or ""})
        except Exception as e:  # noqa: BLE001 - a warm-up reports, it does not raise
            steps.append({"step": name, "ok": False, "ms": round((time.perf_counter() - t0) * 1000),
                          "note": f"{type(e).__name__}: {str(e)[:120]}"})

    async def translate() -> str:
        out = await get_llm(eng).translate_chunk("नमस्ते दोस्तों", lang, [], [])
        return f"{len(out.split())} words back"

    async def stock_voice() -> str:
        n = 0
        voice = {"kind": "stock", "voice": VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])}
        async for chunk in get_tts(eng).synth_stream("ok", lang, voice, sample_rate=s.live_sample_rate):
            n += len(chunk)
        return f"{n} bytes of audio"

    async def voice_engines() -> str:
        got = await get_gpu_voice(eng).health()
        if not got or not all(h.get("ok") for h in got):
            raise RuntimeError(f"{sum(1 for h in got if h.get('ok'))} of {len(got)} voice engines answer")
        return f"{len(got)} engines answer"

    async def get(url: str) -> str:
        async with httpx.AsyncClient() as c:
            r = await c.get(url, timeout=TIMEOUT_S)
            r.raise_for_status()
        return ""

    has_llm = bool((eng == "gpu" and s.gpu_llm_url) or (s.llm_base_url and s.llm_model))
    await step(f"translation ({eng} engine)", translate, skip="" if has_llm else "no translation model is configured")
    await step("stock voice (hosted)", stock_voice, skip="" if s.gnani_api_key.get_secret_value() else "no hosted key")
    await step("copied voice engines", voice_engines, skip="" if s.gpu_voice_url or s.v1_tts_server_url else "no voice engine is configured")
    await step("speech-to-text (ours)", lambda: get(s.gpu_stt_url.rstrip("/") + "/health"), skip="" if s.gpu_stt_url else "not configured")
    await step("separation", lambda: get(s.gpu_separate_url.rstrip("/") + "/health"), skip="" if s.gpu_separate_url else "not configured (CPU is used)")
    await step("QA server", lambda: get(s.v1_qa_url.rstrip("/") + "/health"), skip="" if s.v1_qa_url else "not configured")
    return {"engine": eng, "lang": lang, "ok": all(x["ok"] or x.get("skipped") for x in steps), "steps": steps}
