"""Runs ON the GPU machine: writes voice_engine_live.py = voice_engine.py plus, per request, an optional `speed`
and `fmt` ("opus" = OGG/Opus instead of raw PCM, about a tenth of the bytes).
The original file and the engine already running on port 9000 are not touched."""
from pathlib import Path

src = Path.home() / "voice_engine" / "voice_engine.py"
s = src.read_text(encoding="utf-8")


def sub(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, (s.count(old), old[:60])
    s = s.replace(old, new)


sub("def _synth(rep: dict, text: str, ref_path: str, ref_text: str) -> np.ndarray:",
    "def _synth(rep: dict, text: str, ref_path: str, ref_text: str, speed: float = 1.0) -> np.ndarray:")
sub('mel_spec_type="vocos", nfe_step=NFE, show_info=quiet, device="cuda")',
    'mel_spec_type="vocos", nfe_step=NFE, show_info=quiet, device="cuda", speed=speed)')
sub('mel_spec_type="vocos", nfe_step=NFE, show_info=quiet)\n',
    'mel_spec_type="vocos", nfe_step=NFE, show_info=quiet, speed=speed)\n')
sub('    lang: str = ""\n',
    '    lang: str = ""\n    speed: float = 1.0   # < 1 = slower speech (f5 duration scale)\n'
    '    fmt: str = "pcm"     # "opus" = OGG/Opus\n')
sub('_synth, rep, req.text, ref["path"], ref["text"])',
    '_synth, rep, req.text, ref["path"], ref["text"], max(0.4, min(1.5, req.speed)))')
sub('    return Response(content=_normalize(wave), media_type="application/octet-stream", headers={',
    '    return Response(content=_encode(wave, req.fmt), media_type="application/octet-stream", headers={')
sub('"X-Ref-Version": str(ref["version"]),',
    '"X-Ref-Version": str(ref["version"]), "X-Speed": str(req.speed), "X-Format": "opus" if req.fmt == "opus" else "pcm",')
sub('@app.on_event("startup")',
    'def _encode(a: np.ndarray, fmt: str) -> bytes:\n'
    '    pcm = _normalize(a)\n'
    '    if fmt != "opus":\n'
    '        return pcm\n'
    '    buf = io.BytesIO()\n'
    '    sf.write(buf, np.frombuffer(pcm, dtype=np.int16), SR, format="OGG", subtype="OPUS")\n'
    '    return buf.getvalue()\n\n\n'
    '@app.on_event("startup")')
out = src.with_name("voice_engine_live.py")
out.write_text(s, encoding="utf-8")
print("wrote", out)
