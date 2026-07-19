"""
Standalone embedder microservice — optional, separate HF Space.

This holds NO secrets and touches Supabase and no team/session data at all.
Its main job: given a list of strings, return sentence embeddings, used by
the main backend's duplicate-check feature. It also optionally serves
NER (named-entity recognition), used by the main backend's PII detection
during the organizer's QA batch. Isolating both onto their own compute means
neither can compete with (or block) auth/submit traffic on the main
backend's 2 vCPUs.

The main backend (see ../backend/services/embedder_client.py) calls this
over HTTP with a short timeout and a circuit breaker for /embed (used on
every /check-submission), and falls back to RapidFuzz-only matching if this
Space is slow, asleep, or unreachable -- so this Space being down NEVER
blocks a participant's submission. /ner has a longer timeout and no circuit
breaker since it's only ever called once per organizer-triggered QA batch,
not per-request.

Deploy this as its own Docker HF Space (see embedder/Dockerfile). Set
EMBEDDER_URL on the main backend to this Space's URL to enable it; leave
EMBEDDER_URL unset on the main backend to skip this entirely and load
models in-process there instead (single-Space deploy, simpler, less
isolated).

The NER model loads LAZILY on first /ner call, not at startup -- unlike the
embedding model, which loads eagerly since it's needed on every
/check-submission. NER is only used for the occasional post-event QA batch,
so there's no reason to pay its load cost (and hold its memory) on every
Space restart if it never ends up getting used.
"""

import logging
import os
import threading
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
NER_MODEL_NAME = os.environ.get("NER_MODEL_NAME", "debabrata-ai/Nepali-Named-Entity-Tagger-XLM-R")
# Simple shared-secret check so this Space isn't an open, anonymous compute
# proxy anyone on the internet can hammer. Optional but recommended.
EMBEDDER_API_KEY = os.environ.get("EMBEDDER_API_KEY", "")

MAX_BATCH_SIZE = int(os.environ.get("MAX_BATCH_SIZE", "64"))

_model: Optional[SentenceTransformer] = None

_ner_pipeline = None
_ner_load_attempted = False
_ner_lock = threading.Lock()


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


class NerRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=MAX_BATCH_SIZE)


class NerEntity(BaseModel):
    entity_group: str
    word: str
    score: float


class NerResponse(BaseModel):
    entities: list[list[NerEntity]]  # one list of entities per input text
    model: str
    available: bool  # False if the model failed to load -- caller should fall back


def _check_auth(api_key: Optional[str]) -> None:
    if EMBEDDER_API_KEY and api_key != EMBEDDER_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


def _get_ner_pipeline():
    """Lazily load the NER pipeline on first /ner call. A failed load is
    remembered so a slow/broken HF Hub download isn't retried on every call
    within this process's lifetime -- restart the Space to retry."""
    global _ner_pipeline, _ner_load_attempted

    with _ner_lock:
        if _ner_pipeline is not None or _ner_load_attempted:
            return _ner_pipeline

        _ner_load_attempted = True
        try:
            from transformers import (
                AutoModelForTokenClassification,
                AutoTokenizer,
                pipeline,
            )

            logger.info("Loading NER model: %s (first /ner call, may take a while)", NER_MODEL_NAME)
            tokenizer = AutoTokenizer.from_pretrained(NER_MODEL_NAME)
            model = AutoModelForTokenClassification.from_pretrained(NER_MODEL_NAME)
            _ner_pipeline = pipeline(
                "ner", model=model, tokenizer=tokenizer, aggregation_strategy="simple"
            )
            logger.info("NER model loaded successfully")
        except Exception as exc:
            logger.error("Failed to load NER model %s: %s", NER_MODEL_NAME, exc)
            _ner_pipeline = None

    return _ner_pipeline


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "model_name": MODEL_NAME,
        "ner_loaded": _ner_pipeline is not None,
        "ner_load_attempted": _ner_load_attempted,
    }


@app.post("/embed", response_model=EmbedResponse)
def embed(body: EmbedRequest, x_api_key: Optional[str] = Header(default=None)):
    _check_auth(x_api_key)
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    vectors = _model.encode(body.texts, normalize_embeddings=True)
    return EmbedResponse(embeddings=vectors.tolist(), model=MODEL_NAME)


@app.post("/ner", response_model=NerResponse)
def ner(body: NerRequest, x_api_key: Optional[str] = Header(default=None)):
    _check_auth(x_api_key)

    pipe = _get_ner_pipeline()
    if pipe is None:
        # Not a 503 -- the caller (main backend) treats `available: false` as
        # "fall back to local/regex", the same graceful degradation used
        # everywhere else in this tool. A 503 would work too, but this saves
        # the caller a try/except around a status code for the same outcome.
        return NerResponse(entities=[[] for _ in body.texts], model=NER_MODEL_NAME, available=False)

    try:
        raw = pipe(body.texts)
        if body.texts and raw and not isinstance(raw[0], list):
            raw = [raw]  # pipeline flattens to a single list for a 1-item input
        entities = [
            [
                NerEntity(entity_group=ent["entity_group"], word=ent["word"], score=float(ent["score"]))
                for ent in per_text
                if ent.get("word", "").strip()
            ]
            for per_text in raw
        ]
        return NerResponse(entities=entities, model=NER_MODEL_NAME, available=True)
    except Exception as exc:
        logger.error("NER inference failed: %s", exc)
        raise HTTPException(status_code=500, detail="NER inference failed") from exc
