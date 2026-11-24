#!/usr/bin/env bash
# stop one v1 model server: deploy/stop.sh <qa|tts|maya|transcribe|big-llm> [options]. See kit.py for what it does and never does.
exec python3 "$(dirname "$0")/kit.py" stop "$@"
