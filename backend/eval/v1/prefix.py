"""Does putting the fixed rules first (`V1_LLM_PREFIX_CACHE`) raise the translation server's prefix-cache hits?

  python -m eval.v1.prefix [--lines 40] [--lang ta-IN] [--out DIR]

The same live lines are translated by our model twice, with the flag off and on, in turns of ten so a slow spell
falls on both. Around each turn the server's own counters are read (`vllm:prefix_cache_queries_total` and
`..._hits_total` on its `/metrics`), which gives the share of prompt tokens served from the cache, and each call
is timed. Run it when nobody is live: the counters are the whole server's, so another session would be counted.
"""
import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

LINES = [
    "aaj hum ek naya game khelne wale hain", "chat mein batao kaunsa map khelna hai", "ye round bahut mushkil tha lekin hum jeet gaye",
    "agar stream pasand aaye to like zaroor karna", "mere peeche do enemy hain jaldi cover do", "aaj hum poore do ghante khelenge",
    "is gun mein bahut recoil hai control karna padta hai", "chalo agle match ke liye ready ho jao",
    "kahin bhi tandoori khaoge ya fry khaoge usi oil ko baar baar use karte hain", "isliye ghar ka khana sabse accha hota hai",
]


async def counters(c: httpx.AsyncClient, base: str) -> tuple[float, float]:
    # a fresh connection each time: an idle one is closed by the server between the turns
    text = (await c.get(base + "/metrics", timeout=8, headers={"Connection": "close"})).text
    def val(name: str) -> float:
        m = re.search(rf"^{re.escape(name)}\{{[^}}]*\}} ([0-9.e+]+)$", text, re.M)
        return float(m.group(1)) if m else 0.0
    return val("vllm:prefix_cache_queries_total"), val("vllm:prefix_cache_hits_total")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=40)
    ap.add_argument("--lang", default="ta-IN")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    from app.config import get_settings
    from app.providers import _local_llm
    s = get_settings()
    if not s.gpu_llm_url:
        print("GPU_LLM_URL is not set: nothing to measure")
        return
    base = s.gpu_llm_url.rstrip("/").removesuffix("/v1")
    res = {"off": {"ms": [], "queries": 0.0, "hits": 0.0}, "on": {"ms": [], "queries": 0.0, "hits": 0.0}}
    async with httpx.AsyncClient() as c:
        n = 0
        while n < a.lines:
            for name in ("off", "on"):
                llm = _local_llm()
                llm.s = llm.s.model_copy(update={"v1_llm_prefix_cache": name == "on"})
                q0, h0 = await counters(c, base)
                for k in range(10):
                    line = LINES[(n + k) % len(LINES)]
                    ctx = [LINES[(n + k - j) % len(LINES)] for j in (2, 1)]
                    t0 = time.perf_counter()
                    await llm.translate_chunk(line, a.lang, ["game", "chat"], ctx, native=True, max_words=6 + (n + k) % 5)
                    res[name]["ms"].append((time.perf_counter() - t0) * 1000)
                q1, h1 = await counters(c, base)
                res[name]["queries"] += q1 - q0
                res[name]["hits"] += h1 - h0
            n += 10
    out = {}
    for name, r in res.items():
        ms = sorted(r["ms"])
        out[name] = {"calls": len(ms), "p50_ms": round(statistics.median(ms)), "p95_ms": round(ms[int(0.95 * (len(ms) - 1))]),
                     "prompt_tokens": int(r["queries"]), "from_cache": int(r["hits"]),
                     "cache_share_pct": round(100 * r["hits"] / r["queries"], 1) if r["queries"] else None}
        print(name, out[name])
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True)
        (Path(a.out) / "prefix.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
