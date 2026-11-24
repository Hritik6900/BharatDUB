"""v1.1 WS5: the deploy kit of the v1 model servers, the voice and translation A/B kits, the QA server's speaker
model. Nothing here needs the GPU machine: the card is a stand-in `nvidia-smi`, the servers are fakes or stubs."""
import csv
import json
import os
import socket
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import numpy as np
import pytest

os.environ["V1_STUB"] = "1"
ENGINE = Path(__file__).resolve().parents[2] / "gpu_engine_v1"
for _p in (ENGINE, ENGINE / "deploy", ENGINE / "ab"):
    sys.path.insert(0, str(_p))

import kit  # noqa: E402
import maya_ab  # noqa: E402
import qa_server  # noqa: E402

from eval.v1 import llm_ab  # noqa: E402

FAKE_SMI = '''import os, sys
args = " ".join(sys.argv[1:])
if "--query-gpu=memory.used,memory.free,memory.total" in args:
    total = float(os.environ.get("FAKE_TOTAL_MB", "40960")); free = float(os.environ["FAKE_FREE_MB"])
    print("%d, %d, %d" % (total - free, free, total))
elif "--query-compute-apps" in args:
    print(os.environ.get("FAKE_APPS", ""))
else:
    sys.exit(9)          # anything else (a reset, a mode change) is not something the kit may ask for
'''


