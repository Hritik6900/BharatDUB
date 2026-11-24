"""Side-by-side pitch video from a recorded Live session (app/v1/record.py) and its source video.

  python -m app.v1.pitch RECORDING VIDEO --lang ta-IN [--stereo split|dub|mix] [--out FILE.mp4]
         [--lead-s 0] [--loops 1] [--gap-ms 0] [--offset-ms 0] [--height 720] [--fps 30]
  (scripts/v1/render-pitch.ps1 is the same call from PowerShell.)

Left: the source video with its own sound. Right: the same video with the session's dub, the dub's captions
burned in, the language, and the session's own numbers. Every number on the picture is computed here from that
recording's `phrases.jsonl`; a number the recording does not hold is left out, never filled in.

Where a phrase's dub lies on the picture: at the video time it was spoken at (`media_s`, sync mode) plus how
late its dub started for a viewer (`late_ms`). That is what a viewer saw and heard. A recording without the
video's clock (a microphone session) is placed by the session clock less `--offset-ms`.

`--lead-s`, `--loops`, `--gap-ms` describe how the video was played into the session when that was not "once,
from its start": the replay harness (eval/live_replay.py) feeds `--lead-s` of silence first, then the file
`--loops` times with `--gap-ms` between. The picture is built the same way (the first frame held, the last frame
held in a gap) so the dub lies where it did.

Stereo: `split` = original sound left, dub right (for headphones: take one off to compare); `dub` = the dub
alone on both; `mix` = the dub with the original at 18% under it, as the viewer page plays it.
"""
import argparse
import json
import statistics
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np

from app.config import LANG_NAMES
from app.shared.audio_utils import ffmpeg_bin, ffprobe_bin

STEREO = ("split", "dub", "mix")
ON_TIME_MS, NEAR_MS = 250, 1000     # "on time" as everywhere else in v1: within 0.25 s of the video moment; and within 1 s
UNDER = 0.18                        # mix: the original's level under the dub (the viewer page's default)


