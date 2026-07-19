"""Leaderboard ranking — one shared source of truth for both the organizer's
full admin view and the lightweight live standings every logged-in team can
see.

Ranking is by quota COMPLETION % (the tool's actual goal — filling every
bias category's target plus the non-biased target), not raw submission
count. Raw-count ranking rewards mass-submitting near-duplicate or
single-category sentences; completion % rewards actually finishing the
assignment. Rows flagged as duplicates never count toward either the raw
total or the quota progress used for ranking.

Every team that exists is included, even ones with zero submissions so
far, so a fresh team shows up at 0% instead of being invisible on the
board until their first save.
"""

import logging
import threading
import time
from typing import Optional

import database
from config import CATEGORIES, NON_BIASED_TARGET, QUOTAS

logger = logging.getLogger(__name__)

# Recomputing this means re-fetching and re-aggregating the whole
# submissions table. Fine at hackathon scale for one request, but not
# something every team's browser polling the live board every ~15s should
# each trigger a fresh DB round-trip for. Cache briefly and share the
# result across every caller (team board + admin board both hit this).
_CACHE_TTL_SECONDS = 8.0
_cache_lock = threading.Lock()
_cached_at = 0.0
_cached_result: list[dict] = []


def _quota_progress(team_rows: list[dict]) -> dict:
    """Same capped-progress math as the frontend's config/quotas.js and
    services/qa_batch.py's quota report, kept here as the single backend
    source of truth for anything that ranks teams."""
    earned = 0
    need = sum(QUOTAS.get(category, 0) for category in CATEGORIES) + NON_BIASED_TARGET

    for category in CATEGORIES:
        count = sum(1 for row in team_rows if int(row.get(category) or 0) == 1)
        earned += min(count, QUOTAS.get(category, 0))

    non_biased = sum(
        1 for row in team_rows if all(int(row.get(category) or 0) == 0 for category in CATEGORIES)
    )
    earned += min(non_biased, NON_BIASED_TARGET)

    pct = round((earned / need) * 100) if need else 0
    return {"earned": earned, "need": need, "pct": pct}


def _compute() -> list[dict]:
    teams = database.list_teams()
    columns = "team_id,flag_duplicate," + ",".join(
        f'"{c}"' if c[0].isupper() else c for c in CATEGORIES
    )
    rows = database.fetch_all_submissions(columns)

    credited_rows_by_team: dict[str, list[dict]] = {}
    total_by_team: dict[str, int] = {}
    credited_by_team: dict[str, int] = {}

    for row in rows:
        team_id = row.get("team_id")
        if not team_id:
            continue
        total_by_team[team_id] = total_by_team.get(team_id, 0) + 1
        if row.get("flag_duplicate"):
            continue  # duplicates never count toward rank or quota progress
        credited_rows_by_team.setdefault(team_id, []).append(row)
        credited_by_team[team_id] = credited_by_team.get(team_id, 0) + 1

    entries = []
    for team in teams:
        team_id = team["team_id"]
        progress = _quota_progress(credited_rows_by_team.get(team_id, []))
        entries.append(
            {
                "team_id": team_id,
                "team_name": team["team_name"],
                "total_submissions": total_by_team.get(team_id, 0),
                "credited_submissions": credited_by_team.get(team_id, 0),
                "completion_pct": progress["pct"],
                "quota_units_earned": progress["earned"],
                "quota_units_total": progress["need"],
            }
        )

    # Rank by completion %, tie-broken by credited submissions, then name --
    # ties are common (e.g. every team at 0% before the event starts) and
    # should share a rank rather than getting an arbitrary index apart.
    entries.sort(
        key=lambda e: (-e["completion_pct"], -e["credited_submissions"], e["team_name"].lower())
    )

    ranked: list[dict] = []
    prev_key: Optional[tuple] = None
    rank = 0
    for index, entry in enumerate(entries):
        key = (entry["completion_pct"], entry["credited_submissions"])
        if key != prev_key:
            rank = index + 1
            prev_key = key
        ranked.append({"rank": rank, **entry})
    return ranked


def build_leaderboard(force_refresh: bool = False) -> list[dict]:
    """Full ranked standings, including fields only organizers should see
    (team_id, raw submission totals). Cached briefly so a room full of
    teams polling the board doesn't turn into a full-table re-fetch and
    re-aggregation per request."""
    global _cached_at, _cached_result

    now = time.monotonic()
    with _cache_lock:
        if not force_refresh and _cached_result and now - _cached_at < _CACHE_TTL_SECONDS:
            return _cached_result

    try:
        result = _compute()
    except Exception:
        logger.exception("Leaderboard: failed to compute standings")
        with _cache_lock:
            if _cached_result:
                # Serve the last good snapshot instead of a broken/empty
                # board if Supabase hiccups mid-event.
                return _cached_result
        raise

    with _cache_lock:
        _cached_result = result
        _cached_at = now
    return result


def build_public_leaderboard(viewer_team_id: Optional[str] = None) -> list[dict]:
    """Standings view: rank, name, completion %, and credited submission
    count. Raw counts used to be withheld here because teams themselves
    could see this endpoint and might reverse-engineer a rival's category
    gaps -- but /leaderboard is now judge/admin only (see routers/leaderboard.py),
    so showing the actual number of submissions collected is safe and more
    useful for organizers than a bare percentage."""
    return [
        {
            "rank": entry["rank"],
            "team_name": entry["team_name"],
            "completion_pct": entry["completion_pct"],
            "credited_submissions": entry["credited_submissions"],
            "total_submissions": entry["total_submissions"],
            "is_you": entry["team_id"] == viewer_team_id,
        }
        for entry in build_leaderboard()
    ]
