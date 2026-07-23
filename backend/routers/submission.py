"""Submission endpoints — checking, saving, and reading back a team's own rows.

Every write and every "my data" read is scoped to the team_id embedded in the
caller's session token (see utils/auth.py), never to a team_id supplied in the
request body. This is what stops one team from submitting as, or reading,
another team's data.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

import database
from config import CATEGORIES
from models.schemas import (
    CheckSubmissionRequest,
    CheckSubmissionResponse,
    DuplicateCheckResult,
    MyCountResponse,
    PiiCheckResult,
    SubmitRequest,
    SubmitResponse,
)
from services.duplicate_service import add_to_cache, check_duplicate
from services.pii_service import scan_pii
from utils.auth import require_team
from utils.exceptions import AppError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["submission"])

TeamSession = Annotated[dict, Depends(require_team)]


@router.post("/check-submission", response_model=CheckSubmissionResponse)
def check_submission(body: CheckSubmissionRequest, session: TeamSession):
    """
    Run duplicate and PII checks on submission text.

    Duplicate detection only compares against the caller's OWN team's past
    submissions — team_id is taken from the session token (never trusted
    from the request body), same as every other write/read in this router.

    Returns warnings only — never rejects a submission. If neither the
    remote embedder Space nor a local model is reachable, check_duplicate()
    degrades to fuzzy-string matching rather than failing outright — this
    endpoint should never be the reason a participant can't submit.
    """
    team_id = session["team_id"]
    if not team_id:
        # Admin sessions have no team_id of their own -- there's no per-team
        # corpus to check against, so fail clearly rather than silently
        # checking against an empty/wrong cache (same guard as /submit).
        raise HTTPException(
            status_code=400,
            detail="Admin sessions cannot run duplicate checks — log in as a team to check.",
        )

    logger.info("check-submission received for team_id=%s", team_id)

    pii_result = scan_pii(body.text)

    try:
        duplicate_result = check_duplicate(body.text, team_id=team_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Duplicate check failed: %s", exc)
        raise AppError("Could not reach the database for duplicate check", status_code=503) from exc

    response = CheckSubmissionResponse(
        duplicate=DuplicateCheckResult(**duplicate_result),
        pii=PiiCheckResult(**pii_result),
    )

    logger.info(
        "check-submission complete team_id=%s duplicate_flagged=%s pii_flagged=%s",
        team_id,
        response.duplicate.flagged,
        response.pii.flagged,
    )

    return response


@router.post("/submit", response_model=SubmitResponse)
def submit(body: SubmitRequest, session: TeamSession):
    """Insert a submission for the logged-in team. team_id comes from the
    session token, not from the request body — a team can never write rows
    under another team's id."""
    team_id = session["team_id"]
    if not team_id:
        # An admin session has role="team"-compatible access (for support/
        # debugging) but no team_id of its own -- writing would otherwise
        # insert a null team_id and blow up on the NOT NULL/FK constraint
        # with a confusing 500. Fail clearly instead.
        raise HTTPException(
            status_code=400,
            detail="Admin sessions cannot submit rows — log in as a team to submit.",
        )

    text = body.text.strip()
    row = {
        "team_id": team_id,
        "text": text,
        "source_platform": body.source_platform,
        "comment": body.comment,
        "flag_duplicate": body.flag_duplicate,
        "flag_pii": body.flag_pii,
        "client_submission_id": body.client_submission_id,
    }
    for category in CATEGORIES:
        row[category] = getattr(body, category)

    result = database.insert_submission(row)
    logger.info("submission saved team_id=%s id=%s", team_id, result.get("id"))

    # Keep this team's duplicate-check cache warm without waiting for its
    # next poll -- this row is now a candidate for this team's very next
    # check (other teams' caches are untouched).
    add_to_cache(team_id, result["id"], text)

    return SubmitResponse(id=result["id"])


@router.get("/my-submissions")
def my_submissions(session: TeamSession):
    """Return only the logged-in team's own rows. Other teams' data never
    leaves the backend for a non-admin session."""
    team_id = session["team_id"]
    columns = "id,team_id,text," + ",".join(
        f'"{c}"' if c[0].isupper() else c for c in CATEGORIES
    ) + ",source_platform,comment,submitted_at,flag_duplicate,flag_pii,judge_reviewed"
    return database.fetch_submissions_for_team(team_id, columns)


@router.get("/my-count", response_model=MyCountResponse)
def my_count(session: TeamSession):
    team_id = session["team_id"]
    return MyCountResponse(count=database.count_submissions_for_team(team_id))
