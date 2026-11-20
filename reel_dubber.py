#!/usr/bin/env python3
"""
reel_dubber.py - Dub a Reel / Short / YouTube clip into Indian languages using Gnani AI.

Reference prototype for the Studio pipeline (see SPEC.md section 5). Port logic into
backend/app/studio/stages/ rather than editing this file.

Pipeline:
  video -> extract audio -> split vocals | background (Demucs)
        -> speech segments (Silero VAD, each <= 25s because Prisma REST takes max 30s)
        -> Prisma v3.0 STT (indic-auto, handles Hinglish)
        -> LLM translation (any OpenAI-compatible endpoint), keeps slang/brand terms
        -> Timbre v2.5 TTS, or cloned creator voice (vachana-vc-v1)
        -> time-fit each line into its original slot -> mix over background music
        -> dubbed MP4 + SRT subtitles per language

Usage:
  export GNANI_API_KEY=...            # from app.gnani.ai
  export LLM_BASE_URL=...             # any OpenAI-compatible endpoint
  export LLM_API_KEY=...
  export LLM_MODEL=...                # e.g. gemini-3.5-flash
  python reel_dubber.py my_reel.mp4 --langs ta-IN,bn-IN --clone --consent
"""
import argparse
import json
import os
import subprocess
import sys

import requests
from pydub import AudioSegment

GNANI_KEY = os.environ.get("GNANI_API_KEY")
GNANI = "https://api.vachana.ai"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

LANG_NAMES = {
    "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu", "bn-IN": "Bengali",
    "mr-IN": "Marathi", "kn-IN": "Kannada", "ml-IN": "Malayalam", "gu-IN": "Gujarati",
    "pa-IN": "Punjabi", "en-IN": "English",
}
AUDIO_CFG = {"sample_rate": 44100, "num_channels": 1, "sample_width": 2,
             "encoding": "linear_pcm", "container": "wav"}
DEFAULT_GLOSSARY = ["bro", "subscribe", "like", "share", "reel", "vlog", "OK", "clutch", "GG"]