@pytest.fixture
def card(tmp_path, monkeypatch):
    """A stand-in nvidia-smi and the kit's folders in a scratch place. `card(free_gb)` sets the free memory."""
    smi = tmp_path / "fake_smi.py"
    smi.write_text(FAKE_SMI)
    monkeypatch.setenv("NVIDIA_SMI", str(smi))
    monkeypatch.setattr(kit, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(kit, "VENV_DIR", tmp_path / "venvs")

    def set_free(gb: float) -> None:
        monkeypatch.setenv("FAKE_FREE_MB", str(int(gb * 1024)))
    set_free(6.0)
    return set_free


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------- the memory rule

def test_memory_is_read_from_nvidia_smi_and_the_rule_is_free_minus_need_at_least_4():
    assert kit.parse_memory("34816, 6144, 40960\n") == {"used_gb": 34.0, "free_gb": 6.0, "total_gb": 40.0}
    assert kit.parse_memory("34816 MiB, 6144 MiB, 40960 MiB") == {"used_gb": 34.0, "free_gb": 6.0, "total_gb": 40.0}
    assert kit.parse_memory("") is None and kit.parse_memory("N/A, N/A, N/A") is None
    assert kit.memory_verdict(6.0, 4.0)[0] is False          # today's card: IndicF5 with batching does not fit
    assert kit.memory_verdict(8.0, 4.0)[0] is True           # exactly 4 GB left is allowed
    assert kit.memory_verdict(7.9, 4.0)[0] is False
    assert kit.memory_verdict(6.0, 0.0)[0] is True           # the QA server on CPU
    assert kit.memory_verdict(3.5, 0.0)[0] is False          # under 4 GB free: nothing new, not even a CPU server
    assert "6.0 GB - needed 4.0 GB = 2.0 GB" in kit.memory_verdict(6.0, 4.0)[1]
    assert kit.parse_apps("111, 4096\n222, 1024 MiB\nbad line\n") == {111: 4.0, 222: 1.0}


def test_the_kit_only_knows_its_own_ports_and_never_a_running_one():
    ports = [s["port"] for s in kit.SERVERS.values()]
    assert sorted(ports) == [9041, 9042, 9043, 9044, 9045] and set(ports) == set(kit.OWN_PORTS)
    assert not set(ports) & set(kit.PROTECTED_PORTS)
    for port in (3000, 8010, 3100, 8110, 9001, 9002, 9003, 9010, 9020, 9030, 9040):
        assert port in kit.PROTECTED_PORTS
    source = (ENGINE / "deploy" / "kit.py").read_text(encoding="utf-8")
    for word in ("pkill", "killall", "sudo ", "systemctl", "mps-control -d", "echo quit", "docker ", "--gpu-reset"):
        assert word not in source, word                       # nothing that reaches beyond its own process


def test_start_refuses_when_the_card_is_too_full_and_writes_nothing(card, capsys, tmp_path):
    card(6.0)
    assert kit.main(["start", "tts", "--dry-run"]) == 4
    out = capsys.readouterr().out
    assert "free 6.0 GB - needed 4.0 GB = 2.0 GB" in out and "REFUSED" in out and "would start" not in out
    assert kit.main(["start", "tts"]) == 4                    # the real start refuses the same way, before any setup
    assert not (tmp_path / "run").exists() and not (tmp_path / "venvs").exists()
    for name, free in (("maya", 13.1), ("transcribe", 13.9), ("big-llm", 17.9)):
        assert kit.main(["start", name, "--dry-run"]) == 4, name
    assert kit.main(["start", "big-llm", "--size", "31b", "--dry-run"]) == 4
    assert kit.main(["start", "tts", "--need-gb", "1.5", "--dry-run"]) == 0     # a measured, smaller need is accepted


def test_start_dry_run_prints_the_commands_when_there_is_room(card, capsys, tmp_path):
    card(24.0)
    assert kit.main(["start", "big-llm", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "free 24.0 GB - needed 14.0 GB = 10.0 GB" in out
    assert "google/gemma-4-12B-it-qat-w4a16-ct" in out and "--port 9044" in out and "--gpu-memory-utilization 0.350" in out
    assert "9020" not in out
    card(40.0)
    assert kit.main(["start", "big-llm", "--size", "31b", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "google/gemma-4-31B-it-qat-w4a16-ct" in out and "--gpu-memory-utilization 0.675" in out
    assert kit.main(["start", "maya", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "maya_server:app" in out and "--port 9042" in out and "MayaResearch/maya2-native" in out
    assert not (tmp_path / "run").exists()                    # a dry run leaves no file behind


def test_start_refuses_without_nvidia_smi_unless_the_server_needs_no_gpu(card, capsys, monkeypatch):
    monkeypatch.setattr(kit, "smi_path", lambda: None)
    assert kit.main(["start", "tts", "--dry-run"]) == 4
    assert "nvidia-smi gave no answer" in capsys.readouterr().out
    assert kit.main(["start", "qa", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "takes no GPU memory" in out and "qa_server:app" in out and "whl/cpu" in out


def test_start_never_replaces_something_that_already_answers(card, capsys, monkeypatch):
    card(30.0)
    monkeypatch.setattr(kit, "port_answers", lambda port, host="127.0.0.1": True)
    assert kit.main(["start", "qa"]) == 3
    assert "did not start it" in capsys.readouterr().out
    assert kit.read_pid("qa") is None


def test_argument_parsing_and_unknown_servers(card, capsys):
    with pytest.raises(SystemExit):
        kit.main(["start", "gemma"])                          # v0's servers are not in the kit's vocabulary
    with pytest.raises(SystemExit):
        kit.main(["stop", "9020"])
    with pytest.raises(SystemExit):
        kit.spec("big-llm", size="70b")
    with pytest.raises(SystemExit):
        kit.spec("big-llm", stub=True)
    assert kit.main([]) == 2
    assert kit.spec("tts", stub=True)["need_gb"] == 0.0
    assert kit.spec("big-llm", size="31b")["model"].endswith("31B-it-qat-w4a16-ct")


def test_the_qa_server_is_started_with_no_cuda_device(monkeypatch):
    monkeypatch.delenv("QA_DEVICE", raising=False)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    env = kit.launch_env(kit.spec("qa"), stub=False)
    assert env["CUDA_VISIBLE_DEVICES"] == "" and env["QA_DEVICE"] == "cpu"
    assert kit.launch_env(kit.spec("tts"), stub=False)["CUDA_VISIBLE_DEVICES"] == "0"      # a GPU server keeps the card
    assert kit.launch_env(kit.spec("tts", stub=True), stub=True)["CUDA_VISIBLE_DEVICES"] == ""
    monkeypatch.setenv("QA_DEVICE", "cuda")
    with pytest.raises(SystemExit):
        kit.spec("qa")                                        # on the card only with a stated need
    assert kit.spec("qa", need_gb=3.0)["need_gb"] == 3.0


# ---------------------------------------------------------------- start, smoke, stop of a real (stub) server

def test_start_smoke_stop_of_a_stub_server_and_only_its_own_process(card, capsys, monkeypatch, tmp_path):
    card(6.0)
    port = free_port()
    monkeypatch.setitem(kit.SERVERS["qa"], "port", port)
    monkeypatch.setattr(kit, "OWN_PORTS", (port,))
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        assert kit.main(["start", "qa", "--stub", "--python", sys.executable, "--wait", "90"]) == 0
        out = capsys.readouterr().out
        assert "READY" in out and "memory check" in out
        pid = kit.read_pid("qa")
        state = kit.read_state("qa")
        assert pid and kit.pid_alive(pid) and state["stub"] is True and state["free_before_gb"] == 6.0
        assert kit.main(["start", "qa", "--stub", "--python", sys.executable]) == 0        # a second start changes nothing
        assert "already running" in capsys.readouterr().out and kit.read_pid("qa") == pid

        assert kit.main(["smoke", "qa"]) == 0
        out = capsys.readouterr().out
        assert "RESULT: PASS (4 of 4 checks" in out and "PASS  health" in out and " ms " in out
        assert "GPU memory:" in out and "free before start 6.0 GB, now 6.0 GB (taken 0.0 GB)" in out

        assert kit.main(["stop", "qa"]) == 0
        out = capsys.readouterr().out
        assert "stopped qa (pid %d)" % pid in out and "Nothing else was touched" in out
        assert not kit.pid_alive(pid) and kit.read_pid("qa") is None
        assert bystander.poll() is None                        # the process beside it is still running
        assert kit.main(["stop", "qa"]) == 0
        assert "nothing is stopped" in capsys.readouterr().out
    finally:
        pid = kit.read_pid("qa")
        if pid and kit.pid_alive(pid):
            kit.end_own(pid, 15)
        bystander.terminate()


def test_stop_leaves_a_process_alone_that_is_not_the_kit_s_server(card, capsys, monkeypatch):
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        kit.RUN_DIR.mkdir(parents=True)
        kit.paths("tts")["pid"].write_text(str(other.pid))    # a stale pid file: the number now belongs to someone else
        monkeypatch.setattr(kit, "pid_cmdline", lambda pid: "python -m uvicorn voice_engine_live:app --port 9001")
        assert kit.ours("tts", other.pid, kit.pid_cmdline) is False
        monkeypatch.setattr(kit, "ours", lambda name, pid, cmdline=None: False)
        assert kit.main(["stop", "tts"]) == 0
        assert "Nothing stopped" in capsys.readouterr().out
        assert other.poll() is None and kit.read_pid("tts") is None
    finally:
        other.terminate()


def test_ours_checks_the_port_in_the_command_line():
    me = os.getpid()
    assert kit.ours("tts", me, lambda pid: "/x/python -m uvicorn tts_server:app --host 127.0.0.1 --port 9041") is True
    assert kit.ours("tts", me, lambda pid: "/x/python -m uvicorn voice_engine_live:app --host 127.0.0.1 --port 9001") is False
    assert kit.ours("big-llm", me, lambda pid: "vllm serve google/gemma-4-E4B-it --port 9020") is False
    assert kit.ours("tts", 0, lambda pid: "--port 9041") is False


# ---------------------------------------------------------------- the smoke client against fake servers

class Fake(BaseHTTPRequestHandler):
    """One fake for every kind of server; `mode` on the server object makes it misbehave."""

    def log_message(self, *a):  # noqa: ANN002
        pass

    def _send(self, code: int, body: bytes, headers: dict | None = None, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        mode = self.server.mode
        if self.path == "/health":
            self._send(200, json.dumps({"ok": mode != "unhealthy", "model": "fake", "stub": True, "gpu_gb": 0}).encode())
        elif self.path == "/v1/models":
            self._send(200, json.dumps({"data": [{"id": "big"}]}).encode())
        elif self.path == "/api/live/sessions":
            self._send(200, json.dumps([{"id": "s1", "status": "live" if mode == "live" else "ended"}]).encode())
        elif self.path == "/gpu":
            self._send(200, json.dumps({"gpus": [], "processes": []}).encode())
        else:
            self._send(404, b"{}")

    def do_POST(self) -> None:  # noqa: N802
        mode = self.server.mode
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.seen.append((self.path, body))
        if self.path == "/ref":
            self._send(200, json.dumps({"ok": True, "version": 1}).encode())
        elif self.path == "/tts":
            req = json.loads(body)
            if mode == "silent":
                pcm = b"\0\0" * 24000
            elif mode == "no-english" and req["lang"] == "en-IN":
                return self._send(422, b'{"detail":"language not spoken"}')
            else:
                pcm = (np.sin(np.arange(24000) / 10) * 8000).astype("<i2").tobytes()
            self._send(200, pcm, {"X-Sample-Rate": "24000", "X-Synth-Ms": "12"}, "application/octet-stream")
        elif self.path == "/stt":
            self._send(200, json.dumps({"text": "", "lang": "hi-IN", "ms": 5}).encode())
        elif self.path == "/v1/chat/completions":
            text = "hello" if mode == "latin" else "இன்று புதிய விளையாட்டு"
            self._send(200, json.dumps({"choices": [{"message": {"content": text}}]}).encode())
        else:
            self._send(404, b"{}")


@pytest.fixture
def fake():
    servers = []

    def make(mode: str = "ok") -> str:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        srv.mode, srv.seen = mode, []
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return "http://127.0.0.1:%d" % srv.server_address[1]
    make.servers = servers
    yield make
    for s in servers:
        s.shutdown()
        s.server_close()


def test_smoke_passes_and_fails_with_timing_and_says_when_the_card_cannot_be_read(card, fake, capsys, monkeypatch):
    assert kit.main(["smoke", "tts", "--url", fake()]) == 0
    out = capsys.readouterr().out
    assert "PASS  tts hi-IN" in out and "PASS  tts ta-IN" in out and "1.00 s of audio at 24000 Hz" in out
    assert "RESULT: PASS (4 of 4 checks" in out and "GPU memory: free now 6.0 GB of 40.0 GB" in out
    assert kit.main(["smoke", "maya", "--url", fake()]) == 0
    assert "PASS  tts en-IN" in capsys.readouterr().out       # English is part of Maya's test, not of IndicF5's
    assert kit.main(["smoke", "tts", "--url", fake("silent")]) == 1
    out = capsys.readouterr().out
    assert "FAIL  tts hi-IN" in out and "silent" in out and "RESULT: FAIL" in out
    assert kit.main(["smoke", "tts", "--url", fake("unhealthy")]) == 1
    assert "FAIL  health" in capsys.readouterr().out
    assert kit.main(["smoke", "transcribe", "--url", fake()]) == 0
    assert kit.main(["smoke", "big-llm", "--url", fake()]) == 0
    assert "replied in Tamil" in capsys.readouterr().out
    assert kit.main(["smoke", "big-llm", "--url", fake("latin")]) == 1
    assert "no Tamil letters" in capsys.readouterr().out
    assert kit.main(["smoke", "qa", "--url", "http://127.0.0.1:%d" % free_port()]) == 1    # nothing listens there
    assert "RESULT: FAIL" in capsys.readouterr().out
    monkeypatch.setattr(kit, "smi_path", lambda: None)
    assert kit.main(["smoke", "transcribe", "--url", fake()]) == 0
    assert "GPU memory: not readable here" in capsys.readouterr().out


def test_smoke_reports_what_the_server_took_on_the_card(card, monkeypatch):
    kit.RUN_DIR.mkdir(parents=True)
    kit.paths("tts")["pid"].write_text("4242")
    kit.paths("tts")["state"].write_text(json.dumps({"free_before_gb": 12.0}))
    card(8.1)
    monkeypatch.setenv("FAKE_APPS", "4242, 3994\n777, 18000")
    monkeypatch.setattr(kit, "group_pids", lambda pgid: [pgid])
    line = kit.memory_report("tts")
    assert "pid 4242) hold 3.9 GB" in line and "free before start 12.0 GB, now 8.1 GB (taken 3.9 GB)" in line
    assert "headroom ok" in line
    card(3.0)
    assert "headroom TOO SMALL" in kit.memory_report("tts")


# ---------------------------------------------------------------- the voice A/B kit

def store_with_voice(tmp_path: Path, consent: str | None) -> Path:
    (tmp_path / "voices").mkdir(exist_ok=True)
    (tmp_path / "voices" / "v.wav").write_bytes(kit.tone_wav(1.0))
    store = tmp_path / "local_db.json"
    store.write_text(json.dumps({"voice_profiles": [{"id": "vp1", "consent_at": consent, "ref_path": "v.wav",
                                                     "ref_text": "namaste doston"}]}), encoding="utf-8")
    return store


def test_the_twenty_voice_lines():
    lines = maya_ab.read_lines(ENGINE / "ab" / "voice_lines.tsv")
    assert len(lines) == 20 and len({ln["id"] for ln in lines}) == 20
    by_lang = {lang: sum(1 for ln in lines if ln["lang"] == lang) for lang in {ln["lang"] for ln in lines}}
    assert by_lang["en-IN"] >= 5 and set(by_lang) == {"hi-IN", "ta-IN", "bn-IN", "pa-IN", "en-IN"}
    for ln in lines:
        latin = sum(1 for ch in ln["text"] if "a" <= ch.lower() <= "z")
        assert (latin > 10) == (ln["lang"] == "en-IN"), ln    # Indian lines in their own letters, English in Latin


def test_voice_ab_needs_a_profile_with_consent(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        maya_ab.consented_voice(store_with_voice(tmp_path, None), "vp1", None)
    assert "REFUSED" in str(e.value) and "consent" in str(e.value)
    with pytest.raises(SystemExit):
        maya_ab.consented_voice(store_with_voice(tmp_path, "2026-11-25T00:00:00Z"), "someone-else", None)
    with pytest.raises(SystemExit):
        maya_ab.main(["--out", str(tmp_path / "o")])          # no way in without a store and a profile
    v = maya_ab.consented_voice(store_with_voice(tmp_path, "2026-11-25T00:00:00Z"), "vp1", None)
    assert v["text"] == "namaste doston" and v["sample"].name == "v.wav"


def test_voice_ab_writes_two_folders_of_same_named_files_and_blind_pairs(tmp_path, fake, capsys):
    store = store_with_voice(tmp_path, "2026-11-25T00:00:00Z")
    f5, maya, quiet = fake("no-english"), fake(), fake()
    out = tmp_path / "ab"
    args = ["--store", str(store), "--voice", "vp1", "--out", str(out), "--indicf5", f5, "--maya", maya, "--busy", quiet]
    assert maya_ab.main(args + ["--dry-run"]) == 0 and not out.exists()
    assert maya_ab.main(args) == 0
    a, b = sorted(p.name for p in (out / "indicf5").iterdir()), sorted(p.name for p in (out / "maya").iterdir())
    assert len(b) == 20 and len(a) == 14 and set(a) <= set(b)          # this fake IndicF5 refuses the six English lines
    with wave.open(str(out / "maya" / "en01.wav")) as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1 and w.getnframes() == 24000
    m = json.loads((out / "pairs" / "pairs.json").read_text(encoding="utf-8"))
    assert m["systems"] == ["indicf5", "maya"] and len(m["pairs"]) == 14 and len(m["missing"]) == 6
    for p in m["pairs"]:
        assert set(p) >= {"id", "lang", "text", "a", "b", "a_system", "b_system"}
        assert {p["a_system"], p["b_system"]} == {"indicf5", "maya"}
        assert (out / "pairs" / p["a"]).is_file() and (out / "pairs" / p["b"]).is_file()
        assert "maya" not in p["a"] and "indicf5" not in p["a"]        # the file names do not give the system away
    assert len({p["a_system"] for p in m["pairs"]}) == 2                # which one is A changes from pair to pair
    timing = json.loads((out / "timing.json").read_text(encoding="utf-8"))
    assert len(timing["systems"]["maya"]["lines"]) == 20 and len(timing["systems"]["indicf5"]["failed"]) == 6
    sent = [json.loads(body) for path, body in fake.servers[0].seen if path == "/tts"]
    assert all(r["nfe"] == 16 and r["speed"] == 1.0 for r in sent)
    again = maya_ab.build_pairs(out, maya_ab.read_lines(ENGINE / "ab" / "voice_lines.tsv"), seed=1)
    assert again["pairs"] == m["pairs"]                                 # the same seed gives the same sides
    assert maya_ab.main(["--out", str(out), "--pairs-only"]) == 0


def test_voice_ab_refuses_while_a_stream_is_live(tmp_path, fake, capsys):
    store = store_with_voice(tmp_path, "2026-11-25T00:00:00Z")
    f5, maya = fake(), fake()
    code = maya_ab.main(["--store", str(store), "--voice", "vp1", "--out", str(tmp_path / "ab"), "--indicf5", f5,
                         "--maya", maya, "--busy", fake("live")])
    assert code == 3 and "a stream is live" in capsys.readouterr().out
    assert not fake.servers[0].seen and not fake.servers[1].seen       # not one line was sent


# ---------------------------------------------------------------- the translation A/B

def test_translation_set_and_rule_are_fixed():
    lines = llm_ab.fixed_lines()
    assert len(lines) == 40 and len({ln["id"] for ln in lines}) == 40
    assert sum(1 for ln in lines if ln["id"].startswith("stream")) == 16
    assert llm_ab.WIN_RULE == {"prefer_share": 0.60, "decided_min": 40, "lang_share_min": 0.50, "lang_decided_min": 10,
                               "length_ratio_max": 1.10, "studio_line_s_max": 2.0, "live_p50_s_max": 0.6,
                               "live_p95_s_max": 1.0}


def fake_llm(reply) -> httpx.AsyncClient:  # noqa: ANN001
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": reply(body)}}]})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_translation_ab_runs_both_models_and_builds_a_blind_sheet(tmp_path):
    lines = llm_ab.fixed_lines()[:8]

    def tamil(extra: str):
        def reply(body: dict) -> str:
            user = body["messages"][1]["content"]
            n = len(json.loads(user)) if user.startswith("[") else 1
            return json.dumps(["இன்று புதிய விளையாட்டு" + extra] * n, ensure_ascii=False) if user.startswith("[") \
                else "இன்று புதிய விளையாட்டு" + extra
        return reply
    a = await llm_ab.run_model(llm_ab.translator("http://a/v1", "local", fake_llm(tamil(""))), lines, ("ta-IN",), "batch")
    b = await llm_ab.run_model(llm_ab.translator("http://b/v1", "big", fake_llm(tamil(" நண்பர்களே"))), lines, ("ta-IN",), "batch")
    assert len(a["results"]) == 8 and len(a["calls"]) == 1 and a["calls"][0]["lines"] == 8
    assert all(r["out"].startswith("இன்று") for r in a["results"])
    live = await llm_ab.run_model(llm_ab.translator("http://a/v1", "local", fake_llm(tamil(""))), lines[:3], ("ta-IN",), "live")
    assert len(live["calls"]) == 3 and live["mode"] == "live"
    auto = llm_ab.make_sheet(a, b, ("current", "big12"), tmp_path)
    assert auto["pairs"] == 8 and auto["a"]["wrong_script_or_latin"] == 0 and auto["length_ratio_b_over_a"] > 1.3
    key = json.loads((tmp_path / "key.json").read_text(encoding="utf-8"))
    with (tmp_path / "side_by_side.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 8 and all(r["better"] == "" for r in rows)
    assert "current" not in (tmp_path / "side_by_side.csv").read_text(encoding="utf-8-sig")
    assert "big12" not in (tmp_path / "side_by_side.md").read_text(encoding="utf-8")
    assert len({key["pairs"][r["pair"]]["X"] for r in rows}) == 2       # which model is X changes from line to line
    for r in rows:                                                      # the key really says who wrote X
        assert r["X"].endswith("நண்பர்களே") == (key["pairs"][r["pair"]]["X"] == "big12")
    # the reader votes for the longer line every time: all eight votes go to big12
    for r in rows:
        r["better"] = "X" if r["X"].endswith("நண்பர்களே") else "Y"
    with (tmp_path / "side_by_side.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert llm_ab.read_votes(tmp_path / "side_by_side.csv", key) == {"ta-IN": {"a": 0, "b": 8, "same": 0}}


def auto_numbers(**b) -> dict:  # noqa: ANN003
    base = {"mode": "batch", "empty": 0, "wrong_script_or_latin": 1, "line_s_median": 0.9, "line_s_p95": 1.4}
    return {"a": dict(base, name="current"), "b": dict(base, name="big12", **b), "length_ratio_b_over_a": b.pop("ratio", 1.02)}


def test_translation_verdict_follows_the_rule():
    good = {lang: {"a": 5, "b": 12, "same": 23} for lang in llm_ab.LANGS}             # 36 of 51 decided = 71%
    assert llm_ab.verdict(good, auto_numbers())["wins"] is True
    close = {lang: {"a": 8, "b": 9, "same": 23} for lang in llm_ab.LANGS}             # 53%: under 60%
    assert llm_ab.verdict(close, auto_numbers())["wins"] is False
    one_bad = dict(good, **{"bn-IN": {"a": 9, "b": 6, "same": 25}})                   # one language under half
    v = llm_ab.verdict(one_bad, auto_numbers())
    assert v["wins"] is False and [c for c in v["checks"] if c["check"] == "preferred in bn-IN"][0]["ok"] is False
    few = {lang: {"a": 1, "b": 4, "same": 35} for lang in llm_ab.LANGS}               # 15 decided: not enough to say
    assert llm_ab.verdict(few, auto_numbers())["wins"] is None
    assert llm_ab.verdict({}, auto_numbers())["wins"] is None
    assert llm_ab.verdict(good, auto_numbers(wrong_script_or_latin=3))["wins"] is False   # more unreadable lines
    assert llm_ab.verdict(good, auto_numbers(empty=1))["wins"] is False
    assert llm_ab.verdict(good, auto_numbers(line_s_median=2.4))["wins"] is False         # too slow for Studio
    long = auto_numbers()
    long["length_ratio_b_over_a"] = 1.2
    assert llm_ab.verdict(good, long)["wins"] is False                                    # longer lines, later dub
    live = auto_numbers(mode="live", line_s_median=0.5, line_s_p95=0.9)
    v = llm_ab.verdict(good, live)
    assert v["fit_for_live"] is True and v["wins"] is None        # live mode says nothing about Studio speed
    assert llm_ab.verdict(good, auto_numbers(mode="live", line_s_median=0.8, line_s_p95=1.5))["fit_for_live"] is False


# ---------------------------------------------------------------- the QA server's speaker model

class FakeSpeaker:
    """Stands in for the speaker model: the 'voice' is how loud the clip is in three bands of its spectrum."""

    def __init__(self) -> None:
        self.calls = 0

    def encode_batch(self, wavs):  # noqa: ANN001, ANN201
        import torch
        self.calls += 1
        spec = torch.abs(torch.fft.rfft(wavs[0]))
        n = spec.shape[0] // 3
        return torch.stack([spec[:n].sum(), spec[n:2 * n].sum(), spec[2 * n:].sum()]).reshape(1, 1, 3)


class FakeWhisper:
    def transcribe(self, path, language=None, beam_size=5, vad_filter=False):  # noqa: ANN001, ANN201
        seg = type("Seg", (), {"text": " namaste doston "})
        return [seg], None


def wav_bytes(hz: float, seconds: float = 2.0) -> bytes:
    return kit.tone_wav(seconds, hz=hz)


def test_only_a_speaker_model_open_to_commercial_use_is_loaded(monkeypatch):
    assert qa_server.SPK_MODEL == "speechbrain/spkrec-ecapa-voxceleb"
    assert qa_server.speaker_licence() == ("Apache-2.0", True) and qa_server.speaker_allowed()
    assert qa_server.speaker_licence("Jenthe/ECAPA2") == ("CC-BY-NC-4.0", False)
    assert not qa_server.speaker_allowed("Jenthe/ECAPA2")
    assert qa_server.speaker_licence("someone/unknown-model") == ("not checked", False)
    assert not qa_server.speaker_allowed("someone/unknown-model")
    loaded = []
    monkeypatch.setattr(qa_server, "_load_speaker", lambda: loaded.append(1) or FakeSpeaker())
    monkeypatch.setattr(qa_server, "HEAR", False)
    monkeypatch.setattr(qa_server, "speaker", None)
    monkeypatch.setitem(qa_server.state, "speaker_refused", "")
    monkeypatch.setattr(qa_server, "SPK_MODEL", "Jenthe/ECAPA2")
    qa_server._load()
    assert not loaded and qa_server.speaker is None and "CC-BY-NC-4.0" in qa_server.state["speaker_refused"]
    monkeypatch.setattr(qa_server, "ALLOW_NONCOMMERCIAL", True)       # a measurement that ships nothing may say so
    qa_server._load()
    assert loaded == [1] and qa_server.speaker is not None


async def test_qa_server_compares_voices_on_cpu_with_a_fake_model(monkeypatch):
    spk = FakeSpeaker()
    monkeypatch.setattr(qa_server, "STUB", False)
    monkeypatch.setattr(qa_server, "speaker", spk)
    monkeypatch.setattr(qa_server, "whisper", FakeWhisper())
    monkeypatch.setitem(qa_server.state, "speaker_refused", "")
    low, low2, high = wav_bytes(200), wav_bytes(210), wav_bytes(6000)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=qa_server.app), base_url="http://qa") as c:
        same = (await c.post("/similarity", files={"audio": ("a.wav", low), "ref": ("b.wav", low)})).json()
        near = (await c.post("/similarity", files={"audio": ("a.wav", low), "ref": ("b.wav", low2)})).json()
        far = (await c.post("/similarity", files={"audio": ("a.wav", low), "ref": ("b.wav", high)})).json()
        assert same["similarity"] == 1.0 and near["similarity"] > 0.9 > far["similarity"]
        assert same["model"] == "speechbrain/spkrec-ecapa-voxceleb" and isinstance(same["ms"], int)
        assert spk.calls == 6
        r = (await c.post("/score", data={"text": "namaste doston", "lang": "hi-IN"},
                          files={"audio": ("a.wav", low), "ref": ("b.wav", high)})).json()
        assert r["heard"] == "namaste doston" and r["backcheck"] == 1.0 and r["similarity"] == far["similarity"]
        short = (await c.post("/similarity", files={"audio": ("a.wav", wav_bytes(200, 0.3)), "ref": ("b.wav", low)})).json()
        assert short["similarity"] is None                              # under half a second: no figure, not a guess
        h = (await c.get("/health")).json()
        assert h["ok"] and h["device"] == "cpu" and h["speaker_licence"] == "Apache-2.0"
        assert h["speaker_commercial_use"] is True and h["speaker_loaded"] is True and h["compares"] == 4
        monkeypatch.setattr(qa_server, "speaker", None)
        monkeypatch.setitem(qa_server.state, "speaker_refused", "refused: licence")
        assert (await c.post("/similarity", files={"audio": ("a.wav", low), "ref": ("b.wav", low)})).status_code == 503
        r = (await c.post("/score", data={"text": "namaste doston", "lang": "hi-IN"},
                          files={"audio": ("a.wav", low), "ref": ("b.wav", high)})).json()
        assert r["backcheck"] == 1.0 and r["similarity"] is None       # words are still scored without a speaker model


async def test_qa_stub_still_answers_as_before_and_has_the_new_call():
    assert qa_server.STUB is True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=qa_server.app), base_url="http://qa") as c:
        tone = wav_bytes(200)
        r = (await c.post("/score", data={"text": "namaste doston", "lang": "hi-IN"},
                          files={"audio": ("a.wav", tone), "ref": ("b.wav", tone)})).json()
        assert r["heard"] == "namaste doston" and r["backcheck"] == 1.0 and r["similarity"] == 0.5
        assert (await c.post("/similarity", files={"audio": ("a.wav", tone), "ref": ("b.wav", tone)})).json()["similarity"] == 1.0
        h = (await c.get("/health")).json()
        assert h["ok"] is True and h["stub"] is True and h["model"] == "large-v3-turbo"


def test_the_kit_s_scripts_are_plain_wrappers():
    for name in ("start", "smoke", "stop"):
        text = (ENGINE / "deploy" / f"{name}.sh").read_text(encoding="utf-8")
        assert f'kit.py" {name} "$@"' in text and "\r" not in text
    assert time.time() > 0
