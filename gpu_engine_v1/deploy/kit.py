#!/usr/bin/env python3
"""Deploy kit for the v1 model servers (ports 9041-9045). Runs on the GPU machine; needs only Python 3.8+.

    python3 deploy/kit.py start  <server> [--stub] [--dry-run] [--python PATH] [--need-gb N] [--skip-install]
    python3 deploy/kit.py smoke  <server> [--url http://127.0.0.1:PORT]
    python3 deploy/kit.py stop   <server>
    python3 deploy/kit.py status

    servers: qa (9045, CPU) | tts (9041) | maya (9042) | transcribe (9043) | big-llm (9044; --size 12b|31b)

What it will and will not do:
  * `start` reads `nvidia-smi` first and refuses unless (free memory - the server's need) >= 4 GB.
  * It binds only 9041-9045. A port that already answers is left alone: `start` refuses, nothing is replaced.
  * It never starts, stops or configures CUDA MPS. If MPS runs, it says so and leaves it as it is.
  * It never touches the engines on 9001-9003, 9010, 9020, 9030, 9040, or anything it did not start itself.
  * `stop` ends only the process whose id is in this kit's own pid file (`run/<server>.pid`), and only after
    checking that this process is still the server the kit started.
  * No sudo, no system packages, no Docker. Each server gets its own Python environment under `.venvs/`.
"""
from __future__ import annotations

import argparse
import array
import io
import json
import math
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ENGINE_DIR = HERE.parent
RUN_DIR = Path(os.environ.get("V1_KIT_RUN_DIR", str(ENGINE_DIR / "run")))
VENV_DIR = Path(os.environ.get("V1_KIT_VENV_DIR", str(ENGINE_DIR / ".venvs")))
MODEL_CACHE = os.environ.get("V1_MODEL_CACHE", str(Path.home() / "bharatdb-v1-models"))

HEADROOM_GB = 4.0
OWN_PORTS = (9041, 9042, 9043, 9044, 9045)
# What runs today and is never to be bound, stopped or restarted by this kit.
PROTECTED_PORTS = (3000, 3100, 8010, 8110, 9001, 9002, 9003, 9010, 9020, 9030, 9040)

BIG_LLM = {  # size -> (Hugging Face id, GB the server is given on the card)
    "12b": ("google/gemma-4-12B-it-qat-w4a16-ct", 14.0),
    "31b": ("google/gemma-4-31B-it-qat-w4a16-ct", 27.0),
}

# need_gb: what the server is expected to take on the card. None of these was measured: tts is an estimate from
# v0's engines, maya and transcribe are their model cards' figures (the peak while loading), big-llm is the
# share vLLM is told to take (weights on disk 10.3 GB for 12B, 23.3 GB for 31B, plus its cache).
SERVERS: Dict[str, Dict[str, Any]] = {
    "qa": {"port": 9045, "need_gb": 0.0, "app": "qa_server:app", "health": "/health", "wait_s": 900,
           "torch_index": "https://download.pytorch.org/whl/cpu", "torch": ["torch==2.5.1", "torchaudio==2.5.1"],
           "reqs": "requirements.qa.txt",
           "env": {"QA_DEVICE": "cpu"}},
    "tts": {"port": 9041, "need_gb": 4.0, "app": "tts_server:app", "health": "/health", "wait_s": 600,
            "torch_index": "https://download.pytorch.org/whl/cu124", "torch": ["torch==2.5.1", "torchaudio==2.5.1"],
            "reqs": "deploy/requirements.tts.txt",
            "env": {"NFE": "12", "BATCH_MAX": "4", "BATCH_WAIT_MS": "15"}},
    "maya": {"port": 9042, "need_gb": 9.2, "app": "maya_server:app", "health": "/health", "wait_s": 900,
             "git": ("https://github.com/MayaResearch/maya2-native", "MAYA_COMMIT"),
             "pip_extra": ["--extra-index-url", "https://download.pytorch.org/whl/cu128"],
             "reqs": "deploy/requirements.maya.txt", "env": {"MAYA_SEATS": "1"}},
    "transcribe": {"port": 9043, "need_gb": 10.0, "app": "transcribe_server:app", "health": "/health", "wait_s": 900,
                   "torch_index": "https://download.pytorch.org/whl/cu124",
                   "torch": ["torch==2.5.1", "torchaudio==2.5.1"],
                   "reqs": "deploy/requirements.transcribe.txt", "env": {}},
    "big-llm": {"port": 9044, "need_gb": BIG_LLM["12b"][1], "app": "", "health": "/v1/models", "wait_s": 1800,
                "env": {}},
}
STUB_REQS = "deploy/requirements.stub.txt"


