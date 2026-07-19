"""Judge-facing endpoints — a separate identity from teams/admin. Judges log
in with their own access code and only ever see: the raw text of a sampled
submission, never the participant's labels, team name, or team_id (see
database.fetch_judge_queue, which selects id+text only).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

import database
from config import CATEGORIES
from models.schemas import (
    JudgeLabelRequest,
    JudgeLoginRequest,
    JudgeLoginResponse,
    JudgeQueueItem,
)
from utils.auth import create_token, require_judge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/judge", tags=["judge"])

JudgeSession = Annotated[dict, Depends(require_judge)]


@router.post("/login", response_model=JudgeLoginResponse)
def judge_login(body: JudgeLoginRequest):
    row = database.verify_judge_code(body.access_code.strip())
    if not row:
        raise HTTPException(status_code=401, detail="That access code doesn't match a judge.")

    token = create_token(role="judge", judge_id=row["judge_id"], judge_name=row["judge_name"])
    return JudgeLoginResponse(judge_id=row["judge_id"], judge_name=row["judge_name"], token=token)


@router.get("/queue", response_model=list[JudgeQueueItem])
def judge_queue(session: JudgeSession):
    """Sampled submissions this judge hasn't labeled yet. Text only --
    intentionally blind, so the judge's label isn't anchored by what the
    participant picked."""
    judge_id = session.get("judge_id")
    if not judge_id:
        raise HTTPException(status_code=401, detail="Invalid judge session")
    return database.fetch_judge_queue(judge_id)


@router.post("/label")
def submit_judge_label(body: JudgeLabelRequest, session: JudgeSession):
    judge_id = session.get("judge_id")
    if not judge_id:
        raise HTTPException(status_code=401, detail="Invalid judge session")

    row = {"submission_id": body.submission_id}
    for category in CATEGORIES:
        row[category] = getattr(body, category)

    result = database.upsert_judge_label(judge_id, row)
    logger.info("judge_label saved judge_id=%s submission_id=%s", judge_id, body.submission_id)
    return {"ok": True, "id": result.get("id")}
