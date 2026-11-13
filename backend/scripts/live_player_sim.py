"""live_player_sim.py OUTDIR RUN LANG [--jitter 0.3] [--catchup-after 2] [--rate 1.1] [--max-backlog 10]

Replays the audio messages a viewer received in a live_e2e run through the same scheduling rules as the web
player (web/lib/useLiveFeed.ts) and reports what the viewer would have heard: how late each phrase starts,
gaps inside a phrase (underruns), and phrases skipped. Offline, no provider calls. Run from backend/.
"""
import argparse
import json
import statistics as st
from pathlib import Path


def simulate(events: list[dict], lang: str, jitter: float, catchup_after: float, rate: float,
             max_backlog: float) -> dict:
    next_at = 0.0
    cur = {"seq": -1, "drop": False, "rate": 1.0}
    starts: dict[int, float] = {}
    underruns, dropped, sped = 0, set(), set()
    backlog_at_start: list[float] = []
    for m in events:
        if m.get("type") != "audio" or m.get("lang") != lang or m.get("_ch") != lang or not m.get("bytes"):
            continue
        now, seq = m["_t"], m["seq"]
        if seq != cur["seq"]:
            backlog = max(0.0, next_at - now)
            cur = {"seq": seq, "drop": backlog > max_backlog, "rate": rate if backlog > catchup_after else 1.0}
            backlog_at_start.append(backlog)
            if cur["rate"] != 1.0:
                sped.add(seq)
        if cur["drop"]:
            dropped.add(seq)
            continue
        dur = m["bytes"] / 2 / m["sample_rate"]
        if next_at > now:
            at = max(next_at, now + 0.02)
        else:
            at = now + jitter
            if seq in starts:
                underruns += 1  # the phrase had already started: this is an audible gap inside it
        starts.setdefault(seq, at)
        next_at = at + dur / cur["rate"]
    return {"starts": starts, "underruns": underruns, "dropped": len(dropped), "sped": len(sped),
            "backlog": backlog_at_start}


def pct(v: list[float], p: float) -> float:
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("run")
    ap.add_argument("lang")
    ap.add_argument("--jitter", type=float, default=0.3)
    ap.add_argument("--catchup-after", type=float, default=2.0)
    ap.add_argument("--rate", type=float, default=1.1)
    ap.add_argument("--max-backlog", type=float, default=10.0)
    a = ap.parse_args()
    d = Path(a.outdir) / a.run
    events = json.loads((d / "events.json").read_text(encoding="utf-8"))
    summ = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    db = json.loads(Path("data/local_db.json").read_text(encoding="utf-8"))
    rows = {c["seq"]: c for c in db["live_chunks"] if c["session_id"] == summ["session_id"]}
    r = simulate(events, a.lang, a.jitter, a.catchup_after, a.rate, a.max_backlog)
    # Client clock -> session clock: the first audio message of a phrase arrived when the server recorded t_first_audio.
    first_msg = {}
    for m in events:
        if m.get("type") == "audio" and m.get("_ch") == a.lang and m.get("bytes"):
            first_msg.setdefault(m["seq"], m["_t"])
    heard = []
    for seq, at in r["starts"].items():
        t = (rows.get(seq) or {}).get("timings") or {}
        fa = t.get(f"t_first_audio:{a.lang}")
        if fa is None or seq not in first_msg:
            continue
        heard.append(fa - t["t_speech_end"] + (at - first_msg[seq]) * 1000)
    print(f"{a.run} {a.lang} jitter={a.jitter} catchup>{a.catchup_after}s x{a.rate} skip>{a.max_backlog}s")
    if heard:
        print(f"  phrase end -> heard: p50 {st.median(heard):.0f}  p95 {pct(heard, 95):.0f}  max {max(heard):.0f} ms "
              f"({len(heard)} phrases)")
    print(f"  gaps inside a phrase {r['underruns']}  phrases skipped {r['dropped']}  played faster {r['sped']}  "
          f"audio waiting at phrase start p50 {st.median(r['backlog']) if r['backlog'] else 0:.2f}s "
          f"max {max(r['backlog'], default=0):.2f}s")


if __name__ == "__main__":
    main()
