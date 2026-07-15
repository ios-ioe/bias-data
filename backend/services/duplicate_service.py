"""Duplicate detection using RapidFuzz pre-filter and sentence embeddings.

PERFORMANCE NOTE (fixes the #1 bottleneck under concurrent load):
The original implementation re-fetched the *entire* submissions table and
re-embedded every candidate on every single /check-submission call. With
100+ participants hammering "Check & save" concurrently near the end of an
event, that's O(table size) network + CPU work per request, on a 2 vCPU
Hugging Face Space -- it queues up fast and starts hitting the frontend's
30s timeout.

Instead we keep an in-process cache of (id -> text, id -> embedding) that is:
  - built once, lazily, on first use (or eagerly at startup via warmup_model)
  - updated incrementally in O(1) whenever this process inserts a new row
    (see add_to_cache, called from routers/submission.py right after insert)
  - refreshed from the DB on a cheap cadence (row-count check) so it also
    picks up rows inserted by another process/replica, without doing a full
    re-embed unless the count actually changed
A threading.Semaphore bounds how many encode() calls can run at once, so a
burst of concurrent checks doesn't oversubscribe the box's CPUs and starve
other requests (login/submit) sharing the same thread pool.
"""

import logging
import threading
import time
from typing import Optional, TypedDict

import numpy as np
from rapidfuzz import fuzz, process
from sentence_transformers import SentenceTransformer

from config import (
    FUZZ_PREFILTER_THRESHOLD,
    FUZZ_TOP_K,
    MODEL_NAME,
    SIMILARITY_THRESHOLD,
)
from database import count_all_submissions, fetch_all_submissions
from services.embedder_client import encode_remote, is_remote_configured

logger = logging.getLogger(__name__)

SNIPPET_MAX_LEN = 100

_model: Optional[SentenceTransformer] = None

# Cap how many encode() calls can run concurrently. Keep this <= vCPU count
# on the host (HF free CPU-Basic = 2) so duplicate checks can't starve out
# /login and /submit, which share the same uvicorn thread pool.
_ENCODE_CONCURRENCY = 2
_encode_semaphore = threading.Semaphore(_ENCODE_CONCURRENCY)

# Only re-poll the DB row count this often, so a burst of concurrent checks
# doesn't turn into a burst of COUNT queries too.
_CACHE_REFRESH_INTERVAL_SECONDS = 15


class _CorpusCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready = False  # ids/texts loaded, regardless of embedding availability
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._embeddings: Optional[np.ndarray] = None  # None => embeddings unavailable (degraded mode)
        self._known_ids: set[str] = set()
        self._last_count_check = 0.0
        self._last_known_count: Optional[int] = None

    def _encode_texts(self, texts: list[str]) -> Optional[np.ndarray]:
        """Tiered fallback: remote embedder Space -> local in-process model ->
        None (embeddings unavailable; caller degrades to fuzzy-only). Never
        raises -- a dead embedder must never be able to break a check."""
        if not texts:
            return np.zeros((0, 1))

        remote = encode_remote(texts)
        if remote is not None:
            return remote

        if is_model_loaded():
            with _encode_semaphore:
                return np.asarray(get_model().encode(texts, normalize_embeddings=True))

        return None

    def _full_reload_locked(self) -> None:
        rows = fetch_all_submissions("id, text")
        ids: list[str] = []
        texts: list[str] = []
        seen: set[str] = set()
        for row in rows:
            row_id = row.get("id")
            row_text = (row.get("text") or "").strip()
            if row_id and row_text and row_id not in seen:
                seen.add(row_id)
                ids.append(row_id)
                texts.append(row_text)

        embeddings = self._encode_texts(texts)
        self._ids = ids
        self._texts = texts
        self._embeddings = embeddings
        self._known_ids = seen
        self._last_known_count = len(ids)
        self._ready = True
        logger.info(
            "Duplicate cache: full reload, %d rows, embeddings=%s",
            len(ids),
            "available" if embeddings is not None else "UNAVAILABLE (fuzzy-only fallback)",
        )

    def ensure_fresh(self) -> None:
        """Cheap freshness check: only hit the DB for a row COUNT at most
        once per _CACHE_REFRESH_INTERVAL_SECONDS, and only pay for a full
        reload if that count actually changed (e.g. another process/replica
        inserted rows this one doesn't know about yet)."""
        now = time.monotonic()
        with self._lock:
            if not self._ready:
                try:
                    self._full_reload_locked()
                except Exception as exc:
                    # Supabase unreachable on the very first load (e.g. down
                    # at startup, or the first /check-submission ever). This
                    # must NOT propagate as an error on every check -- there's
                    # simply nothing to compare against yet, which is a
                    # legitimate (if degraded) state, not a failure. Mark the
                    # cache ready with an empty corpus so callers get a normal
                    # "no duplicates found" result instead of a 503, and so we
                    # don't retry-and-fail this exact path on every single
                    # request. The periodic count-check below will pick up
                    # real data automatically once Supabase recovers.
                    logger.warning(
                        "Duplicate cache: initial load failed (Supabase unreachable?) -- "
                        "treating as empty corpus until it recovers: %s",
                        exc,
                    )
                    self._ids, self._texts, self._embeddings = [], [], None
                    self._known_ids = set()
                    self._last_known_count = None
                    self._ready = True
                self._last_count_check = now
                return
            if now - self._last_count_check < _CACHE_REFRESH_INTERVAL_SECONDS:
                return
            self._last_count_check = now

        try:
            current_count = count_all_submissions()
        except Exception as exc:
            logger.warning("Duplicate cache: could not check row count: %s", exc)
            return

        with self._lock:
            if current_count != self._last_known_count:
                self._full_reload_locked()
            elif self._embeddings is None:
                # Row count unchanged but we're in degraded (no-embeddings)
                # mode -- retry embedding periodically in case the remote
                # embedder's circuit breaker has since closed again.
                self._full_reload_locked()

    def add(self, row_id: str, text: str) -> None:
        """O(1)-ish incremental update after this process inserts a row --
        no DB round-trip, just one embedding + one array append (or a plain
        text-only append if embeddings are currently unavailable)."""
        text = (text or "").strip()
        if not row_id or not text:
            return
        with self._lock:
            if row_id in self._known_ids or not self._ready:
                return
            self._ids.append(row_id)
            self._texts.append(text)
            self._known_ids.add(row_id)
            self._last_known_count = (self._last_known_count or 0) + 1

            if self._embeddings is None:
                return  # degraded mode; nothing to append embedding-wise
            embedding = self._encode_texts([text])
            if embedding is None:
                # Embedder just went down between reload and now -- drop to
                # degraded mode for everyone until the next reload retries it.
                self._embeddings = None
                return
            self._embeddings = (
                embedding if self._embeddings.shape[0] == 0 else np.vstack([self._embeddings, embedding])
            )

    def encode_texts(self, texts: list[str]) -> Optional[np.ndarray]:
        """Public wrapper so callers (e.g. check_duplicate for the query
        text itself) can reuse the same tiered fallback without duplicating it."""
        return self._encode_texts(texts)

    def snapshot(self) -> tuple[list[str], list[str], Optional[np.ndarray]]:
        with self._lock:
            return (
                list(self._ids),
                list(self._texts),
                self._embeddings.copy() if self._embeddings is not None else None,
            )


