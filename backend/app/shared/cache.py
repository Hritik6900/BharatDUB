"""Content-addressed stage cache on disk: data/cache/<stage>/<key>.<ext>. Shared across jobs."""
import json
import shutil
from pathlib import Path
from typing import Any

from app.config import get_settings


def cache_dir(stage: str) -> Path:
    s = get_settings()
    # Mock-mode results must never be served once real providers are configured.
    d = s.data_path / ("cache-mock" if s.mock_providers else "cache") / stage
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_json(stage: str, key: str) -> Any | None:
    p = cache_dir(stage) / f"{key}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def put_json(stage: str, key: str, value: Any) -> None:
    p = cache_dir(stage) / f"{key}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def file_path(stage: str, key: str, ext: str) -> Path:
    return cache_dir(stage) / f"{key}.{ext}"


def get_file(stage: str, key: str, ext: str) -> Path | None:
    p = file_path(stage, key, ext)
    return p if p.exists() and p.stat().st_size > 0 else None


def put_file(stage: str, key: str, ext: str, src: Path | bytes) -> Path:
    p = file_path(stage, key, ext)
    tmp = p.with_suffix(f".{ext}.tmp")
    if isinstance(src, bytes):
        tmp.write_bytes(src)
    else:
        shutil.copyfile(src, tmp)
    tmp.replace(p)
    return p