def sh(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------- audio prep ----------
def extract_audio(video, out_wav, sr=44100):
    sh(["ffmpeg", "-y", "-i", video, "-vn", "-ac", "1", "-ar", str(sr), out_wav])


def separate(wav, workdir):
    """Vocals + background via Demucs so music/game sound survives the dub."""
    try:
        sh([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-o", workdir, wav])
        stem = os.path.join(workdir, "htdemucs", os.path.splitext(os.path.basename(wav))[0])
        return os.path.join(stem, "vocals.wav"), os.path.join(stem, "no_vocals.wav")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Demucs failed ({e}); dubbing without background music.")
        return wav, None


def speech_segments(vocals_wav, max_len=25.0, min_gap=0.35):
    """Speech regions in seconds, merged at short pauses, each <= max_len."""
    from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    model = load_silero_vad()
    audio = read_audio(vocals_wav, sampling_rate=16000)
    ts = get_speech_timestamps(audio, model, sampling_rate=16000, return_seconds=True)
    merged = []
    for t in ts:
        s, e = float(t["start"]), float(t["end"])
        if merged and s - merged[-1][1] < min_gap and e - merged[-1][0] <= max_len:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    out = []
    for s, e in merged:
        while e - s > max_len:
            out.append((s, s + max_len))
            s += max_len
        out.append((s, e))
    return out


# ---------- Gnani: STT ----------
def stt(clip_path, lang="indic-auto"):
    with open(clip_path, "rb") as f:
        r = requests.post(
            f"{GNANI}/stt/v3",
            headers={"X-API-Key-ID": GNANI_KEY},
            files={"audio_file": (os.path.basename(clip_path), f, "audio/wav")},
            data={"model": "prisma-v3.0", "language_code": lang},
            timeout=60,
        )
    r.raise_for_status()
    j = r.json()
    if not j.get("success"):
        raise RuntimeError(f"STT failed: {j}")
    return j.get("transcript", "").strip()


# ---------- LLM: translation ----------
def translate_all(lines, target, glossary):
    system = (
        f"You dub short Indian social-media videos. Translate each line into natural, spoken "
        f"{LANG_NAMES.get(target, target)}, the way a creator talks on camera, not textbook style. "
        f"Keep these words in English as-is: {', '.join(glossary)}. Keep brand names in English. "
        "Keep each line about the same spoken length as the source so it fits the same time slot. "
        "Return ONLY a JSON array of strings, same length and order as the input. No commentary."
    )
    r = requests.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
        json={"model": LLM_MODEL, "temperature": 0.3,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": json.dumps(lines, ensure_ascii=False)}]},
        timeout=180,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    # Reasoning models may think out loud first: keep only the JSON array.
    text = text[text.find("["): text.rfind("]") + 1]
    out = json.loads(text)
    if len(out) != len(lines):
        raise ValueError(f"LLM returned {len(out)} lines for {len(lines)} inputs")
    return [str(x) for x in out]


# ---------- Gnani: TTS / voice clone ----------
def clone_embedding(ref_wav):
    with open(ref_wav, "rb") as f:
        r = requests.post(f"{GNANI}/api/v1/tts/voice-clone/embeddings",
                          headers={"X-API-Key-ID": GNANI_KEY},
                          files={"audio_file": ("reference.wav", f, "audio/wav")}, timeout=120)
    r.raise_for_status()
    j = r.json()
    # Docs: {"success", "message", "data": {"voice_clone_embedding": {embedding, shape, dtype}}}
    return j.get("data", {}).get("voice_clone_embedding", j)


def tts(text, out_wav, lang, voice, embedding=None):
    if embedding:
        body = {"text": text, "model": "vachana-vc-v1", "audio_config": AUDIO_CFG,
                "speaker_embedding": embedding}
    else:
        body = {"text": text, "voice": voice, "model": "timbre-v2.5", "language": lang,
                "speed": 1.0, "audio_config": AUDIO_CFG}
    r = requests.post(f"{GNANI}/api/v1/tts/inference",
                      headers={"X-API-Key-ID": GNANI_KEY, "Content-Type": "application/json"},
                      json=body, timeout=120)
    r.raise_for_status()
    with open(out_wav, "wb") as f:
        f.write(r.content)


# ---------- timing + mixing ----------
def fit(clip_wav, slot_ms, tmp, max_speed=1.35):
    seg = AudioSegment.from_file(clip_wav)
    if slot_ms <= 0 or len(seg) <= slot_ms:
        return seg
    speed = min(len(seg) / slot_ms, max_speed)
    sh(["ffmpeg", "-y", "-i", clip_wav, "-filter:a", f"atempo={speed:.3f}", tmp])
    return AudioSegment.from_file(tmp)


def srt_time(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(path, segs, lines):
    with open(path, "w", encoding="utf-8") as f:
        for i, ((s, e), t) in enumerate(zip(segs, lines), 1):
            f.write(f"{i}\n{srt_time(s)} --> {srt_time(e)}\n{t}\n\n")


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Dub a short video into Indian languages with Gnani AI")
    ap.add_argument("video")
    ap.add_argument("--langs", default="ta-IN", help="comma-separated target codes, e.g. ta-IN,bn-IN,en-IN")
    ap.add_argument("--src", default="indic-auto", help="source language code for Prisma")
    ap.add_argument("--voice", default="Nalini", help="Timbre voice from the Voice Catalog (when not cloning)")
    ap.add_argument("--clone", action="store_true", help="dub in the speaker's own cloned voice")
    ap.add_argument("--consent", action="store_true", help="confirm the speaker consented to voice cloning")
    ap.add_argument("--glossary", default="", help="extra comma-separated words to keep in English")
    ap.add_argument("--no-separate", action="store_true", help="skip Demucs vocal/music split")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    if not GNANI_KEY:
        sys.exit("Set GNANI_API_KEY")
    if not (LLM_BASE_URL and LLM_MODEL):
        sys.exit("Set LLM_BASE_URL and LLM_MODEL (any OpenAI-compatible endpoint)")
    if a.clone and not a.consent:
        sys.exit("Voice cloning needs the speaker's consent. Re-run with --consent once you have it.")

    name = os.path.splitext(os.path.basename(a.video))[0]
    work = os.path.join(a.out, name, "work")
    os.makedirs(work, exist_ok=True)
    glossary = DEFAULT_GLOSSARY + [g.strip() for g in a.glossary.split(",") if g.strip()]

    full = os.path.join(work, "full.wav")
    extract_audio(a.video, full)
    duration_ms = len(AudioSegment.from_file(full))
    vocals, background = (full, None) if a.no_separate else separate(full, work)

    # Transcribe once and cache, so prompt experiments don't burn STT credits.
    cache = os.path.join(work, "transcript.json")
    if os.path.exists(cache):
        data = json.load(open(cache, encoding="utf-8"))
        segs, src_lines = [tuple(x) for x in data["segments"]], data["lines"]
        print(f"[cache] {len(segs)} segments loaded")
    else:
        segs = speech_segments(vocals)
        voc = AudioSegment.from_file(vocals).set_channels(1).set_frame_rate(16000)
        src_lines = []
        for i, (s, e) in enumerate(segs):
            clip = os.path.join(work, f"src_{i:03}.wav")
            voc[int(s * 1000):int(e * 1000)].export(clip, format="wav")
            src_lines.append(stt(clip, a.src))
            print(f"[stt] {s:6.2f}-{e:6.2f}  {src_lines[-1]}")
        json.dump({"segments": segs, "lines": src_lines}, open(cache, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    keep = [i for i, t in enumerate(src_lines) if t]
    segs = [segs[i] for i in keep]
    src_lines = [src_lines[i] for i in keep]
    if not segs:
        sys.exit("No speech found.")

    embedding = None
    if a.clone:
        voc = AudioSegment.from_file(vocals)
        ref = AudioSegment.empty()
        for s, e in segs:
            ref += voc[int(s * 1000):int(e * 1000)]
            if len(ref) >= 20_000:
                break
        ref_path = os.path.join(work, "clone_ref.wav")
        ref[:25_000].export(ref_path, format="wav")
        embedding = clone_embedding(ref_path)
        print("[clone] speaker embedding ready")

    bg = AudioSegment.from_file(background) if background else AudioSegment.silent(duration_ms)
    write_srt(os.path.join(a.out, name, f"{name}_source.srt"), segs, src_lines)

    for lang in [x.strip() for x in a.langs.split(",") if x.strip()]:
        lines = translate_all(src_lines, lang, glossary)
        dub = AudioSegment.silent(duration_ms, frame_rate=AUDIO_CFG["sample_rate"])
        for i, ((s, e), text) in enumerate(zip(segs, lines)):
            raw = os.path.join(work, f"{lang}_{i:03}.wav")
            tts(text, raw, lang, a.voice, embedding)
            next_start = segs[i + 1][0] if i + 1 < len(segs) else duration_ms / 1000
            slot_ms = int((next_start - s) * 1000)  # may spill into the pause after the line
            clip = fit(raw, slot_ms, os.path.join(work, f"{lang}_{i:03}_fit.wav"))
            dub = dub.overlay(clip, position=int(s * 1000))
            print(f"[{lang}] {text}")
        mixed = bg.overlay(dub)
        mix_path = os.path.join(work, f"mix_{lang}.wav")
        mixed.export(mix_path, format="wav")
        out_mp4 = os.path.join(a.out, name, f"{name}_{lang}.mp4")
        sh(["ffmpeg", "-y", "-i", a.video, "-i", mix_path, "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-shortest", out_mp4])
        write_srt(os.path.join(a.out, name, f"{name}_{lang}.srt"), segs, lines)
        print(f"[done] {out_mp4}")


if __name__ == "__main__":
    main()
