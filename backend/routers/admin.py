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
import random

from config import CATEGORIES, NON_BIASED_TARGET, QUOTAS
from models.schemas import (
    AdminAccountResponse,
    CreateAdminRequest,
    CreateJudgeRequest,
    CreateTeamRequest,
    JudgeResponse,
    MarkReviewedRequest,
    SampleForJudgingRequest,
    SampleForJudgingResponse,
    TeamResponse,
)
from services.admin_service import hash_password
from services.email_service import send_team_access_code
from services.judge_service import build_judge_report
from services.leaderboard_service import build_leaderboard
from services.qa_batch import run_qa_batch
from utils.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

AdminSession = Annotated[dict, Depends(require_admin)]

_ADMIN_COLUMNS = (
    "id,team_id,text,"
    + ",".join(f'"{c}"' if c[0].isupper() else c for c in CATEGORIES)
    + ",source_platform,comment,submitted_at,flag_duplicate,flag_pii,judge_reviewed"
)


@router.get("/submissions")
def all_submissions(_: AdminSession):
    """Full submissions table — admin only. Teams cannot reach this endpoint."""
    return database.fetch_all_submissions(_ADMIN_COLUMNS)


@router.get("/leaderboard")
def leaderboard(_: AdminSession):
    """Full ranked team standings — team_id, team_name, raw + credited
    submission counts, and quota completion %, ranked by completion % (see
    services/leaderboard_service). Every team is included, even ones with
    zero submissions so far. A trimmed rank/name/% view of the same ranking
    is also available to every logged-in team at GET /leaderboard."""
    return build_leaderboard(force_refresh=True)


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
        "Disablity", "source_platform", "comment", "submitted_at",
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


# --- Judging (post-event blind review) --------------------------------------


@router.get("/judges", response_model=list[JudgeResponse])
def get_judges(_: AdminSession):
    """List all judges with their access codes, so an organizer can hand them
    out. Same pattern as GET /admin/teams."""
    return database.list_judges()


@router.post("/judges", response_model=JudgeResponse)
def add_judge(body: CreateJudgeRequest, _: AdminSession):
    """Create a judge with a freshly generated access code. Judges are a
    separate identity from teams/admin -- this code only ever grants access
    to GET /judge/queue and POST /judge/label, never submission or admin
    routes."""
    slug = _slugify(body.judge_name)

    row = None
    last_exc: Exception | None = None
    for _attempt in range(_MAX_ACCESS_CODE_ATTEMPTS):
        access_code = _generate_access_code(slug)
        try:
            row = database.create_judge(body.judge_name.strip(), access_code)
            break
        except Exception as exc:  # likely a unique constraint hit on access_code
            last_exc = exc
            logger.warning("Access code collision creating judge %s, retrying: %s", body.judge_name, exc)

    if row is None:
        logger.error("Failed to create judge after %d attempts: %s", _MAX_ACCESS_CODE_ATTEMPTS, last_exc)
        raise HTTPException(status_code=500, detail="Failed to create judge — access_code collision, please retry.")

    logger.info("Admin created judge judge_id=%s", row["judge_id"])
    return JudgeResponse(**row)


# --- Admin account management ------------------------------------------------
# The very FIRST admin account is created via the unauthenticated
# POST /admin/bootstrap (see routers/auth.py), gated by ADMIN_BOOTSTRAP_SECRET.
# Every admin account after that is created here, by an already-logged-in
# admin -- same "authenticated action creates the next credential" pattern
# as team/judge creation.


@router.get("/admins", response_model=list[AdminAccountResponse])
def get_admins(_: AdminSession):
    """List all admin accounts (name + email only, never password hashes)."""
    return database.list_admins()


@router.post("/admins", response_model=AdminAccountResponse)
def add_admin(body: CreateAdminRequest, _: AdminSession):
    """Create another admin account. Requires being logged in as an admin
    already -- there's no open signup for admin access."""
    password_hash = hash_password(body.password)
    try:
        row = database.create_admin(body.admin_name.strip(), body.email.strip(), password_hash)
    except Exception as exc:
        logger.warning("Failed to create admin %s (likely duplicate email): %s", body.email, exc)
        raise HTTPException(status_code=400, detail="That email is already registered as an admin.")

    logger.info("Admin created another admin account admin_id=%s", row["admin_id"])
    return AdminAccountResponse(admin_id=row["admin_id"], admin_name=row["admin_name"], email=row["email"])


@router.post("/judge-sample", response_model=SampleForJudgingResponse)
def sample_for_judging(body: SampleForJudgingRequest, _: AdminSession):
    """Randomly pick `per_team` submissions from EACH team (not a flat pool)
    and mark them for judging. Stratified per team so every team gets a
    fair, comparable sample regardless of how many teams there are -- a flat
    random pick across all submissions could easily leave some teams with
    zero items sampled by chance. Teams with fewer unsampled/non-duplicate
    rows than `per_team` just get all of what they have (never an error).
    Intended to run once, after the event closes and the QA batch
    (POST /admin/qa-batch) has already flagged duplicates."""
    candidates_by_team = database.fetch_unsampled_submission_ids_by_team()

    chosen: list[str] = []
    teams_sampled = 0
    teams_skipped = 0
    for team_id, ids in candidates_by_team.items():
        if not ids:
            teams_skipped += 1
            continue
        take = min(body.per_team, len(ids))
        chosen.extend(random.sample(ids, k=take))
        teams_sampled += 1

    if chosen:
        database.mark_sampled_for_judging(chosen)

    logger.info(
        "Admin sampled %d submissions for judging across %d teams (%d skipped, no candidates)",
        len(chosen), teams_sampled, teams_skipped,
    )
    return SampleForJudgingResponse(
        sampled=len(chosen), teams_sampled=teams_sampled, teams_skipped_insufficient=teams_skipped
    )


@router.get("/judge-report")
def judge_report(_: AdminSession):
    """Compares each judge's blind label against the participant's original
    label, per category, for every sampled submission. Admin-only -- this is
    the one place original labels and judge labels are ever shown together."""
    return build_judge_report()
