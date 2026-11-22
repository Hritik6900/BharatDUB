"""v1 trace: records per Live phrase and Studio line, and the numbers computed from them."""
import json

import pytest

from app.config import get_settings
from app.v1 import metrics, trace


@pytest.fixture
def traced(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "data_dir", str(tmp_path))
    monkeypatch.setattr(s, "v1_trace", True)
    return tmp_path


def _phrase(seq: int, first: int, late: int, **marks):
    t = {"t_speech_end": 1000 * seq, "t_stt_final": 1000 * seq + 400,
         "t_translate_start:ta-IN": 1000 * seq + 410, "t_translated:ta-IN": 1000 * seq + 900,
         "t_first_audio:ta-IN": 1000 * seq + first, "t_heard:ta-IN": 1000 * seq + first + 300,
         "late:ta-IN": late, "clone:ta-IN": 1, "gpu:ta-IN": 1, "gpu_ms:ta-IN": 450, "tts_chars:ta-IN": 40}
    t.update(marks)
    return {"src_text": "aaj hum naya game khelenge", "t_speech_ms": 1000 * seq - 800, "timings": t}


def test_live_phrase_record_and_summary(traced):
    row = {"engine": "gpu"}
    prov = {"stt": "GnaniSTT>GpuSTT", "llm": "LocalLLM>OpenAILLM"}
    trace.live_phrase("abcdef123456", row, 1, _phrase(1, 2000, 100), prov)
    trace.live_phrase("abcdef123456", row, 2, _phrase(2, 3000, 1500, **{"llm_fb:ta-IN": 1}), prov)
    trace.live_phrase("abcdef123456", row, 3, {"src_text": "ok", "t_speech_ms": 2500, "timings": {
        "t_speech_end": 3000, "skipped:ta-IN": "late"}}, prov)
    trace.live_played("abcdef123456", 1, "ta-IN", 200)
    files = list((traced / "trace").glob("trace-*.jsonl"))
    assert len(files) == 1
    recs = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert [r["kind"] for r in recs] == ["live_phrase", "live_phrase", "live_phrase", "live_played"]
    first = recs[0]
    assert first["trace_id"] == "abcdef12-1-ta-IN" and first["first_audio_ms"] == 2000 and first["translate_ms"] == 490
    assert first["tts"] == "gpu_voice" and first["fallback"] == {"stt": False, "llm": False, "tts": False}
    assert first["gpu_s"] == pytest.approx(0.45 + 0.49)   # the voice engine's own time + translation on our GPU
    assert recs[1]["fallback"]["llm"] is True and recs[1]["gpu_s"] == pytest.approx(0.45)

    out = metrics.live_summary(trace.read(1), get_settings())
    assert out["phrases"] == 3 and out["spoken"] == 2 and out["skipped_late"] == 1
    assert out["first_audio_p50_ms"] in (2000, 2500, 3000)
    assert out["on_time_pct"] == 50.0 and out["within_1s_pct"] == 50.0
    assert out["fallback_pct"]["llm"] == pytest.approx(33.3)
    assert out["viewer_reports"] == 1 and out["viewer_within_1s_pct"] == 100.0
    assert out["cost"]["per_minute"] is None and "gpu" in out["cost"]["rates_missing"]   # no rate set, no figure


def test_cost_only_for_rates_that_are_set(traced, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "v1_gpu_rate_per_hour", 3.6)
    usage = {"gpu_seconds": 100.0, "hosted_stt_minutes": 2.0, "hosted_tts_chars": 500, "hosted_llm_calls": 10}
    c = metrics.cost(usage, 2.0, s)
    assert c["parts"]["gpu"] == pytest.approx(0.1) and c["parts"]["hosted_stt"] is None
    assert c["per_minute"] == pytest.approx(0.05) and c["rates_set"] == ["gpu"]


def test_studio_line_and_job(traced):
    trace.studio_line("job12345678", "ta-IN", 0, mode="studio_hq", speed=1.1, backcheck=0.95, flagged=False, gpu_s=1.5)
    trace.studio_line("job12345678", "ta-IN", 1, mode="studio_hq", speed=1.3, backcheck=0.6, flagged=True)
    trace.studio_job("job12345678", mode="studio_hq", duration_s=60.0, langs=["ta-IN"], total_s=90.0,
                     usage={"tts_chars": 400, "llm_calls": 3, "stt_audio_s": 55.0})
    out = metrics.studio_summary(trace.read(1), get_settings())
    assert out["lines"] == 2 and out["flagged"] == 1 and out["jobs"] == 1
    assert out["backcheck_mean_pct"] == 77.5 and out["speed_max"] == 1.3 and out["within_115_pct"] == 50.0
    assert out["usage"]["dubbed_minutes"] == 1.0 and out["turnaround_p50_s"] == 90


def test_provider_name():
    class A: ...
    class Pair:
        def __init__(self): self.first, self.second = A(), A()
    assert trace.provider_name(Pair()) == "A>A" and trace.provider_name(None) == "none"
