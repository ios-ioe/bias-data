"""
Standalone embedder microservice — optional, separate HF Space.

This holds NO secrets and touches Supabase and no team/session data at all.
Its only job: given a list of strings, return sentence embeddings. It exists
so the CPU-heavy ML inference used by the main backend's duplicate-check
feature can be isolated onto its own compute, restarted/scaled independently,
and can't compete with (or block) auth/submit traffic on the main backend's
2 vCPUs.

The main backend (see ../backend/services/embedder_client.py) calls this
over HTTP with a short timeout and a circuit breaker, and falls back to
RapidFuzz-only matching if this Space is slow, asleep, or unreachable —
so this Space being down NEVER blocks a participant's submission.

Deploy this as its own Docker HF Space (see embedder/Dockerfile). Set
EMBEDDER_URL on the main backend to this Space's URL to enable it; leave
EMBEDDER_URL unset on the main backend to skip this entirely and load the
model in-process there instead (single-Space deploy, simpler, less isolated).
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = os.environ.get(
    "MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
# Simple shared-secret check so this Space isn't an open, anonymous compute
# proxy anyone on the internet can hammer. Optional but recommended.
EMBEDDER_API_KEY = os.environ.get("EMBEDDER_API_KEY", "")

MAX_BATCH_SIZE = int(os.environ.get("MAX_BATCH_SIZE", "64"))

_model: Optional[SentenceTransformer] = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _model
    try:
        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model loaded successfully")
    except Exception as exc:
        logger.error("Failed to load embedding model at startup: %s", exc)
    yield


app = FastAPI(title="Bias Data Tool — Embedder", lifespan=lifespan)


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=MAX_BATCH_SIZE)


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str


def _check_auth(api_key: Optional[str]) -> None:
    if EMBEDDER_API_KEY and api_key != EMBEDDER_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _model is not None, "model_name": MODEL_NAME}


@app.post("/embed", response_model=EmbedResponse)
def embed(body: EmbedRequest, x_api_key: Optional[str] = Header(default=None)):
    _check_auth(x_api_key)
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    vectors = _model.encode(body.texts, normalize_embeddings=True)
    return EmbedResponse(embeddings=vectors.tolist(), model=MODEL_NAME)
