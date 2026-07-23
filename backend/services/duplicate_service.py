"""Duplicate detection using RapidFuzz string matching.

This is the ML-free version optimized for Railway's free tier (~300MB RAM).
No sentence-transformers, no embeddings — just fast C-backed fuzzy matching.

For 2.5k submissions:
  - Live /check-submission: ~50-100ms per request (top-K extraction from corpus)
  - QA batch pairwise: ~1-10 minutes (O(n^2) comparisons, acceptable for one-time job)

If semantic similarity is needed later, deploy the embedder service and set
EMBEDDER_URL — this module can be extended to use remote embeddings with
the same tiered fallback pattern.
"""

import logging
import threading
import time
from typing import Optional, TypedDict

from rapidfuzz import fuzz, process

from config import (
    FUZZ_PREFILTER_THRESHOLD,
    FUZZ_TOP_K,
    SIMILARITY_THRESHOLD,
)
from database import count_submissions_for_team, fetch_submissions_for_team

logger = logging.getLogger(__name__)

SNIPPET_MAX_LEN = 100

# Only re-poll the DB row count this often, so a burst of concurrent checks
# doesn't turn into a burst of COUNT queries too.
_CACHE_REFRESH_INTERVAL_SECONDS = 15


class _CorpusCache:
    """In-process cache of one team's submission IDs and texts for fast
    duplicate checking, scoped to a single team_id.

    Refreshes from Supabase on a cheap cadence (row-count check every 15s).
    Updated incrementally in O(1) when this process inserts a new row.
    """

    def __init__(self, team_id: str) -> None:
        self._team_id = team_id
        self._lock = threading.Lock()
        self._ready = False
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._known_ids: set[str] = set()
        self._last_count_check = 0.0
        self._last_known_count: Optional[int] = None

    def _full_reload_locked(self) -> None:
        rows = fetch_submissions_for_team(self._team_id, "id, text")
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

        self._ids = ids
        self._texts = texts
        self._known_ids = seen
        self._last_known_count = len(ids)
        self._ready = True
        logger.info("Duplicate cache: full reload, %d rows", len(ids))

    def ensure_fresh(self) -> None:
        """Cheap freshness check: only hit the DB for a row COUNT at most
        once per _CACHE_REFRESH_INTERVAL_SECONDS, and only pay for a full
        reload if that count actually changed."""
        now = time.monotonic()
        with self._lock:
            if not self._ready:
                try:
                    self._full_reload_locked()
                except Exception as exc:
                    logger.warning(
                        "Duplicate cache: initial load failed (Supabase unreachable?) -- "
                        "treating as empty corpus until it recovers: %s",
                        exc,
                    )
                    self._ids, self._texts = [], []
                    self._known_ids = set()
                    self._last_known_count = None
                    self._ready = True
                self._last_count_check = now
                return
            if now - self._last_count_check < _CACHE_REFRESH_INTERVAL_SECONDS:
                return
            self._last_count_check = now

        try:
            current_count = count_submissions_for_team(self._team_id)
        except Exception as exc:
            logger.warning("Duplicate cache: could not check row count: %s", exc)
            return

        with self._lock:
            if current_count != self._last_known_count:
                self._full_reload_locked()

    def add(self, row_id: str, text: str) -> None:
        """O(1) incremental update after this process inserts a row."""
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

    def snapshot(self) -> tuple[list[str], list[str]]:
        with self._lock:
            return list(self._ids), list(self._texts)


_team_caches: dict[str, _CorpusCache] = {}
_team_caches_lock = threading.Lock()


def _get_team_cache(team_id: str) -> _CorpusCache:
    """Return the corpus cache for this team, creating it on first use.

    Each team gets its own independent cache instance, so duplicate checks
    for one team never see another team's submissions.
    """
    with _team_caches_lock:
        cache = _team_caches.get(team_id)
        if cache is None:
            cache = _CorpusCache(team_id)
            _team_caches[team_id] = cache
        return cache


def init_cache() -> None:
    """No-op at startup now that caches are created lazily per team_id on
    first use — kept as a callable for backward-compat with app startup."""
    return


def add_to_cache(team_id: str, row_id: str, text: str) -> None:
    """Called right after a successful /submit insert so the new row is
    immediately visible to future duplicate checks for that team, without a
    DB round-trip."""
    try:
        _get_team_cache(team_id).add(row_id, text)
    except Exception as exc:
        logger.warning("Duplicate cache: failed to add row %s for team_id=%s: %s", row_id, team_id, exc)


class DuplicateResult(TypedDict):
    flagged: bool
    similarity: float
    closest_match_snippet: str


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


def check_duplicate(text: str, team_id: str) -> DuplicateResult:
    """Compare text against that SAME team's own past submissions using
    RapidFuzz. Teams are never compared against each other's data.

    Uses process.extract to find top-K fuzzy matches from the team's corpus
    cache, then returns the best match above the similarity threshold.
    """
    normalized = text.strip()
    if not normalized:
        return _empty_result()

    corpus_cache = _get_team_cache(team_id)
    corpus_cache.ensure_fresh()
    id_list, text_list = corpus_cache.snapshot()

    if not text_list:
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

    # Find best match among candidates
    best_match = max(
        (fuzzy_hits[i] for i in range(len(fuzzy_hits)) if fuzzy_hits[i][2] in candidate_indices),
        key=lambda hit: hit[1],
    )
    best_text, fuzzy_score, _ = best_match
    best_similarity = fuzzy_score / 100.0
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


def pairwise_duplicates(
    rows: list[dict], threshold: Optional[float] = None
) -> list[dict]:
    """Exhaustive O(n^2) RapidFuzz duplicate detection for organizer QA batch.

    For 2.5k submissions: ~6.25M comparisons, ~1-10 minutes (acceptable for
    a one-time post-event batch job).
    """
    if threshold is None:
        threshold = SIMILARITY_THRESHOLD

    valid = [row for row in rows if (row.get("text") or "").strip()]
    flagged: list[dict] = []

    if len(valid) < 2:
        return flagged

    texts = [row["text"] for row in valid]

    logger.info("QA batch: starting pairwise RapidFuzz dedup on %d rows", len(valid))

    for j in range(1, len(valid)):
        best_score = 0.0
        best_i = 0
        for i in range(j):
            score = fuzz.ratio(texts[j], texts[i])
            if score > best_score:
                best_score = score
                best_i = i

        best_similarity = best_score / 100.0
        if best_similarity >= threshold:
            flagged.append(
                {
                    "id": valid[j]["id"],
                    "duplicate_of": valid[best_i]["id"],
                    "similarity": round(best_similarity, 4),
                }
            )

    logger.info("QA batch: found %d flagged duplicates", len(flagged))
    return flagged