# ---------- the recording ----------
def load(rec: Path, lang: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = json.loads((rec / "session.json").read_text(encoding="utf-8"))
    rows = []
    for line in (rec / "phrases.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("lang") == lang:
                rows.append(r)
    return meta, sorted(rows, key=lambda r: r["seq"])


def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The numbers of one language of one recording. None = the recording does not hold it."""
    spoken = [r for r in rows if not r.get("skipped")]
    late = [r["late_ms"] for r in spoken if r.get("late_ms") is not None]
    first = [r["first_audio_ms"] for r in spoken if r.get("first_audio_ms") is not None]
    skipped: dict[str, int] = {}
    for r in rows:
        if r.get("skipped"):
            skipped[r["skipped"]] = skipped.get(r["skipped"], 0) + 1

    def share(limit: int) -> float | None:
        return round(100 * sum(1 for v in late if v <= limit) / len(late), 1) if late else None

    return {"phrases": len(rows), "spoken": len(spoken), "skipped": skipped,
            "first_audio_p50_ms": round(statistics.median(first)) if first else None, "first_audio_n": len(first),
            "on_time_pct": share(ON_TIME_MS), "within_1s_pct": share(NEAR_MS), "timed": len(late),
            "late_p50_ms": round(statistics.median(late)) if late else None,
            "late_max_ms": max(late) if late else None,
            "copied": sum(1 for r in spoken if r.get("voice") == "copied"),
            "hold_ms": next((r["hold_ms"] for r in reversed(spoken) if r.get("hold_ms")), None)}


def overlay_lines(st: dict[str, Any]) -> list[str]:
    """What is written on the picture. Only what `stats` measured."""
    out = []
    if st["first_audio_p50_ms"] is not None:
        out.append(f"first audio {st['first_audio_p50_ms'] / 1000:.1f} s (median, {st['first_audio_n']} phrases)")
    if st["on_time_pct"] is not None:
        out.append(f"on time {st['on_time_pct']:g}% within 0.25 s, {st['within_1s_pct']:g}% within 1 s")
    if st["spoken"]:
        out.append(f"{st['spoken']} of {st['phrases']} phrases dubbed, {st['copied']} in the copied voice")
    return out


def place(rows: list[dict[str, Any]], offset_ms: int = 0) -> list[tuple[dict[str, Any], int]]:
    """(row, where its dub starts on the picture in ms) for every spoken row."""
    out = []
    for r in rows:
        if r.get("skipped"):
            continue
        if r.get("media_s") is not None:
            at = round(r["media_s"] * 1000) + int(r.get("late_ms") or 0)
        else:
            at = int(r["start_ms"]) - offset_ms
        out.append((r, max(0, at)))
    return out


def build_track(track: Path, placed: list[tuple[dict[str, Any], int]], out: Path, total_ms: int) -> int:
    """The dub laid on the picture's clock: every phrase cut from the session track and put at its place."""
    with wave.open(str(track), "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    y = np.zeros(max(1, round(total_ms * sr / 1000)), dtype=np.int32)
    for r, at in placed:
        a = round(r["track_ms"] * sr / 1000)
        seg = x[a: a + round(r["dur_ms"] * sr / 1000)]
        b = round(at * sr / 1000)
        seg = seg[: max(0, len(y) - b)]
        y[b: b + len(seg)] += seg      # two phrases can touch when the hold grew between them
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.clip(y, -32768, 32767).astype("<i2").tobytes())
    return sr


# ---------- the picture ----------
def probe(video: Path) -> dict[str, Any]:
    out = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,duration:format=duration", "-of", "json", str(video)],
                         check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    pic = next(x for x in d["streams"] if x.get("codec_type") == "video")
    return {"w": int(pic["width"]), "h": int(pic["height"]), "dur_s": float(pic.get("duration") or d["format"]["duration"]),
            "audio": any(x.get("codec_type") == "audio" for x in d["streams"])}


def pane(w: int, h: int, height: int) -> tuple[int, int]:
    """One half of the picture: the video scaled to `height`, both sides even."""
    height -= height % 2
    pw = round(w * height / h)
    return pw + pw % 2, height


def _t(ms: int) -> str:
    cs = max(0, round(ms / 10))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\r", " ").replace("\n", " ").strip()


def captions_ass(placed: list[tuple[dict[str, Any], int]], pw: int, ph: int, total_ms: int, *, lang: str,
                 src_lang: str, lines: list[str]) -> str:
    """Everything written on the picture, as one ASS file over the whole frame (2 x pw wide)."""
    big, small = max(16, ph // 26), max(12, ph // 40)
    m = max(8, pw // 40)
    head = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {2 * pw}", f"PlayResY: {ph}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        # captions: bottom of the right half, in a box, a font that holds every Indian script on Windows
        f"Style: Cap,Nirmala UI,{big},&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,3,2,0,2,{pw + m},{m},{m * 2},1",
        f"Style: TagL,Nirmala UI,{small},&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,1,0,0,0,100,100,0,0,3,2,0,7,{m},{pw + m},{m},1",
        f"Style: TagR,Nirmala UI,{small},&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,1,0,0,0,100,100,0,0,3,2,0,7,{pw + m},{m},{m},1",
        f"Style: Num,Nirmala UI,{small},&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,3,2,0,7,{pw + m},{m},{m + small * 2},1",
        f"Style: Now,Nirmala UI,{small},&H0000E5FF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,3,2,0,9,{pw + m},{m},{m},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    end = _t(total_ms)
    ev = [f"Dialogue: 0,0:00:00.00,{end},TagL,,0,0,0,,Original ({_esc(LANG_NAMES.get(src_lang, src_lang))})",
          f"Dialogue: 0,0:00:00.00,{end},TagR,,0,0,0,,{_esc(LANG_NAMES.get(lang, lang))}: AI-dubbed live by Bharat Dub"]
    if lines:
        ev.append(f"Dialogue: 0,0:00:00.00,{end},Num,,0,0,0,," + "\\N".join(_esc(x) for x in lines))
    for i, (r, at) in enumerate(placed):
        stop = at + int(r["dur_ms"])
        if i + 1 < len(placed):
            stop = min(stop, placed[i + 1][1])      # one caption at a time
        if stop - at < 100:
            continue
        if r.get("text"):
            ev.append(f"Dialogue: 1,{_t(at)},{_t(stop)},Cap,,0,0,0,,{_esc(str(r['text']))}")
        if r.get("late_ms") is not None:
            ev.append(f"Dialogue: 1,{_t(at)},{_t(stop)},Now,,0,0,0,,this line +{max(0, r['late_ms']) / 1000:.1f} s")
    return "\n".join(head + ev) + "\n"


def unit_cmd(video: Path, out: str, pw: int, ph: int, fps: int, unit_s: float, has_audio: bool = True) -> list[str]:
    """One pass of the source at the pane's size with mono sound, picture and sound both exactly `unit_s` long
    (the last frame held and silence added over a gap), so that it can be played in a loop without drifting."""
    vf = f"scale={pw}:{ph},fps={fps},setsar=1,tpad=stop_mode=clone:stop_duration=600,trim=duration={unit_s:.3f}"
    af = f"aresample=44100,apad,atrim=duration={unit_s:.3f}"
    src = ["-i", str(video)] if has_audio else ["-i", str(video), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono"]
    return [ffmpeg_bin(), "-y", "-loglevel", "error", *src, "-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
            "-vf", vf, "-af", af, "-ac", "1", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-t", f"{unit_s:.3f}", out]


def audio_graph(stereo: str, lead_ms: int, total_s: float) -> str:
    orig = (f"[0:a]adelay={lead_ms}:all=1," if lead_ms > 0 else "[0:a]") + f"apad,atrim=duration={total_s:.3f}[orig]"
    dub = f"[1:a]aresample=44100,apad,atrim=duration={total_s:.3f}[dub]"
    if stereo == "split":
        last = "[orig][dub]join=inputs=2:channel_layout=stereo[a]"
    elif stereo == "dub":
        last = "[orig]anullsink;[dub]pan=stereo|c0=c0|c1=c0[a]"
    else:
        last = f"[orig]volume={UNDER}[o];[o][dub]amix=inputs=2:normalize=0,pan=stereo|c0=c0|c1=c0[a]"
    return f"{orig};{dub};{last}"


def final_cmd(unit: str, dub: str, ass: str, out: str, *, stereo: str, lead_ms: int, loops: int, total_s: float,
              fps: int) -> list[str]:
    pad = (f"tpad=start_mode=clone:start_duration={lead_ms / 1000:.3f}:" if lead_ms > 0 else "tpad=") \
        + "stop_mode=clone:stop_duration=600"
    video = f"[0:v]{pad},trim=duration={total_s:.3f},setpts=PTS-STARTPTS,split[l][r];[l][r]hstack=inputs=2,subtitles={ass}[v]"
    return [ffmpeg_bin(), "-y", "-loglevel", "error", "-stream_loop", str(max(0, loops - 1)), "-i", unit, "-i", dub,
            "-filter_complex", f"{video};{audio_graph(stereo, lead_ms, total_s)}", "-map", "[v]", "-map", "[a]",
            "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-t", f"{total_s:.3f}", "-movflags", "+faststart", out]


def render(rec: Path, video: Path, lang: str, *, out: Path | None = None, stereo: str = "split", lead_s: float = 0.0,
           loops: int = 1, gap_ms: int = 0, offset_ms: int = 0, height: int = 720, fps: int = 30) -> dict[str, Any]:
    if stereo not in STEREO:
        raise ValueError(f"stereo is one of {', '.join(STEREO)}")
    meta, rows = load(rec, lang)
    track = rec / f"dub_{lang}.wav"
    placed = place(rows, offset_ms)
    if not placed or not track.is_file():
        raise ValueError(f"the recording holds no dubbed phrase in {lang}")
    v = probe(video)
    pw, ph = pane(v["w"], v["h"], height)
    lead_ms = round(lead_s * 1000)
    unit_ms = round(v["dur_s"] * 1000) + max(0, gap_ms)
    played_ms = lead_ms + max(1, loops) * unit_ms
    total_ms = max(played_ms, max(at + int(r["dur_ms"]) for r, at in placed) + 500)
    st = stats(rows)
    work = rec / f"pitch_work_{lang}"
    work.mkdir(parents=True, exist_ok=True)
    out = out or rec / f"pitch_{lang}_{stereo}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    build_track(track, placed, work / "dub.wav", total_ms)
    (work / "captions.ass").write_text(captions_ass(placed, pw, ph, total_ms, lang=lang, lines=overlay_lines(st),
                                                    src_lang=meta.get("src_lang") or "hi-IN"), encoding="utf-8")
    # ffmpeg runs inside the work folder with bare file names: a drive letter's colon breaks the subtitles filter
    subprocess.run(unit_cmd(video.resolve(), "unit.mp4", pw, ph, fps, unit_ms / 1000, v["audio"]), check=True, cwd=work)
    subprocess.run(final_cmd("unit.mp4", "dub.wav", "captions.ass", str(out.resolve()), stereo=stereo, lead_ms=lead_ms,
                             loops=loops, total_s=total_ms / 1000, fps=fps), check=True, cwd=work)
    done = probe(out)
    res = {"out": str(out), "duration_s": round(done["dur_s"], 2), "bytes": out.stat().st_size,
           "size": f"{done['w']}x{done['h']}", "lang": lang, "stereo": stereo, "session": meta.get("session"),
           "stats": st, "on_picture": overlay_lines(st)}
    (work / "render.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", help="a folder under <DATA_DIR>/recordings")
    ap.add_argument("video", help="the source video the session was fed from")
    ap.add_argument("--lang", default="", help="which dubbed language; default: the recording's first")
    ap.add_argument("--stereo", default="split", choices=STEREO)
    ap.add_argument("--out", default="", help="default: <recording>/pitch_<lang>_<stereo>.mp4")
    ap.add_argument("--lead-s", type=float, default=0.0, help="the video's time at which the file's first frame was shown")
    ap.add_argument("--loops", type=int, default=1)
    ap.add_argument("--gap-ms", type=int, default=0)
    ap.add_argument("--offset-ms", type=int, default=0, help="a recording without the video's clock: session time of the file's start")
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()
    rec = Path(a.recording)
    lang = a.lang or json.loads((rec / "session.json").read_text(encoding="utf-8"))["langs"][0]
    try:
        res = render(rec, Path(a.video), lang, out=Path(a.out) if a.out else None, stereo=a.stereo, lead_s=a.lead_s,
                     loops=a.loops, gap_ms=a.gap_ms, offset_ms=a.offset_ms, height=a.height, fps=a.fps)
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"render failed: {e}")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
