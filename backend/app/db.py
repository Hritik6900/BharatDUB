"""Supabase client. Repo functions are added per milestone (M2+)."""
from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_db() -> Client:
    s = get_settings()
    key = s.supabase_service_key.get_secret_value()
    if not (s.supabase_url and key):
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY are not set")
    return create_client(s.supabase_url, key)