_corpus_cache = _CorpusCache()


def add_to_cache(row_id: str, text: str) -> None:
    """Called right after a successful /submit insert so the new row is
    immediately visible to future duplicate checks without a DB round-trip."""
    try:
        _corpus_cache.add(row_id, text)
    except Exception as exc:
        logger.warning("Duplicate cache: failed to add row %s: %s", row_id, exc)


class DuplicateResult(TypedDict):
    flagged: bool
    similarity: float
    closest_match_snippet: str


def warmup_model() -> None:
    """Load the embedding model once at startup -- unless a separate embedder
    Space is configured (EMBEDDER_URL), in which case we deliberately skip
    loading a model here at all. That's the whole point of splitting the
    embedder out: this backend should carry zero ML compute/memory when a
    remote embedder is available, and fall back to fuzzy-only matching (not
    a local model) if that remote Space is ever unreachable -- keeping this
    backend's resource footprint small and predictable under load."""
    global _model
    if is_remote_configured():
        logger.info(
            "EMBEDDER_URL is set — skipping local model load; using the "
            "remote embedder Space, with RapidFuzz-only fallback if it's unreachable."
        )
    elif _model is None:
        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model loaded successfully")

    try:
        _corpus_cache.ensure_fresh()
    except Exception as exc:
        # Don't block startup on this -- ensure_fresh() will retry lazily on
        # the first real /check-submission call if the initial load fails
        # (e.g. Supabase not reachable yet during a cold boot race).
        logger.warning("Duplicate cache: initial warmup load failed, will retry lazily: %s", exc)


def get_model() -> SentenceTransformer:
    if _model is None:
        raise RuntimeError("Embedding model is not loaded. Call warmup_model() at startup.")
    return _model


def is_model_loaded() -> bool:
    return _model is not None


def is_embedding_available() -> bool:
    """True if EITHER the remote embedder or a local model can currently
    serve encode() calls. Used by /check-submission to decide whether to
    503 (nothing is even configured/loaded) vs. proceed in fuzzy-only mode
    (something is configured but temporarily unreachable -- that should
    never block a check, per this tool's own 'warnings never block' design)."""
    return is_remote_configured() or is_model_loaded()


def _truncate_snippet(text: str, max_len: int = SNIPPET_MAX_LEN) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _empty_result() -> DuplicateResult:
    return {
        "flagged": False,
        "similarity": 0.0,
        "closest_match_snippet": "",
    }


def _cosine_similarity(query_emb: np.ndarray, candidate_embs: np.ndarray) -> np.ndarray:
    return np.dot(candidate_embs, query_emb)


