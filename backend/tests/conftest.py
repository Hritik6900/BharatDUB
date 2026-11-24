import os
import tempfile

# Isolate tests from backend/.env: local store + temp data dir, no real services.
_tmp = tempfile.mkdtemp(prefix="bharatdub-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""
os.environ["GNANI_API_KEY"] = ""
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_MODEL"] = ""
os.environ["GPU_VOICE_URL"] = ""
os.environ["GPU_SEPARATE_URL"] = ""
os.environ["GPU_STT_URL"] = ""
os.environ["GPU_LLM_URL"] = ""
os.environ["GPU_MIO_URL"] = ""
os.environ["GPU_VOICE_MODEL"] = "f5"
os.environ["AI_MODE"] = "cloud"
# v1: every flag off and no v1 server, whatever this checkout's .env says. A test that wants one switches it on.
for _name in ("V1_TRACE", "V1_ROUTER", "V1_PHRASE_DYNAMIC", "V1_SPEC_TRANSLATE", "V1_TTS_SERVER", "V1_TTS_MAYA",
              "V1_LIVE_STOCK_DEFAULT", "V1_LIVE_LATE_SHORTEN", "V1_LIVE_BACKCHECK", "V1_STUDIO_HQ", "V1_FIT_115", "V1_API_LOG",
              "V1_LLM_PREFIX_CACHE", "V1_BREAKER", "V1_LIVE_DEGRADE", "V1_LIVE_BUDGET", "V1_LIVE_RATECTRL",
              "V1_LIVE_NATIVE_SPEED", "V1_LIVE_WARMSTART", "V1_EN_SINGLE_VOICE", "V1_HQ_JUDGE", "V1_HQ_CALIBRATE",
              "V1_HQ_ADAPTIVE", "V1_HQ_NORMALISE", "V1_HQ_AUTO_GLOSSARY", "V1_HQ_REVIEW", "V1_LIVE_RECORD",
              "V1_LISTEN_TEST"):
    os.environ[_name] = "false"
for _name in ("V1_TTS_SERVER_URL", "V1_MAYA_URL", "V1_TRANSCRIBE_URL", "V1_BIG_LLM_URL", "V1_QA_URL", "REDIS_URL",
              "POSTGRES_DSN", "V1_ROUTING_FILE", "V1_GPU_STATS_URL", "V1_RECORD_DIR", "V1_LISTEN_DIR"):
    os.environ[_name] = ""
os.environ["V1_STORE"] = "json"
os.environ["V1_EN_VOICE"] = "auto"
os.environ["V1_HQ_TAKES_FIXED"] = "0"
os.environ["V1_HQ_ADAPTIVE_SAME_STOP"] = "false"
os.environ["V1_HQ_JUDGE_BY_LANG"] = ""
os.environ["V1_HQ_JUDGE_ORDER"] = "prisma,whisper_gpu,qa_server"
