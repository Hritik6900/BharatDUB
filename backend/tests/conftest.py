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