def say(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- the card

def smi_path() -> Optional[str]:
    return os.environ.get("NVIDIA_SMI") or shutil.which("nvidia-smi")


def run_smi(args: List[str]) -> Optional[str]:
    """Output of one read-only `nvidia-smi` query, or None when it is not there or fails."""
    exe = smi_path()
    if not exe:
        return None
    cmd = [exe] + args
    if exe.endswith(".py"):                       # a stand-in used by the tests
        cmd = [sys.executable] + cmd
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                             timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def parse_memory(text: str, index: int = 0) -> Optional[Dict[str, float]]:
    """`--query-gpu=memory.used,memory.free,memory.total --format=csv,noheader,nounits` -> GB for one card."""
    rows = [ln for ln in (text or "").splitlines() if ln.strip()]
    if index >= len(rows):
        return None
    try:
        used, free, total = [float(x.strip().split()[0]) for x in rows[index].split(",")[:3]]
    except (ValueError, IndexError):
        return None
    return {"used_gb": used / 1024, "free_gb": free / 1024, "total_gb": total / 1024}


def gpu_memory(index: int = 0) -> Optional[Dict[str, float]]:
    out = run_smi(["--query-gpu=memory.used,memory.free,memory.total", "--format=csv,noheader,nounits"])
    return parse_memory(out, index) if out is not None else None


def parse_apps(text: str) -> Dict[int, float]:
    """`--query-compute-apps=pid,used_memory --format=csv,noheader,nounits` -> {pid: GB}."""
    apps: Dict[int, float] = {}
    for ln in (text or "").splitlines():
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) >= 2 and parts[0].isdigit():
            try:
                apps[int(parts[0])] = apps.get(int(parts[0]), 0.0) + float(parts[1].split()[0]) / 1024
            except (ValueError, IndexError):
                continue
    return apps


def memory_verdict(free_gb: float, need_gb: float, headroom_gb: float = HEADROOM_GB) -> Tuple[bool, str]:
    left = free_gb - need_gb
    line = "free %.1f GB - needed %.1f GB = %.1f GB (rule: at least %.1f GB must stay free)" % (
        free_gb, need_gb, left, headroom_gb)
    return left >= headroom_gb, line


def mps_running() -> bool:
    """Read-only: is a CUDA MPS control daemon running? (Linux /proc; False elsewhere.)"""
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for d in proc.iterdir():
        if d.name.isdigit():
            try:
                if b"nvidia-cuda-mps-control" in (d / "cmdline").read_bytes():
                    return True
            except OSError:
                continue
    return False


# ---------------------------------------------------------------- processes and ports

def port_answers(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.5)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True, check=False).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = Path("/proc/%d/stat" % pid)
    try:                                           # a zombie is gone as far as the port and the card go
        return stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


def pid_cmdline(pid: int) -> Optional[str]:
    """The command line of a process (Linux), or None when it cannot be read."""
    try:
        return Path("/proc/%d/cmdline" % pid).read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return None


