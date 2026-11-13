"""scripts/live_quality.py OUTDIR SOURCE_WAV RUN [RUN...]
1) Words: every dubbed chunk is transcribed back by Prisma and compared with the caption that was meant to be spoken.
2) Pitch: median speaking pitch of the source voice vs the dub, split by own-voice / stock chunks (numpy autocorrelation).
Pitch is one coarse trait of a voice, not a similarity score. Run from backend/."""
import asyncio
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from app.providers import get_stt  # noqa: E402

OUT, SRC = Path(sys.argv[1]), sys.argv[2]
db = json.loads(Path("data/local_db.json").read_text(encoding="utf-8"))


def f0_median(path: str) -> tuple[float | None, int]:
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    win, hop = int(0.04 * sr), int(0.02 * sr)
    lo, hi = int(sr / 400), int(sr / 70)
    vals = []
    for i in range(0, len(x) - win, hop):
        fr = x[i:i + win]
        if np.sqrt(np.mean(fr ** 2)) < 0.02:
            continue
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, "full")[win - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.5:
            vals.append(sr / k)
    return (float(np.median(vals)) if vals else None), len(vals)


def norm(s: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", s.lower(), flags=re.UNICODE).split()


async def main() -> None:
    stt = get_stt()
    src_f0, n = f0_median(SRC)
    print(f"source voice: median pitch {src_f0:.0f} Hz ({n} voiced frames)")
    report: dict = {"source_pitch_hz": round(src_f0)}
    for run in sys.argv[3:]:
        d = OUT / run
        summ = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        ev = json.loads((d / "events.json").read_text(encoding="utf-8"))
        rows = {c["seq"]: c for c in db["live_chunks"] if c["session_id"] == summ["session_id"]}
        caps = {(m["lang"], m["seq"]): m["text"] for m in ev if m.get("type") == "caption" and m["_ch"] == m.get("lang")}
        rep: dict = {}
        for lg in summ["langs"]:
            ratios, pitch = [], {0: [], 1: []}
            worst = (1.0, "", "")
            for seq, c in sorted(rows.items()):
                wav = d / f"{lg}_chunk{seq:02d}.wav"
                if not wav.exists() or (lg, seq) not in caps:
                    continue
                own = int(c["timings"].get(f"clone:{lg}", 0))
                f0, nv = f0_median(str(wav))
                if f0 and nv >= 10:
                    pitch[own].append(f0)
                try:
                    heard = (await stt.transcribe(str(wav), lg, fmt="codemix")).text
                except Exception as e:  # noqa: BLE001
                    heard = f"<stt failed: {str(e)[:60]}>"
                r = SequenceMatcher(None, norm(caps[(lg, seq)]), norm(heard)).ratio()
                ratios.append((own, r))
                if r < worst[0]:
                    worst = (r, caps[(lg, seq)], heard)
            def avg(v):
                return round(100 * float(np.mean(v))) if v else None
            rep[lg] = {
                "chunks": len(ratios),
                "words_match_own_voice_pct": avg([r for o, r in ratios if o]),
                "words_match_stock_pct": avg([r for o, r in ratios if not o]),
                "pitch_own_voice_hz": round(float(np.median(pitch[1]))) if pitch[1] else None,
                "pitch_stock_hz": round(float(np.median(pitch[0]))) if pitch[0] else None,
                "worst": {"match_pct": round(100 * worst[0]), "asked": worst[1], "heard": worst[2]},
            }
            x = rep[lg]
            print(f"{run} {lg}: words match own {x['words_match_own_voice_pct']}% stock {x['words_match_stock_pct']}% | "
                  f"pitch own {x['pitch_own_voice_hz']} Hz stock {x['pitch_stock_hz']} Hz | worst {x['worst']['match_pct']}%")
        report[run] = rep
    (OUT / "quality.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


asyncio.run(main())