def check_duplicate(text: str) -> DuplicateResult:
    """
    Compare text against existing submissions.

    Uses RapidFuzz to narrow candidates, then embedding cosine similarity
    on the top fuzzy matches only.
    """
    normalized = text.strip()
    if not normalized:
        return _empty_result()

    # Uses the in-process cache (see _CorpusCache above) instead of fetching
    # and re-embedding the whole table on every call -- this is the change
    # that makes /check-submission viable under 100+ concurrent participants.
    _corpus_cache.ensure_fresh()
    id_list, text_list, embeddings = _corpus_cache.snapshot()

    if not id_list:
        logger.info("Duplicate check: empty database, no candidates")
        return _empty_result()

    fuzzy_hits = process.extract(
        normalized,
        text_list,
        scorer=fuzz.ratio,
        limit=min(FUZZ_TOP_K, len(text_list)),
    )

    candidate_indices: list[int] = [
        index for _match_text, score, index in fuzzy_hits if score >= FUZZ_PREFILTER_THRESHOLD
    ]

    if not candidate_indices:
        logger.info("Duplicate check: no fuzzy candidates above threshold")
        return _empty_result()

    if embeddings is None:
        # Degraded mode: neither the remote embedder nor a local model is
        # currently available. Fall back to the fuzzy-ratio score itself as
        # the similarity signal rather than failing the check outright --
        # this catches near-exact duplicates (typos, punctuation) even
        # without semantic embeddings, which is strictly better than no
        # duplicate protection at all while the embedder recovers.
        best_match = max(
            (fuzzy_hits[i] for i in range(len(fuzzy_hits)) if fuzzy_hits[i][2] in candidate_indices),
            key=lambda hit: hit[1],
        )
        best_text, fuzzy_score, _ = best_match
        best_similarity = fuzzy_score / 100.0
        flagged = best_similarity >= SIMILARITY_THRESHOLD
        logger.warning(
            "Duplicate check running in DEGRADED (fuzzy-only) mode — "
            "similarity=%.4f flagged=%s candidates=%d",
            best_similarity,
            flagged,
            len(candidate_indices),
        )
        return {
            "flagged": flagged,
            "similarity": round(best_similarity, 4),
            "closest_match_snippet": _truncate_snippet(best_text),
        }

    query_emb = _corpus_cache.encode_texts([normalized])
    if query_emb is None:
        # Embedder went down between the snapshot above and now -- treat as
        # degraded rather than crash; the cache will self-heal on next poll.
        return _empty_result()

    candidate_embs = embeddings[candidate_indices]
    candidate_texts = [text_list[i] for i in candidate_indices]

    similarities = _cosine_similarity(query_emb[0], candidate_embs)
    best_idx = int(np.argmax(similarities))
    best_similarity = float(similarities[best_idx])
    best_text = candidate_texts[best_idx]

    flagged = best_similarity >= SIMILARITY_THRESHOLD
    logger.info(
        "Duplicate check: similarity=%.4f flagged=%s candidates=%d",
        best_similarity,
        flagged,
        len(candidate_indices),
    )

    return {
        "flagged": flagged,
        "similarity": round(best_similarity, 4),
        "closest_match_snippet": _truncate_snippet(best_text),
    }


_QA_BATCH_CHUNK_SIZE = 64  # keep in sync with embedder/app.py's MAX_BATCH_SIZE


def _encode_batched(texts: list[str], chunk_size: int = _QA_BATCH_CHUNK_SIZE) -> Optional[np.ndarray]:
    """Encode a (possibly large) list of texts in chunks, via the same
    tiered fallback as everything else. Returns None if embeddings are
    unavailable at all -- callers should degrade gracefully, not crash."""
    if not texts:
        return np.zeros((0, 1))
    chunks: list[np.ndarray] = []
    for start in range(0, len(texts), chunk_size):
        chunk = _corpus_cache.encode_texts(texts[start : start + chunk_size])
        if chunk is None:
            return None
        chunks.append(chunk)
    return np.vstack(chunks)


def pairwise_duplicates(
    rows: list[dict], threshold: Optional[float] = None
) -> list[dict]:
    """Exhaustive duplicate detection for organizer QA batch."""
    if threshold is None:
        threshold = SIMILARITY_THRESHOLD

    valid = [row for row in rows if (row.get("text") or "").strip()]
    flagged: list[dict] = []

    if len(valid) < 2:
        return flagged

    texts = [row["text"] for row in valid]
    embeddings = _encode_batched(texts)
    if embeddings is None:
        logger.warning(
            "QA batch: embeddings unavailable (remote embedder unreachable and no "
            "local model loaded) -- skipping semantic duplicate detection for this run."
        )
        return flagged

    similarities = embeddings @ embeddings.T

    for j in range(1, len(valid)):
        row_sims = similarities[j][:j]
        best_i = int(np.argmax(row_sims))
        best_score = float(row_sims[best_i])
        if best_score >= threshold:
            flagged.append(
                {
                    "id": valid[j]["id"],
                    "duplicate_of": valid[best_i]["id"],
                    "similarity": round(best_score, 4),
                }
            )

    return flagged
