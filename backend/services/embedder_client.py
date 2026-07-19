"""
Encode text to embeddings, either via a separate embedder HF Space
(EMBEDDER_URL set) or an in-process model (EMBEDDER_URL unset).

Why a circuit breaker: if the embedder Space is asleep, crashed, or just
slow, we do NOT want every /check-submission call to hang for the full
timeout one by one while participants wait. After a few consecutive
failures we "open" the breaker and skip calling the embedder entirely for
a cooldown window, going straight to the local-fallback path (or, if there
is no local model loaded either, letting the caller degrade to fuzzy-only
matching). This keeps failures cheap and bounded instead of compounding.
"""

import logging
import threading
import time
from typing import Optional

import httpx
import numpy as np

from config import (
    EMBEDDER_CIRCUIT_COOLDOWN_SECONDS,
    EMBEDDER_CIRCUIT_FAILURE_THRESHOLD,
    EMBEDDER_TIMEOUT_SECONDS,
    EMBEDDER_URL,
    MODEL_NAME,
    NER_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_EMBEDDER_API_KEY_HEADER = "X-API-Key"


class _CircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_seconds: float) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None

    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at >= self._cooldown_seconds:
                # Cooldown elapsed -- allow one probe attempt through.
                self._opened_at = None
                self._consecutive_failures = 0
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold and self._opened_at is None:
                self._opened_at = time.monotonic()
                logger.warning(
                    "Embedder circuit breaker OPEN after %d consecutive failures — "
                    "falling back to local/fuzzy matching for %.0fs",
                    self._consecutive_failures,
                    self._cooldown_seconds,
                )


_breaker = _CircuitBreaker(EMBEDDER_CIRCUIT_FAILURE_THRESHOLD, EMBEDDER_CIRCUIT_COOLDOWN_SECONDS)
_client: Optional[httpx.Client] = None


def _get_http_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=EMBEDDER_TIMEOUT_SECONDS)
    return _client


def is_remote_configured() -> bool:
    return bool(EMBEDDER_URL)


def is_remote_available() -> bool:
    """True if the remote embedder is configured and the breaker isn't open."""
    return is_remote_configured() and not _breaker.is_open()


def encode_remote(texts: list[str], api_key: str = "") -> Optional[np.ndarray]:
    """Try the remote embedder Space. Returns None (never raises) on any
    failure so callers can fall back cleanly -- a slow/dead embedder must
    never be able to break or hang a duplicate check."""
    if not is_remote_available():
        return None
    try:
        headers = {_EMBEDDER_API_KEY_HEADER: api_key} if api_key else {}
        resp = _get_http_client().post(
            f"{EMBEDDER_URL}/embed", json={"texts": texts}, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        _breaker.record_success()
        return np.asarray(data["embeddings"])
    except Exception as exc:
        logger.warning("Embedder Space call failed, will fall back: %s", exc)
        _breaker.record_failure()
        return None


_ner_client: Optional[httpx.Client] = None


def _get_ner_http_client() -> httpx.Client:
    # Separate client (and much longer timeout) from the embed one above --
    # NER is a one-off batch call from the QA batch, possibly the Space's
    # very first request ever if the NER model hasn't been touched yet
    # (cold start + model download), not a per-submission call that needs
    # to fail fast.
    global _ner_client
    if _ner_client is None:
        _ner_client = httpx.Client(timeout=NER_TIMEOUT_SECONDS)
    return _ner_client


def ner_remote(texts: list[str], api_key: str = "") -> Optional[list[list[dict]]]:
    """Try the remote embedder Space's /ner endpoint. Returns None (never
    raises) on any failure -- including the Space being unconfigured, or
    responding with available=False (its own NER model failed to load) --
    so callers (pii_service.scan_pii_batch) can fall back to a local model
    or plain regex+list detection. No circuit breaker: this is called at
    most once per QA batch run, never per-request, so there's no pile-up
    risk to guard against."""
    if not is_remote_configured():
        return None
    try:
        headers = {_EMBEDDER_API_KEY_HEADER: api_key} if api_key else {}
        resp = _get_ner_http_client().post(
            f"{EMBEDDER_URL}/ner", json={"texts": texts}, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("available", False):
            logger.warning("Embedder Space's NER model isn't loaded there — falling back")
            return None
        return data["entities"]
    except Exception as exc:
        logger.warning("Embedder Space /ner call failed, will fall back: %s", exc)
        return None
