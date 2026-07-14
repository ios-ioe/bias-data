"""Organizer-only endpoints. Every route here requires a valid admin session
token (see utils/auth.require_admin) verified server-side — unlike the old
frontend gate, the password check and the resulting authorization never touch
the browser bundle."""

import logging
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

import database
from config import CATEGORIES, NON_BIASED_TARGET, QUOTAS
from models.schemas import CreateTeamRequest, MarkReviewedRequest, TeamResponse
from services.email_service import send_team_access_code
from services.qa_batch import run_qa_batch
from utils.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

AdminSession = Annotated[dict, Depends(require_admin)]

_ADMIN_COLUMNS = (
    "id,team_id,text,"
    + ",".join(f'"{c}"' if c[0].isupper() else c for c in CATEGORIES)
    + ",source_platform,source_date,submitted_at,flag_duplicate,flag_pii,judge_reviewed"
)


@router.get("/submissions")
def all_submissions(_: AdminSession):
    """Full submissions table — admin only. Teams cannot reach this endpoint."""
    return database.fetch_all_submissions(_ADMIN_COLUMNS)


@router.get("/leaderboard")
def leaderboard(_: AdminSession):
    """Per-team credited counts (excludes rows flagged as duplicates), ranked.
    This replaces the old public /leaderboard route — only organizers can see
    team rankings now."""
    rows = database.fetch_all_submissions(
        "team_id,flag_duplicate," + ",".join(f'"{c}"' if c[0].isupper() else c for c in CATEGORIES)
    )
    totals: dict[str, dict] = {}
    for row in rows:
        team_id = row.get("team_id")
        if not team_id:
            continue
        bucket = totals.setdefault(team_id, {"team_id": team_id, "total": 0, "credited": 0})
        bucket["total"] += 1
        if not row.get("flag_duplicate"):
            bucket["credited"] += 1

    ranked = sorted(totals.values(), key=lambda r: r["credited"], reverse=True)
    return ranked


@router.post("/mark-reviewed")
def mark_reviewed(body: MarkReviewedRequest, _: AdminSession):
    database.update_judge_reviewed(body.id, body.reviewed)
    return {"ok": True}


@router.post("/qa-batch")
def qa_batch(_: AdminSession):
    logger.info("Admin triggered QA batch")
    return run_qa_batch()


@router.get("/export")
def export_json(_: AdminSession):
    """Full export with exact published dataset column names."""
    rows = database.fetch_all_submissions(_ADMIN_COLUMNS)
    export_keys = [
        "team_id", "text", "gender", "religional", "caste", "religion",
        "appearence", "socialstatus", "amiguity", "political", "Age",
        "Disablity", "source_platform", "source_date", "submitted_at",
        "flag_duplicate", "flag_pii", "judge_reviewed",
    ]
    return [{key: row.get(key) for key in export_keys} for row in rows]


@router.get("/quota-report")
def quota_report(_: AdminSession):
    rows = database.fetch_all_submissions(
        "team_id," + ",".join(f'"{c}"' if c[0].isupper() else c for c in CATEGORIES)
    )
    team_ids = sorted({r["team_id"] for r in rows if r.get("team_id")})
    report = {}
    for team_id in team_ids:
        team_rows = [r for r in rows if r.get("team_id") == team_id]
        team_report = {}
        for category in CATEGORIES:
            count = sum(1 for r in team_rows if int(r.get(category) or 0) == 1)
            team_report[category] = {"count": count, "required": QUOTAS.get(category, 0)}
        non_biased = sum(
            1 for r in team_rows if all(int(r.get(c) or 0) == 0 for c in CATEGORIES)
        )
        team_report["non_biased"] = {"count": non_biased, "required": NON_BIASED_TARGET}
        report[team_id] = team_report
    return report


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "team"


def _generate_access_code(slug: str) -> str:
    # e.g. "everest-73920" -- team name slug + a random 5-digit number, shared
    # by the whole team. secrets.randbelow keeps this cryptographically random
    # (not guessable/sequential) while staying short enough to type by hand.
    suffix = f"{secrets.randbelow(100_000):05d}"
    return f"{slug[:20]}-{suffix}"


@router.get("/teams", response_model=list[TeamResponse])
def get_teams(_: AdminSession):
    """List all teams with their access codes, so an organizer can copy one and
    send it manually via Gmail/whatever mail tool. Only reachable with an admin
    session — access codes never appear anywhere a team member can see them."""
    return database.list_teams()


_MAX_ACCESS_CODE_ATTEMPTS = 5


@router.post("/teams", response_model=TeamResponse)
def add_team(body: CreateTeamRequest, _: AdminSession):
    """Create a new team with a freshly generated access code and email it to
    every member. This replaces hand-editing seed.sql for every team --
    organizers can add teams as they register, any time before or during the
    event.

    Login model: ONE shared access code per team (format
    "<team_name_slug>-<5 digit number>", e.g. "everest-73920"). Every member
    types the same code to log in -- there's no separate per-member token.

    Requires 2-4 member_emails (validated by CreateTeamRequest). The access
    code is emailed to all of them via Resend (services/email_service.py). If
    RESEND_API_KEY isn't configured, or the send fails, team creation still
    succeeds -- the response's email_sent flag tells the organizer whether
    they need to copy the access_code and send it manually instead.
    """
    slug = _slugify(body.team_name)
    team_id = f"team_{slug}_{secrets.token_hex(2)}"

    row = None
    last_exc: Exception | None = None
    for _attempt in range(_MAX_ACCESS_CODE_ATTEMPTS):
        access_code = _generate_access_code(slug)
        try:
            row = database.create_team(team_id, body.team_name.strip(), access_code, body.member_emails)
            break
        except Exception as exc:  # likely a unique constraint hit on access_code
            last_exc = exc
            logger.warning("Access code collision for team_id=%s, retrying: %s", team_id, exc)

    if row is None:
        logger.error("Failed to create team after %d attempts: %s", _MAX_ACCESS_CODE_ATTEMPTS, last_exc)
        raise HTTPException(status_code=500, detail="Failed to create team — access_code collision, please retry.")

    email_sent = send_team_access_code(row["team_name"], row["access_code"], row.get("member_emails") or [])

    logger.info("Admin created team team_id=%s email_sent=%s", team_id, email_sent)
    return TeamResponse(**row, email_sent=email_sent)
