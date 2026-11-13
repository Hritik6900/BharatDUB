"""scripts/live_analyze.py OUTDIR NAME [NAME...] : per-run numbers from the server's own chunk timings + the audio the viewer received.
Run from backend/. Prints a table and writes OUTDIR/results.json."""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(sys.argv[1])
db = json.loads(Path("data/local_db.json").read_text(encoding="utf-8"))
results = {}


def pct(v, p):
    return round(float(np.percentile(v, p)) / 1000, 2) if v else None


for name in sys.argv[2:]:
    d = OUT / name
    summ = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    sid, langs = summ["session_id"], summ["langs"]
    rows = sorted([c for c in db["live_chunks"] if c["session_id"] == sid], key=lambda c: c["seq"])
    res = {"voice": summ["voice"], "langs": langs, "chunks": len(rows), "errors": len(summ["errors"]),
           "voice_ready_s": (summ["voice_events"][0]["t_ms"] / 1000 if summ["voice_events"] else None), "per_lang": {}}
    all_first, all_heard, clone_n, total_n = [], [], 0, 0
    for lg in langs:
        first, heard, done, clone = [], [], [], []
        play_end = 0.0
        dropped = 0
        for c in rows:
            t = c["timings"]
            end = t["t_speech_end"]
            fa = t.get(f"t_first_audio:{lg}")
            if fa is None:
                continue
            wav = d / f"{lg}_chunk{c['seq']:02d}.wav"
            dur = sf.info(wav).duration * 1000 if wav.exists() else 0
            first.append(fa - end)
            # Same rule as web/lib/useLiveFeed.ts: back to back; 1.1x when >2 s is waiting; skip a chunk >10 s late.
            backlog = max(0.0, play_end - fa)
            if backlog > 10000:
                dropped += 1
            else:
                start = max(fa, play_end)
                play_end = start + dur / (1.1 if backlog > 2000 else 1.0)
                heard.append(start - end)
            done.append(t[f"t_audio_done:{lg}"] - end)
            clone.append(t.get(f"clone:{lg}", 0))
        res["per_lang"][lg] = {"n": len(first), "first_audio_p50_s": pct(first, 50), "first_audio_p95_s": pct(first, 95),
                               "heard_p50_s": pct(heard, 50), "heard_p95_s": pct(heard, 95), "heard_max_s": pct(heard, 100),
                               "own_voice_chunks": int(sum(clone)), "skipped_by_player": dropped}
        all_first += first
        all_heard += heard
        clone_n += int(sum(clone))
        total_n += len(first)
    stt = [c["timings"]["t_stt_final"] - c["timings"]["t_speech_end"] for c in rows]
    tr = [c["timings"][f"t_translated:{lg}"] - c["timings"]["t_stt_final"] for c in rows for lg in langs
          if f"t_translated:{lg}" in c["timings"]]
    res |= {"first_audio_p50_s": pct(all_first, 50), "first_audio_p95_s": pct(all_first, 95),
            "heard_p50_s": pct(all_heard, 50), "heard_p95_s": pct(all_heard, 95), "heard_max_s": pct(all_heard, 100),
            "own_voice_pct": round(100 * clone_n / total_n) if total_n else None,
            "stt_after_speech_p50_s": pct(stt, 50), "translate_after_stt_p50_s": pct(tr, 50),
            "chat": summ["chat"]}
    results[name] = res
    print(f"\n{name}: voice={res['voice'][:8]} langs={len(langs)} chunks={res['chunks']} errors={res['errors']} "
          f"voice_ready={res['voice_ready_s']}")
    print(f"  first audio p50 {res['first_audio_p50_s']} p95 {res['first_audio_p95_s']} | heard p50 {res['heard_p50_s']} "
          f"p95 {res['heard_p95_s']} max {res['heard_max_s']} | own voice {res['own_voice_pct']}% | "
          f"stt {res['stt_after_speech_p50_s']} translate {res['translate_after_stt_p50_s']}")
    for lg, r in res["per_lang"].items():
        print(f"   {lg}: n={r['n']} first p50 {r['first_audio_p50_s']} p95 {r['first_audio_p95_s']} heard p50 {r['heard_p50_s']} "
              f"max {r['heard_max_s']} own-voice {r['own_voice_chunks']}/{r['n']} skipped {r['skipped_by_player']}")
(OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
