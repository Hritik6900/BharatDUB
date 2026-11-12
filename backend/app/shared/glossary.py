"""Glossary: words that are never translated."""
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import DEFAULT_GLOSSARY
from app.db import get_store

router = APIRouter()


class Term(BaseModel):
    term: str
    note: str | None = None


@router.get("/api/glossary")
async def list_terms() -> dict[str, Any]:
    rows = await get_store().select("glossary_terms", order="term")
    return {"defaults": DEFAULT_GLOSSARY, "terms": rows}


@router.post("/api/glossary", status_code=201)
async def add_term(t: Term) -> dict[str, Any]:
    term = t.term.strip()
    if not term or len(term) > 80:
        raise HTTPException(400, "term must be 1-80 characters")
    store = get_store()
    if await store.select("glossary_terms", term=term):
        raise HTTPException(409, "term already exists")
    return await store.insert("glossary_terms", {"term": term, "note": (t.note or "").strip() or None})


@router.delete("/api/glossary/{tid}")
async def delete_term(tid: str) -> dict[str, bool]:
    if not await get_store().delete("glossary_terms", id=tid):
        raise HTTPException(404, "term not found")
    return {"deleted": True}
