"""live_llm_bench.py MODEL[@effort] ...   Speed and script cleanliness of live phrase translation.

Runs the real Live prompt (OpenAILLM.translate_chunk) on Hinglish phrases cut the way the Phraser cuts them,
into Tamil, Bengali, Punjabi and English, and reports per model: latency p50/p95, how many replies contain
letters from a script that is neither the target's nor Latin, and how many came back untranslated.
Real provider calls (about 50 short ones per model). Run from backend/.
"""
import asyncio
import statistics as st
import sys
import time
import unicodedata

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from app.config import get_settings  # noqa: E402
from app.providers.llm_openai import OpenAILLM, wrong_script  # noqa: E402

PHRASES = [
    "कहीं भी तंदूरी खाओगे या fry खाओगे उसी oil को बार बार",
    "बदलते रहते हैं और पकाते रहते हैं",
    "जो कि काफ़ी नुकसान करता है",
    "मैं ये grill chicken खुद खाता हूँ",
    "और अपने family में भी खिलाता हूँ",
    "मैं कहूँगा आपको पूरी दिल्ली में ऐसा taste नहीं मिलेगा भाई",
    "इस green chicken की खास बात ये है",
    "कि भाई इसे हम कम से कम machine में डेढ़ घंटे पकाते हैं",
    "भाई, token claim करते हैं। रैबो को बोल token claim करें यार।",
    "पीछे वाले two touch कर ले, इसके पीछे tower के पीछे वाले।",
    "नहीं भाई, बहाने चाहिए होते हैं हर चीज़ में।",
    "अरे वो कैसी वाले यार उनसे दूर रहना पड़ेगा।",
]
LANGS = ["ta-IN", "bn-IN", "pa-IN", "en-IN"]


async def main() -> None:
    base = get_settings()
    for spec in sys.argv[1:]:
        model, _, effort = spec.partition("@")
        s = base.model_copy(update={"llm_model_fast": model, "llm_reasoning_effort_fast": effort,
                                    "llm_model": "bench-no-fallback"})
        llm = OpenAILLM(s)
        times, bad, same, chars, errs = [], [], 0, 0, 0
        try:
            await llm._chat("Reply with OK.", "hi", model=model, effort=effort or None, max_tokens=5)  # warm up
        except Exception as e:  # noqa: BLE001
            print(f"{spec:34s} unavailable: {str(e)[:110]}")
            continue
        for lang in LANGS:
            ctx: list[str] = []
            for ph in PHRASES:
                t0 = time.perf_counter()
                try:
                    out = await llm.translate_chunk(ph, lang, [], ctx)
                except Exception:  # noqa: BLE001 - includes the fallback to the non-existent main model
                    errs += 1
                    ctx.append(ph)
                    continue
                times.append(time.perf_counter() - t0)
                ctx.append(ph)
                chars += len(out)
                if out.strip() == ph.strip():
                    same += 1
                if wrong_script(out, lang):
                    bad.append((lang, out))
        n = len(times)
        if not n:
            print(f"{spec:34s} no replies ({errs} errors)")
            continue
        ts = sorted(times)
        print(f"{spec:34s} p50 {st.median(ts):.2f}s p95 {ts[int(0.95 * (n - 1))]:.2f}s | wrong script or untranslated "
              f"{errs + len(bad)}/{n + errs} | avg {chars / n:.0f} chars")
        for lang, out in bad[:3]:
            odd = sorted({unicodedata.name(ch, "?").split()[0] for ch in out if ch.isalpha() and not ch.isascii()})
            print(f"      {lang}: {out[:70]}  [{', '.join(odd)}]")


asyncio.run(main())
