#!/usr/bin/env bash
# start one v1 model server: deploy/start.sh <qa|tts|maya|transcribe|big-llm> [options]. See kit.py for what it does and never does.
exec python3 "$(dirname "$0")/kit.py" start "$@"
