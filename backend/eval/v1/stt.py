"""Speech-to-text eval on the hard set: key words heard right, out of 80, clean and hard, per provider.

  python -m eval.v1.stt --set <folder with 00.wav .. 23.wav> [--runs 3] [--providers prisma,whisper_gpu] --out DIR

The set is 24 class and stream lines (Hindi and Hinglish) with 80 key words: names, subject terms, numbers
(`eval/v1/hard_set.json`: the text of each line and the spellings that count for each key word). The audio is
not in the repository: it was made with hosted stock voices, so it is speech from a machine, not from a teacher.
"Hard" is the same audio 15% faster, with a room's echo and noise 10 dB under the voice, made here from the clean
file; the noise differs per run (seeded by the run number), so the spread across runs is real.

Providers are the router's names (`prisma`, `whisper_gpu`, `indic_transcribe`); one that is not configured is
left out. Calls go one at a time: the hosted account takes one request at once.
"""
import argparse
import asyncio
import json
import re
import statistics
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent


def load16(path: Path) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != 16000:
        x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * 16000 / sr)), np.arange(len(x)), x).astype(np.float32)
    return x


def harden(x: np.ndarray, seed: int) -> np.ndarray:
    """15% faster, a room's echo, low rumbling noise 10 dB under the voice."""
    rng = np.random.default_rng(seed)
    ir = rng.standard_normal(5600).astype(np.float32) * np.exp(-np.arange(5600) / 1120).astype(np.float32)
    ir[0] = 4.0
    x = np.interp(np.linspace(0, len(x) - 1, int(len(x) / 1.15)), np.arange(len(x)), x).astype(np.float32)
    x = np.convolve(x, ir)[: len(x)]
    x = x / (np.abs(x).max() + 1e-6) * 0.5
    nz = np.cumsum(rng.standard_normal(len(x)).astype(np.float32))
    nz -= np.convolve(nz, np.ones(400) / 400, "same")
    nz = nz / (np.sqrt((nz ** 2).mean()) + 1e-9) * float(np.sqrt((x ** 2).mean())) * 10 ** (-0.5)
    return (x + nz).astype(np.float32)


def squash(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s.lower(), flags=re.UNICODE)


def key_words(truth: list[dict[str, Any]], heard: list[str]) -> int:
    """A key word counts when any of its accepted spellings is in what was heard for its line."""
    return sum(any(squash(a) in squash(text) for a in alts) for t, text in zip(truth, heard) for alts in t["terms"])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, help="folder with the audio of the hard set")
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--providers", default="prisma,whisper_gpu,indic_transcribe")
    ap.add_argument("--kinds", default="clean,hard")
    a = ap.parse_args()
    import sys
    sys.path.insert(0, str(HERE.parents[1]))
    from app.v1.router import Router, load_config
    r = Router(load_config())
    truth = json.loads((HERE / "hard_set.json").read_text(encoding="utf-8"))
    total = sum(len(t["terms"]) for t in truth)
    names = [n for n in a.providers.split(",") if r.available(n)]
    left_out = [n for n in a.providers.split(",") if n not in names]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    tmp = Path(tempfile.gettempdir()) / "bd_v1_stt_eval.wav"
    for kind in a.kinds.split(","):
        for run in range(1, (a.runs if kind == "hard" else 1) + 1):    # the clean audio is the same every time
            heard: dict[str, list[str]] = {n: [] for n in names}
            for t in truth:
                x = load16(Path(a.set) / t["file"])
                sf.write(str(tmp), harden(x, 7 * run) if kind == "hard" else x, 16000)
                for n in names:
                    text = ""
                    for attempt in range(3):
                        try:
                            kw = {"fmt": "codemix"} if n == "prisma" else {}
                            text = (await r.provider("stt", n).transcribe(str(tmp), "hi-IN", **kw)).text
                            break
                        except Exception:  # noqa: BLE001 - counted as nothing heard after three tries
                            await asyncio.sleep(2 + 2 * attempt)
                    heard[n].append(text)
            for n in names:
                rows.append({"kind": kind, "run": run, "provider": n, "key_words": key_words(truth, heard[n]), "of": total,
                             "empty": sum(1 for h in heard[n] if not h.strip()), "heard": heard[n]})
                print(f"{kind} run {run} | {n}: {rows[-1]['key_words']}/{total} key words", flush=True)
            (out / "stt_runs.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.unlink(missing_ok=True)
    lines = ["| Provider | " + " | ".join(a.kinds.split(",")) + " |", "|---|" + "---|" * len(a.kinds.split(","))]
    for n in names:
        cells = []
        for kind in a.kinds.split(","):
            v = [x["key_words"] for x in rows if x["provider"] == n and x["kind"] == kind]
            cells.append(f"{statistics.mean(v):g} of {total} ({min(v)}-{max(v)}, {len(v)} run{'s' if len(v) > 1 else ''})" if v else "not measured")
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    for n in left_out:
        lines.append(f"| {n} | " + " | ".join("not configured" for _ in a.kinds.split(",")) + " |")
    (out / "stt_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