def group_pids(pgid: int) -> List[int]:
    """Processes in the group the kit started (the server and any workers it made). Linux only."""
    pids: List[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return [pgid]
    for d in proc.iterdir():
        if d.name.isdigit():
            try:
                if os.getpgid(int(d.name)) == pgid:
                    pids.append(int(d.name))
            except OSError:
                continue
    return pids or [pgid]


def paths(name: str) -> Dict[str, Path]:
    return {"pid": RUN_DIR / (name + ".pid"), "state": RUN_DIR / (name + ".json"), "log": RUN_DIR / (name + ".log")}


def read_state(name: str) -> Dict[str, Any]:
    try:
        return json.loads(paths(name)["state"].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def read_pid(name: str) -> Optional[int]:
    try:
        return int(paths(name)["pid"].read_text().strip())
    except (OSError, ValueError):
        return None


def marker(name: str) -> str:
    """What the command line of the server this kit starts always contains."""
    return "--port %d" % SERVERS[name]["port"]


def ours(name: str, pid: int, cmdline: Callable[[int], Optional[str]] = pid_cmdline) -> bool:
    """Is `pid` still the server this kit started? Its command line must carry our port (where it can be read)."""
    if not pid_alive(pid):
        return False
    line = cmdline(pid)
    return True if line is None else marker(name) in line


# ---------------------------------------------------------------- what to run

def spec(name: str, size: str = "12b", need_gb: Optional[float] = None, stub: bool = False) -> Dict[str, Any]:
    if name not in SERVERS:
        raise SystemExit("unknown server %r; one of: %s" % (name, ", ".join(SERVERS)))
    s = dict(SERVERS[name])
    s["name"] = name
    if name == "big-llm":
        if size not in BIG_LLM:
            raise SystemExit("unknown size %r; 12b or 31b" % size)
        s["model"] = os.environ.get("BIG_LLM_MODEL", BIG_LLM[size][0])
        s["need_gb"] = BIG_LLM[size][1]
        if stub:
            raise SystemExit("big-llm has no stub mode")
    if stub:
        s["need_gb"] = 0.0
    if need_gb is not None:
        s["need_gb"] = float(need_gb)
    if name == "qa" and not stub and os.environ.get("QA_DEVICE", "cpu") == "cuda" and s["need_gb"] <= 0:
        raise SystemExit("QA_DEVICE=cuda puts the QA server on the card: say how much it needs with --need-gb")
    if s["port"] not in OWN_PORTS or s["port"] in PROTECTED_PORTS:
        raise SystemExit("port %d is not one of this kit's ports" % s["port"])
    return s


def venv_python(name: str) -> Path:
    return VENV_DIR / name / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def built(name: str, stub: bool) -> bool:
    """Did an earlier `start` finish building this server's environment (the full one, or at least the stub one)?"""
    try:
        kind = (VENV_DIR / name / ".built").read_text().strip()
    except OSError:
        return False
    return kind == "real" or (stub and kind == "stub")


def vllm_bin() -> Path:
    """vLLM is big; by default the one v0's translation server was installed with is run (its files are only read)."""
    given = os.environ.get("VLLM_BIN")
    if given:
        return Path(given)
    v0 = Path.home() / "voice_engine" / ".venv_llm" / "bin" / "vllm"
    return v0 if v0.exists() else VENV_DIR / "big-llm" / "bin" / "vllm"


def setup_commands(s: Dict[str, Any], stub: bool, python: Optional[str]) -> List[List[str]]:
    """The commands that build the server's own environment (none when an interpreter is given)."""
    name = s["name"]
    if python:
        return []
    py = str(venv_python(name))
    pip = [py, "-m", "pip", "install", "--disable-pip-version-check"]
    if name == "big-llm":
        if vllm_bin().exists():
            return []
        vllm = "vllm" + ("==" + os.environ["VLLM_VERSION"] if os.environ.get("VLLM_VERSION") else "")
        return [[sys.executable, "-m", "venv", str(VENV_DIR / name)], pip + [vllm]]
    cmds: List[List[str]] = [[sys.executable, "-m", "venv", str(VENV_DIR / name)]]
    if stub:
        return cmds + [pip + ["-r", str(ENGINE_DIR / STUB_REQS)]]
    if s.get("torch"):
        cmds.append(pip + list(s["torch"]) + ["--index-url", s["torch_index"]])
    if s.get("git"):
        url, commit_env = s["git"]
        src = VENV_DIR / (name + "-src")
        if not src.exists():
            cmds.append(["git", "clone", url, str(src)])
        cmds.append(["git", "-C", str(src), "checkout", os.environ.get(commit_env, "main")])
        cmds.append(pip + ["-e", str(src) + "[server]"] + list(s.get("pip_extra", [])))
    cmds.append(pip + ["-r", str(ENGINE_DIR / s["reqs"])])
    return cmds


def launch_command(s: Dict[str, Any], python: Optional[str], total_gb: Optional[float]) -> List[str]:
    name, port = s["name"], str(s["port"])
    if name == "big-llm":
        share = min(0.95, max(0.05, s["need_gb"] / total_gb)) if total_gb else 0.35
        return [str(vllm_bin()), "serve", s["model"], "--revision", os.environ.get("BIG_LLM_REVISION", "main"),
                "--host", "127.0.0.1", "--port", port, "--served-model-name", "big",
                "--gpu-memory-utilization", "%.3f" % share, "--max-model-len", os.environ.get("BIG_LLM_CTX", "8192"),
                "--max-num-seqs", "8", "--enable-prefix-caching",
                "--limit-mm-per-prompt", '{"image":0,"audio":0,"video":0}']
    py = python or str(venv_python(name))
    return [py, "-m", "uvicorn", s["app"], "--host", "127.0.0.1", "--port", port]


def launch_env(s: Dict[str, Any], stub: bool) -> Dict[str, str]:
    env = dict(os.environ)
    for k, v in s.get("env", {}).items():
        env.setdefault(k, v)
    if s["name"] == "qa" and env.get("QA_DEVICE", "cpu") != "cuda":
        env["QA_DEVICE"], env["CUDA_VISIBLE_DEVICES"] = "cpu", ""        # no CUDA device: no GPU memory at all
    env.setdefault("HF_HOME", str(Path(MODEL_CACHE) / "hf"))
    env.setdefault("REF_DIR", str(RUN_DIR / ("refs-" + s["name"])))
    if stub:
        env["V1_STUB"] = "1"
        env["CUDA_VISIBLE_DEVICES"] = ""
    return env


# ---------------------------------------------------------------- http

def http(method: str, url: str, body: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None,
         timeout: float = 120.0) -> Tuple[int, Dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def multipart(fields: Dict[str, str], files: Dict[str, Tuple[str, bytes]]) -> Tuple[bytes, Dict[str, str]]:
    edge = uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n" % (edge, k)).encode())
        out.write(v.encode("utf-8") + b"\r\n")
    for k, (fname, data) in files.items():
        out.write(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                   "Content-Type: application/octet-stream\r\n\r\n" % (edge, k, fname)).encode())
        out.write(data + b"\r\n")
    out.write(("--%s--\r\n" % edge).encode())
    return out.getvalue(), {"Content-Type": "multipart/form-data; boundary=" + edge}


def tone_wav(seconds: float = 3.0, sr: int = 16000, hz: float = 200.0) -> bytes:
    """A made sound, not a person's voice: the smoke test copies nobody."""
    n = int(seconds * sr)
    pcm = array.array("h", (int(6000 * math.sin(2 * math.pi * hz * i / sr) * (0.6 + 0.4 * math.sin(i / 900.0)))
                            for i in range(n)))
    if sys.byteorder == "big":
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def health_ok(s: Dict[str, Any], base: Optional[str] = None) -> bool:
    try:
        code, _h, body = http("GET", (base or "http://127.0.0.1:%d" % s["port"]) + s["health"], timeout=5)
    except (OSError, ValueError):
        return False
    if code != 200:
        return False
    if s["name"] == "big-llm":
        return True
    try:
        return bool(json.loads(body.decode("utf-8")).get("ok"))
    except ValueError:
        return False


# ---------------------------------------------------------------- start

def cmd_start(a: argparse.Namespace) -> int:
    s = spec(a.server, a.size, a.need_gb, a.stub)
    name, port = s["name"], s["port"]
    p = paths(name)
    old = read_pid(name)
    if old and ours(name, old):
        say("%s is already running (pid %d, started by this kit). Nothing done; `stop %s` first to restart it."
            % (name, old, name))
        return 0
    if port_answers(port):
        say("REFUSED: something already answers on port %d and this kit did not start it. Nothing was touched." % port)
        return 3

    # 1. the card, before anything else
    mem = gpu_memory(a.gpu_index)
    if mem is None:
        if s["need_gb"] > 0:
            say("REFUSED: nvidia-smi gave no answer, so the free memory is unknown and %s (%.1f GB) is not started."
                % (name, s["need_gb"]))
            return 4
        say("nvidia-smi: not found. %s takes no GPU memory, so there is nothing to check." % name)
    else:
        ok, line = memory_verdict(mem["free_gb"], s["need_gb"])
        say("nvidia-smi: used %.1f GB, free %.1f GB of %.1f GB" % (mem["used_gb"], mem["free_gb"], mem["total_gb"]))
        say("memory check: " + line)
        if not ok:
            say("REFUSED: not enough free GPU memory for %s. Nothing was started and nothing else was stopped." % name)
            return 4
    if mps_running():
        say("CUDA MPS is running: left exactly as it is (this kit never starts, stops or configures MPS).")

    setup = [] if a.skip_install or (built(name, a.stub) and not a.reinstall) else setup_commands(s, a.stub, a.python)
    launch = launch_command(s, a.python, mem["total_gb"] if mem else None)
    if a.dry_run:
        for c in setup:
            say("would run: " + " ".join(c))
        say("would start: " + " ".join(launch))
        say("would write: %s, %s" % (p["pid"], p["log"]))
        return 0

    # 2. the server's own environment
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    for c in setup:
        say("setup: " + " ".join(c))
        if subprocess.run(c, check=False).returncode != 0:
            say("FAILED: the setup command above did not finish. Nothing was started.")
            say("If `python3 -m venv` is missing here, give an interpreter that has the packages: --python PATH")
            return 5
    if setup:
        (VENV_DIR / name).mkdir(parents=True, exist_ok=True)
        (VENV_DIR / name / ".built").write_text("stub" if a.stub else "real")
    if not Path(launch[0]).exists() and not shutil.which(launch[0]):
        say("FAILED: %s is not there. Nothing was started." % launch[0])
        return 5

    # 3. the card again (the setup may have taken minutes), then start
    mem = gpu_memory(a.gpu_index)
    if mem is not None and not memory_verdict(mem["free_gb"], s["need_gb"])[0]:
        say("REFUSED: the free GPU memory changed during setup (now %.1f GB). Nothing was started." % mem["free_gb"])
        return 4
    env = launch_env(s, a.stub)
    Path(env["REF_DIR"]).mkdir(parents=True, exist_ok=True)
    log = open(str(p["log"]), "ab")
    kwargs: Dict[str, Any] = {"start_new_session": True} if os.name != "nt" else {}
    proc = subprocess.Popen(launch, cwd=str(ENGINE_DIR), env=env, stdout=log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, **kwargs)
    p["pid"].write_text(str(proc.pid))
    p["state"].write_text(json.dumps({
        "server": name, "pid": proc.pid, "port": port, "stub": bool(a.stub), "need_gb": s["need_gb"],
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "command": launch,
        "free_before_gb": round(mem["free_gb"], 2) if mem else None, "model": s.get("model", "")}), encoding="utf-8")
    say("started %s: pid %d, port %d, log %s" % (name, proc.pid, port, p["log"]))

    # 4. wait until it answers
    t0, limit = time.time(), a.wait if a.wait is not None else s["wait_s"]
    while time.time() - t0 < limit:
        if proc.poll() is not None:
            say("FAILED: %s ended by itself (exit %s). Last lines of its log:" % (name, proc.returncode))
            say(tail(p["log"]))
            p["pid"].unlink()
            return 6
        if health_ok(s):
            now = gpu_memory(a.gpu_index)
            took = "" if not (mem and now) else "; GPU memory free %.1f GB -> %.1f GB" % (mem["free_gb"], now["free_gb"])
            say("READY: %s answers on 127.0.0.1:%d after %.0f s%s" % (name, port, time.time() - t0, took))
            say("next: python3 %s smoke %s" % (Path(__file__).name, name))
            return 0
        time.sleep(2)
    say("NOT READY after %d s: %s is still loading or stuck (pid %d). Its log: %s" % (limit, name, proc.pid, p["log"]))
    say("It was left running. `smoke %s` when it answers, or `stop %s` to end it." % (name, name))
    return 7


def tail(path: Path, lines: int = 25) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log)"


# ---------------------------------------------------------------- stop

def cmd_stop(a: argparse.Namespace) -> int:
    name = spec(a.server)["name"]
    p = paths(name)
    pid = read_pid(name)
    if pid is None:
        say("%s: no pid file of this kit (%s). This kit started nothing, so nothing is stopped." % (name, p["pid"]))
        return 0
    if not ours(name, pid):
        say("%s: pid %d is gone or is no longer the server this kit started. Nothing stopped; pid file removed."
            % (name, pid))
        p["pid"].unlink()
        return 0
    before = gpu_memory()
    end_own(pid, signal.SIGTERM)
    t0 = time.time()
    while pid_alive(pid) and time.time() - t0 < a.grace:
        time.sleep(0.5)
    if pid_alive(pid):
        say("%s did not end in %d s; ending it for good (the same process, nothing else)." % (name, a.grace))
        end_own(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        time.sleep(1)
    p["pid"].unlink()
    after = gpu_memory()
    mem = "" if not (before and after) else "; GPU memory free %.1f GB -> %.1f GB" % (before["free_gb"], after["free_gb"])
    say("stopped %s (pid %d)%s. Nothing else was touched." % (name, pid, mem))
    return 0


def end_own(pid: int, sig: int) -> None:
    """Signal the server this kit started. On Linux it was started as the leader of its own process group, so its
    workers go with it; a pid that is not such a leader gets the signal alone."""
    try:
        if os.name != "nt" and os.getpgid(pid) == pid:
            os.killpg(pid, sig)
        else:
            os.kill(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


# ---------------------------------------------------------------- smoke

class Checks:
    def __init__(self) -> None:
        self.rows: List[Tuple[str, bool, float, str]] = []

    def run(self, label: str, fn: Callable[[], str]) -> bool:
        t0 = time.perf_counter()
        try:
            detail, ok = fn(), True
        except Exception as e:  # noqa: BLE001 - a failed check is a result, not a crash
            detail, ok = "%s: %s" % (type(e).__name__, str(e)[:200]), False
        ms = (time.perf_counter() - t0) * 1000
        self.rows.append((label, ok, ms, detail))
        say("%s  %-22s %7.0f ms  %s" % ("PASS" if ok else "FAIL", label, ms, detail))
        return ok

    @property
    def ok(self) -> bool:
        return bool(self.rows) and all(r[1] for r in self.rows)


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def get_json(url: str, timeout: float = 30) -> Dict[str, Any]:
    code, _h, body = http("GET", url, timeout=timeout)
    need(code == 200, "HTTP %d: %s" % (code, body[:160].decode("utf-8", "replace")))
    return json.loads(body.decode("utf-8"))


def post_json(url: str, payload: Dict[str, Any], timeout: float = 300) -> Tuple[Dict[str, str], bytes]:
    code, h, body = http("POST", url, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"}, timeout)
    need(code == 200, "HTTP %d: %s" % (code, body[:160].decode("utf-8", "replace")))
    return h, body


def post_form(url: str, fields: Dict[str, str], files: Dict[str, Tuple[str, bytes]], timeout: float = 300) -> Dict[str, Any]:
    body, headers = multipart(fields, files)
    code, _h, out = http("POST", url, body, headers, timeout)
    need(code == 200, "HTTP %d: %s" % (code, out[:160].decode("utf-8", "replace")))
    return json.loads(out.decode("utf-8"))


def smoke_voice(c: Checks, base: str, lines: List[Tuple[str, str]]) -> None:
    sid = "smoke-" + uuid.uuid4().hex[:8]

    def health() -> str:
        h = get_json(base + "/health")
        need(bool(h.get("ok")), "health says not ok: %s" % h)
        return "model=%s stub=%s gpu_gb=%s" % (h.get("model"), h.get("stub"), h.get("gpu_gb"))

    def ref() -> str:
        r = post_form(base + "/ref", {"session_id": sid, "ref_text": "namaste doston, aaj ka din achchha hai",
                                      "lang": "hi-IN"}, {"audio": ("tone.wav", tone_wav())})
        need(bool(r.get("ok")), "the sample was not taken: %s" % r)
        return "a made tone as the sample (no person's voice), version %s" % r.get("version")

    if not c.run("health", health) or not c.run("ref", ref):
        return
    for lang, text in lines:
        def line(lang: str = lang, text: str = text) -> str:
            h, audio = post_json(base + "/tts", {"session_id": sid, "text": text, "lang": lang, "fmt": "pcm"})
            sr = int(h.get("x-sample-rate", "24000"))
            secs = len(audio) / 2 / sr
            need(secs >= 0.3, "only %.2f s of audio came back" % secs)
            pcm = array.array("h", audio[: len(audio) // 2 * 2])
            need(max(abs(x) for x in pcm[:: max(1, len(pcm) // 4000)]) > 50, "the audio is silent")
            return "%.2f s of audio at %d Hz, server took %s ms" % (secs, sr, h.get("x-synth-ms", "?"))
        c.run("tts " + lang, line)


def smoke_transcribe(c: Checks, base: str) -> None:
    def health() -> str:
        h = get_json(base + "/health")
        need(bool(h.get("ok")), "health says not ok: %s" % h)
        return "model=%s stub=%s gpu_gb=%s" % (h.get("model"), h.get("stub"), h.get("gpu_gb"))

    def stt() -> str:
        r = post_form(base + "/stt", {"lang": "hi-IN"}, {"audio": ("tone.wav", tone_wav())})
        need("text" in r, "no `text` in the answer: %s" % r)
        return "answered (a tone has no words): %r, server took %s ms" % (r["text"][:40], r.get("ms"))

    if c.run("health", health):
        c.run("stt", stt)


def smoke_qa(c: Checks, base: str) -> None:
    def health() -> str:
        h = get_json(base + "/health")
        need(bool(h.get("ok")), "health says not ok: %s" % h)
        return "device=%s hear=%s speaker=%s (%s) stub=%s" % (
            h.get("device"), h.get("model"), h.get("speaker_model"), h.get("speaker_licence"), h.get("stub"))

    def score() -> str:
        r = post_form(base + "/score", {"text": "namaste doston", "lang": "hi-IN"},
                      {"audio": ("a.wav", tone_wav(3.0, hz=200.0)), "ref": ("b.wav", tone_wav(3.0, hz=210.0))})
        need("backcheck" in r and "heard" in r, "no score in the answer: %s" % r)
        need(r.get("similarity") is None or -1.0 <= float(r["similarity"]) <= 1.0, "similarity out of range: %s" % r)
        return "backcheck=%s similarity=%s, server took %s ms" % (r["backcheck"], r.get("similarity"), r.get("ms"))

    def similarity() -> str:
        r = post_form(base + "/similarity", {}, {"audio": ("a.wav", tone_wav(3.0)), "ref": ("b.wav", tone_wav(3.0))})
        need(r.get("similarity") is not None and float(r["similarity"]) > 0.9,
             "the same sound twice must score close to 1: %s" % r)
        return "the same sound twice = %s, server took %s ms" % (r["similarity"], r.get("ms"))

    def gpu() -> str:
        r = get_json(base + "/gpu")
        need("gpus" in r, "no `gpus` in the answer: %s" % r)
        g = r["gpus"][0] if r["gpus"] else {}
        return "card: %s, free %s of %s GB" % (g.get("name"), g.get("free_gb"), g.get("total_gb")) if g else "no card seen from here"

    if c.run("health", health):
        c.run("score", score)
        c.run("similarity", similarity)
        c.run("gpu", gpu)


def smoke_llm(c: Checks, base: str) -> None:
    box: Dict[str, str] = {}

    def models() -> str:
        r = get_json(base + "/v1/models")
        ids = [m.get("id") for m in r.get("data", [])]
        need(bool(ids), "no model listed")
        box["model"] = ids[0]
        return "serves %s" % ", ".join(str(i) for i in ids)

    def translate() -> str:
        _h, body = post_json(base + "/v1/chat/completions", {
            "model": box["model"], "temperature": 0.2, "max_tokens": 80,
            "messages": [{"role": "system", "content": "Translate the line into natural spoken Tamil. Reply with the line only."},
                         {"role": "user", "content": "aaj hum ek naya game khelenge"}]})
        text = json.loads(body.decode("utf-8"))["choices"][0]["message"]["content"].strip()
        need(bool(text), "empty reply")
        need(any("஀" <= ch <= "௿" for ch in text), "the reply has no Tamil letters: %r" % text[:80])
        return "replied in Tamil, %d letters" % len(text)

    if c.run("models", models):
        c.run("translate", translate)


VOICE_LINES = [("hi-IN", "नमस्ते दोस्तों, आज हम एक नया खेल खेलेंगे"), ("ta-IN", "வணக்கம் நண்பர்களே, இன்று புதிய விளையாட்டு")]


def memory_report(name: str) -> str:
    """What the server took on the card: by its processes (nvidia-smi) and by the change in free memory."""
    st, mem = read_state(name), gpu_memory()
    if mem is None:
        return "GPU memory: not readable here (no nvidia-smi on this machine); run the smoke test on the GPU machine"
    parts = []
    pid = read_pid(name)
    apps = parse_apps(run_smi(["--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"]) or "")
    if pid:
        group = set(group_pids(pid)) | {pid}
        held = sum(gb for p, gb in apps.items() if p in group)
        parts.append("the server's processes (pid %d) hold %.1f GB" % (pid, held))
    if st.get("free_before_gb") is not None:
        parts.append("free before start %.1f GB, now %.1f GB (taken %.1f GB)" % (
            st["free_before_gb"], mem["free_gb"], st["free_before_gb"] - mem["free_gb"]))
    else:
        parts.append("free now %.1f GB of %.1f GB" % (mem["free_gb"], mem["total_gb"]))
    left = mem["free_gb"]
    parts.append("headroom %s (%.1f GB free, rule %.1f GB)" % ("ok" if left >= HEADROOM_GB else "TOO SMALL", left, HEADROOM_GB))
    return "GPU memory: " + "; ".join(parts)


def cmd_smoke(a: argparse.Namespace) -> int:
    s = spec(a.server)
    name = s["name"]
    base = (a.url or "http://127.0.0.1:%d" % s["port"]).rstrip("/")
    say("smoke test of %s at %s" % (name, base))
    c, t0 = Checks(), time.perf_counter()
    if name in ("tts", "maya"):
        smoke_voice(c, base, VOICE_LINES + ([("en-IN", "Hello friends, welcome back to the stream")] if name == "maya" else []))
    elif name == "transcribe":
        smoke_transcribe(c, base)
    elif name == "qa":
        smoke_qa(c, base)
    else:
        smoke_llm(c, base)
    say(memory_report(name))
    say("RESULT: %s (%d of %d checks, %.1f s)" % ("PASS" if c.ok else "FAIL", sum(1 for r in c.rows if r[1]),
                                                   len(c.rows), time.perf_counter() - t0))
    return 0 if c.ok else 1


# ---------------------------------------------------------------- status

def cmd_status(_a: argparse.Namespace) -> int:
    mem = gpu_memory()
    say("nvidia-smi: " + ("used %.1f GB, free %.1f GB of %.1f GB" % (mem["used_gb"], mem["free_gb"], mem["total_gb"])
                          if mem else "not found"))
    say("CUDA MPS: " + ("running (never touched by this kit)" if mps_running() else "not seen"))
    for name, s in SERVERS.items():
        pid = read_pid(name)
        mine = bool(pid and ours(name, pid))
        up = port_answers(s["port"])
        state = "up, started by this kit (pid %d)" % pid if (mine and up) else \
            "loading, started by this kit (pid %d)" % pid if mine else \
            "answers, NOT started by this kit" if up else "down"
        say("  %-10s :%d  need %4.1f GB  %s" % (name, s["port"], s["need_gb"], state))
    for port in PROTECTED_PORTS[4:]:
        say("  (v0) :%d  %s" % (port, "answers" if port_answers(port) else "does not answer"))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="kit.py", description="Start, test and stop one v1 model server.")
    sub = ap.add_subparsers(dest="cmd")
    st = sub.add_parser("start")
    st.add_argument("server", choices=sorted(SERVERS))
    st.add_argument("--stub", action="store_true", help="without its model and without the GPU (V1_STUB=1)")
    st.add_argument("--dry-run", action="store_true", help="check the card and print what would run")
    st.add_argument("--python", help="an interpreter that already has the server's packages (no environment is built)")
    st.add_argument("--need-gb", type=float, help="GPU memory the server needs, when measured (overrides the table)")
    st.add_argument("--size", default="12b", help="big-llm only: 12b or 31b")
    st.add_argument("--skip-install", action="store_true")
    st.add_argument("--reinstall", action="store_true")
    st.add_argument("--gpu-index", type=int, default=0)
    st.add_argument("--wait", type=int, help="seconds to wait for the server to answer")
    st.set_defaults(fn=cmd_start)
    sm = sub.add_parser("smoke")
    sm.add_argument("server", choices=sorted(SERVERS))
    sm.add_argument("--url", help="another address, e.g. a forwarded port")
    sm.set_defaults(fn=cmd_smoke)
    sp = sub.add_parser("stop")
    sp.add_argument("server", choices=sorted(SERVERS))
    sp.add_argument("--grace", type=int, default=30)
    sp.set_defaults(fn=cmd_stop)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        ap.print_help()
        return 2
    return int(a.fn(a))


if __name__ == "__main__":
    sys.exit(main())
