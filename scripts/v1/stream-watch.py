"""Watch every live session on one or more backends, all the time. Read-only: it asks the backends' own
endpoints and, when a session ends, reads that backend's store file to sum the session up. It never posts.

  python scripts/v1/stream-watch.py --out data-v1/streamwatch \
      v0=http://127.0.0.1:8010=C:/path/to/v0/backend/data/local_db.json \
      v1=http://127.0.0.1:8110=C:/path/to/v1/data-v1/local_db.json

Writes <out>/<name>_<session>.csv (a row every 20 s), <out>/<name>_<session>.summary.txt (at the end) and
<out>/events.log (one line per thing worth knowing; the same lines go to stdout).

Lines about the link to the GPU machine (from a backend with V1_BREAKER on, asked every 20 s at
/api/v1/circuits; a backend without that endpoint is simply not asked again):
  CIRCUIT OPEN <endpoint>: <why>          the endpoint is not called for 30 s; the next provider answers
  CIRCUIT CLOSED <endpoint> after <n> s   it answers again and is in use
  CIRCUIT LINK STALL / LINK BACK          every GPU endpoint failed in the same look / one answers again
  RUNG [backend session] a -> b (why)     a live session stepped down or up (V1_LIVE_DEGRADE)

A session's summary also has, per language, the dub's length against its slot (dur_ratio p50 / p90), the backlog
(how far the dub queue was behind the video, p50 / p95) and what the budget controller did, when the backend
stores them (v1.1: with the trace or V1_LIVE_BUDGET / V1_LIVE_RATECTRL on).
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

EVERY_S = 20
SUMMARY_EVERY = 15            # polls: a summary line every 5 minutes per live session
STALL_POLLS = 9               # 3 minutes without a new phrase
SLOW_MS = 3500                # first audio, median of a language's last 20 phrases
LOW_ON_TIME = 80.0            # percent, with at least MIN_N phrases counted
MIN_N = 20
FIELDS = ["time", "status", "viewers", "chunks", "n", "p50_ms", "p95_ms", "heard_p50_ms", "heard_p95_ms",
          "viewer_n", "viewer_on_time_pct", "viewer_late_p95_ms", "sync_delay_ms", "sync_grown",
          "sync_on_time_pct", "sync_late_p95_ms", "last20"]


def get(url: str, timeout: float = 10) -> object:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def pct(values: list[float], p: float) -> float | None:
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))] if v else None


def share(flags: list) -> str:
    return f"{100 * sum(map(bool, flags)) / len(flags):.0f}% of {len(flags)}" if flags else "-"


def session_summary(db_path: str, sid: str) -> list[str]:
    """Per-language numbers of one finished session, from its stored phrases."""
    rows = None
    for _ in range(5):                       # the server may be in the middle of writing the file
        try:
            rows = json.loads(Path(db_path).read_text(encoding="utf-8")).get("live_chunks", [])
            break
        except (OSError, ValueError):
            time.sleep(1)
    if rows is None:
        return ["   (the store file could not be read)"]
    if isinstance(rows, dict):
        rows = list(rows.values())
    r = sorted((x for x in rows if x.get("session_id") == sid), key=lambda x: x["seq"])
    if not r:
        return ["   (no stored phrases)"]
    dur = max(1.0, (r[-1]["timings"].get("t_speech_end", r[-1]["t_speech_ms"]) - r[0]["t_speech_ms"]) / 1000)
    words = [len(x["src_text"].split()) for x in r]
    span = [(x["timings"].get("t_speech_end", x["t_speech_ms"]) - x["t_speech_ms"]) / 1000 for x in r]
    out = [f"   {len(r)} phrases in {dur / 60:.1f} min; speaking {100 * sum(s for s in span if s > 0) / dur:.0f}% of the "
           f"time, {sum(words) / (dur / 60):.0f} words a minute, {pct(words, 50)} words a phrase"]
    timings = [x["timings"] for x in r]
    for lang in sorted({k.split(":")[1] for t in timings for k in t if k.startswith("t_translated:")}):
        spoken = [t for t in timings if f"t_first_audio:{lang}" in t]
        if not spoken:
            continue
        skips = Counter(t[f"skipped:{lang}"] for t in timings if f"skipped:{lang}" in t)
        first = [t[f"t_first_audio:{lang}"] - t["t_speech_end"] for t in spoken if "t_speech_end" in t]
        voice = [t[f"t_first_audio:{lang}"] - t[f"t_translated:{lang}"] for t in spoken if f"t_translated:{lang}" in t]
        late = [t[f"late:{lang}"] for t in spoken if t.get(f"late:{lang}") is not None]
        tempo = [t.get(f"tempo:{lang}", 1.0) for t in spoken]
        out.append(f"   {lang}: {len(spoken)} spoken; first audio p50 {pct(first, 50)} p95 {pct(first, 95)} ms; "
                   f"text to audio p50 {pct(voice, 50)} p95 {pct(voice, 95)} ms")
        out.append(f"      within 0.25 s {share([x <= 250 for x in late])}, within 1 s {share([x <= 1000 for x in late])}, "
                   f"late p95 {pct(late, 95)} ms, worst {max(late) if late else None} ms")
        out.append(f"      copied voice {share([t.get(f'clone:{lang}', 0) for t in spoken])}, on our GPU "
                   f"{share([t.get(f'gpu:{lang}', 0) for t in spoken])}, at the 1.3x limit {share([x >= 1.295 for x in tempo])}, "
                   f"skipped as too late {skips.get('late', 0)}")
        ratio = [t[f"dur_ratio:{lang}"] for t in spoken if t.get(f"dur_ratio:{lang}") is not None]
        if ratio:     # v1.1 (a backend with the trace or the dense-speech flags on): dub length against its slot
            backlog = [t[f"backlog:{lang}"] for t in timings if t.get(f"backlog:{lang}") is not None
                       and t.get(f"skipped:{lang}") != "unheard"]
            scale = [t[f"ctl:{lang}"] for t in timings if t.get(f"ctl:{lang}") is not None]
            out.append(f"      dub length / slot p50 {pct(ratio, 50):.2f} p90 {pct(ratio, 90):.2f}, longer than its slot "
                       f"{share([x > 1.0 for x in ratio])}; backlog p50 {pct(backlog, 50)} p95 {pct(backlog, 95)} ms; "
                       f"at 1.4x {share([x >= 1.395 for x in tempo])}"
                       + (f"; budget scale mean {sum(scale) / len(scale):.2f}, shortened again "
                          f"{sum(1 for t in timings if t.get(f'reasked:{lang}') == 2)}, dense phrases "
                          f"{sum(1 for t in timings if t.get('dense'))}" if scale else ""))
    return out


class Watch:
    def __init__(self, out: Path, backends: list[tuple[str, str, str]], health_url: str) -> None:
        self.out, self.backends, self.health_url = out, backends, health_url
        self.state: dict[tuple[str, str], dict] = {}     # (backend, session id) -> what was seen last
        self.down: set[str] = set()
        self.bad_engines: set[str] = set()
        self.both = False
        self.tick = 0
        self.circuit_url = health_url.rsplit("/health", 1)[0] + "/circuits" if health_url.endswith("/health") else ""
        self.circuit_seen: int | None = None      # id of the last circuit event printed; None = not asked yet
        out.mkdir(parents=True, exist_ok=True)

    def say(self, text: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}"
        print(line, flush=True)
        with (self.out / "events.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    @staticmethod
    def brief(m: dict) -> str:
        return (f"phrases={m.get('chunks')} first_audio p50={m.get('p50_ms')} p95={m.get('p95_ms')} "
                f"hold={m.get('sync_delay_ms')} on_time={m.get('sync_on_time_pct')}% "
                f"viewer_on_time={m.get('viewer_on_time_pct')}% (n={m.get('viewer_n')}) last20={m.get('last20')}")

    def log_row(self, name: str, sid: str, m: dict) -> None:
        path = self.out / f"{name}_{sid[:8]}.csv"
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(m)

    def one_session(self, name: str, base: str, db: str, s: dict) -> None:
        sid, key, tag = s["id"], (name, s["id"]), f"[{name} {s['id'][:8]}]"
        m = dict(get(f"{base}/api/live/sessions/{sid}/metrics"))
        last20 = {lang: pct(v.get("recent_ms", [])[-20:], 50) for lang, v in m.get("per_lang", {}).items()}
        m.update(time=time.strftime("%H:%M:%S"), status=s.get("status"), viewers=s.get("viewers"),
                 last20=" ".join(f"{k}:{int(v)}" for k, v in last20.items() if v is not None))
        self.log_row(name, sid, m)
        prev = self.state.get(key)
        if prev is None:
            self.state[key] = {"m": m, "polls": 0, "still": 0, "slow": set(), "low": False}
            self.say(f"START {tag} engine={s.get('engine')} langs={','.join(s.get('target_langs', []))} "
                     f"video={s.get('youtube_video_id')} voice_from_stream={s.get('voice_from_stream')} "
                     f"streamer={bool(s.get('streamer_id'))}")
            return
        st, pm = prev, prev["m"]
        st["polls"] += 1
        if st["polls"] % SUMMARY_EVERY == 0:
            self.say(f"SUMMARY {tag} {self.brief(m)}")
        if m.get("rung") != pm.get("rung"):
            self.say(f"RUNG {tag} {pm.get('rung')} -> {m.get('rung')} ({m.get('rung_why') or 'back to normal'})")
        if m.get("sync_delay_ms") != pm.get("sync_delay_ms"):
            self.say(f"HOLD {pm.get('sync_delay_ms')}->{m.get('sync_delay_ms')} {tag} {self.brief(m)}")
        for lang, v in last20.items():
            slow = v is not None and v > SLOW_MS
            if slow and lang not in st["slow"]:
                self.say(f"SLOW {tag} {lang}: last 20 phrases first audio p50 {int(v)} ms {self.brief(m)}")
            (st["slow"].add if slow else st["slow"].discard)(lang)
        on_time, n = m.get("viewer_on_time_pct"), m.get("viewer_n") or 0
        low = on_time is not None and n >= MIN_N and on_time < LOW_ON_TIME
        if low and not st["low"]:
            self.say(f"LATE {tag} viewer on time under {LOW_ON_TIME:.0f}% {self.brief(m)}")
        st["low"] = low
        st["still"] = st["still"] + 1 if m.get("chunks") == pm.get("chunks") else 0
        if st["still"] == STALL_POLLS:
            self.say(f"STALL {tag} no new phrase for {STALL_POLLS * EVERY_S // 60} min while live {self.brief(m)}")
        st["m"] = m

    def ended(self, name: str, base: str, db: str, sid: str) -> None:
        st = self.state.pop((name, sid))
        try:
            m = dict(get(f"{base}/api/live/sessions/{sid}/metrics"))
        except Exception:  # noqa: BLE001
            m = st["m"]
        time.sleep(2)                                  # let the last phrases reach the store
        lines = session_summary(db, sid) if db else []
        (self.out / f"{name}_{sid[:8]}.summary.txt").write_text("\n".join([self.brief(m), *lines]) + "\n", encoding="utf-8")
        self.say(f"ENDED [{name} {sid[:8]}] {self.brief(m)}\n" + "\n".join(lines))

    def engines(self) -> None:
        try:
            checks = get(self.health_url, timeout=40).get("checks", [])
        except Exception as e:  # noqa: BLE001
            checks = [{"name": "status endpoint", "ok": False, "error": str(e)}]
        bad = {c["name"] for c in checks if not c.get("ok") and c.get("configured", True)}
        down, back = sorted(bad - self.bad_engines), sorted(self.bad_engines - bad)
        if len(down) > 3:           # everything at once, hosted services too: the link from this PC, not the engines
            self.say(f"LINK STALL {len(down)} services did not answer at once: {', '.join(down)}")
        else:
            for name in down:
                self.say(f"ENGINE DOWN {name}")
        if len(back) > 3:
            self.say(f"LINK BACK {len(back)} services answer again")
        else:
            for name in back:
                self.say(f"ENGINE BACK {name}")
        self.bad_engines = bad

    def circuits(self) -> None:
        """Opens and closes of the backend's circuit breakers since the last look."""
        if not self.circuit_url:
            return
        try:
            got = get(f"{self.circuit_url}?after={self.circuit_seen or 0}", timeout=5)
        except urllib.error.HTTPError as e:
            if e.code == 404:           # a backend from before the breakers: nothing to ask
                self.circuit_url = ""
            return
        except Exception:  # noqa: BLE001 - the backend is away; BACKEND DOWN says so
            return
        if not isinstance(got, dict) or not got.get("on"):
            return
        events = got.get("events") or []
        if self.circuit_seen is None:   # first look: say what is open now, not the history
            for c in got.get("circuits") or []:
                if c.get("state") != "closed":
                    self.say(f"CIRCUIT OPEN {c['name']}: {c.get('reason', '')} (already, for {c.get('down_s')} s)")
            self.circuit_seen = max([e["id"] for e in events], default=0)
            return
        if int(got.get("last") or 0) < self.circuit_seen:
            self.circuit_seen = 0       # the backend restarted and its ids began again: ask from the beginning
            return
        for e in events:
            name, kind = e.get("name"), e.get("event")
            if kind == "open":
                self.say(f"CIRCUIT OPEN {name}: {e.get('reason', '')}")
            elif kind == "close":
                self.say(f"CIRCUIT CLOSED {name} after {e.get('down_s')} s ({e.get('retries', 0)} retries failed first)")
            elif kind == "link_stall":
                self.say(f"CIRCUIT LINK STALL all {e.get('services')} GPU endpoints failed at once ({e.get('reason', '')}); "
                         "the hosted services answer until the link is back")
            elif kind == "link_back":
                self.say(f"CIRCUIT LINK BACK after {e.get('down_s')} s: {e.get('answering')} of {e.get('services')} GPU endpoints answer")
            self.circuit_seen = max(self.circuit_seen, int(e.get("id", 0)))

    def run(self) -> None:
        self.say("WATCH started: " + ", ".join(f"{n}={b}" for n, b, _ in self.backends))
        while True:
            live_now: dict[str, list[str]] = {}
            for name, base, db in self.backends:
                try:
                    sessions = [s for s in get(f"{base}/api/live/sessions") if s.get("status") == "live"]
                except Exception as e:  # noqa: BLE001
                    if name not in self.down:
                        self.say(f"BACKEND DOWN {name} ({base}): {e}")
                    self.down.add(name)
                    continue
                if name in self.down:
                    self.down.discard(name)
                    self.say(f"BACKEND BACK {name}")
                live_now[name] = [s["id"] for s in sessions]
                for s in sessions:
                    try:
                        self.one_session(name, base, db, s)
                    except Exception as e:  # noqa: BLE001
                        self.say(f"READ FAILED [{name} {s['id'][:8]}] {e}")
                for n, sid in [k for k in self.state if k[0] == name and k[1] not in live_now[name]]:
                    self.ended(name, base, db, sid)
            total = sum(len(v) for v in live_now.values())
            if total > 1 and not self.both:
                self.say(f"SHARED GPU: {total} streams are live at once ({', '.join(f'{k}:{len(v)}' for k, v in live_now.items())}); "
                         "they share one GPU and one hosted account, so their numbers are not comparable with a stream alone")
            self.both = total > 1
            if self.health_url and self.tick % 3 == 0:        # once a minute
                self.engines()
            self.circuits()
            self.tick += 1
            time.sleep(EVERY_S)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backends", nargs="+", help="name=url[=store file]")
    ap.add_argument("--out", required=True)
    ap.add_argument("--health", default="http://127.0.0.1:8110/api/v1/health", help="status endpoint to ask once a minute ('' = none)")
    a = ap.parse_args()
    backends = []
    for b in a.backends:
        name, url, *db = b.split("=", 2)
        backends.append((name, url.rstrip("/"), db[0] if db else ""))
    Watch(Path(a.out), backends, a.health).run()


if __name__ == "__main__":
    main()
