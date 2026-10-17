"""POST /api/query. Mount with app.include_router(router)."""
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .pipeline import run_query

router = APIRouter()
CACHE_FILE = Path(__file__).parent / "demo_cache.json"


class QueryRequest(BaseModel):
    text: str
    selected_asset_id: str | None = None
    year: int = 2026


def _key(req: QueryRequest) -> str:
    return f"{(req.selected_asset_id or '').lower()}|{req.text.strip().lower()}|{req.year}"


def _load_cache() -> dict:
    return json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}


@router.get("/api/health")
def health():
    return {"status": "ok",
            "mock_llm": os.getenv("USE_MOCK", "false").lower() == "true",
            "mock_sim": os.getenv("USE_MOCK_SIM", "true").lower() == "true",
            "demo_mode": os.getenv("DEMO_MODE", "false").lower() == "true"}


@router.post("/api/query")
def query(req: QueryRequest):
    cache = _load_cache()
    if os.getenv("DEMO_MODE", "false").lower() == "true" and _key(req) in cache:
        return cache[_key(req)]          # instant, no LLM call: protects the live demo
    try:
        result = run_query(req.text, req.selected_asset_id, req.year)
    except Exception as e:               # LLM/network failure should not crash the server
        raise HTTPException(status_code=502, detail=f"Query failed: {e}")
    if not result.get("needs_clarification"):
        cache[_key(req)] = result
        CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return result