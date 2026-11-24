"""Words heard back on a sample of the lines a replay dubbed (`eval.live_replay --keep-audio`).

  python -m eval.live_judge RUN_DIR [RUN_DIR ...] --n 20 [--out FILE.json]

For each run folder and language, `--n` dubbed lines spread evenly over the run (three words and more) are sent to
the hosted speech-to-text, one at a time, and the share of each line's words that it hears back is the score (the
same count the pipeline uses for a voice sample: the same word, or the same first four letters). A line spoken in
one call with the lines after it is scored on its own words only. This costs one hosted request per line.
"""
import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.live.pipeline import words_heard  # noqa: E402
from app.providers import get_stt  # noqa: E402


def pick(items: list[Any], n: int) -> list[Any]:
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


async def judge(run: Path, n: int, stt: Any) -> dict[str, Any]:
    lines = json.loads((run / "run.json").read_text(encoding="utf-8"))["lines"]
    out: dict[str, Any] = {}
    for lang in sorted({ln["lang"] for ln in lines}):
        have = [ln for ln in lines if ln["lang"] == lang and len(ln["text"].split()) >= 3
                and (run / f"{lang}_{ln['seq']:04d}.wav").exists()]
        scores = []
        for ln in pick(have, n):
            try:
                heard = (await stt.transcribe(str(run / f"{lang}_{ln['seq']:04d}.wav"), lang)).text
            except Exception as e:  # noqa: BLE001 - no verdict for this line
                print(f"  {run.name} {lang} {ln['seq']}: no verdict ({str(e)[:80]})", flush=True)
                continue
            scores.append({"seq": ln["seq"], "words": len(ln["text"].split()), "score": round(words_heard(ln["text"], heard), 3)})
        vals = [s["score"] for s in scores]
        out[lang] = {"lines": len(vals), "mean_pct": round(100 * statistics.mean(vals), 1) if vals else None,
                     "under_half": sum(v < 0.5 for v in vals), "scores": scores}
        print(f"{run.name} {lang}: {out[lang]['mean_pct']}% of words heard back over {len(vals)} lines "
              f"({out[lang]['under_half']} under half)", flush=True)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    stt = get_stt()     # the hosted service: our own model hears Hindi and Hinglish only
    res = {Path(r).name: await judge(Path(r), a.n, stt) for r in a.runs}
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
