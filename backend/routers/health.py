"""Health check endpoint."""

from fastapi import APIRouter

from config import (
    EMBEDDER_URL,
    SIMILARITY_THRESHOLD,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)
from services.embedder_client import is_remote_available, is_remote_configured

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "secrets_configured": bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        "embedding_mode": "remote" if is_remote_configured() else "rapidfuzz",
        "embedder_configured": is_remote_configured(),
        "embedder_reachable": is_remote_available() if is_remote_configured() else None,
        "similarity_threshold": SIMILARITY_THRESHOLD,
    }
