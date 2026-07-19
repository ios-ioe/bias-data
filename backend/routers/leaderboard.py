"""Leaderboard — visible to organizers and judges only, NOT participant
teams. Shows relative standing (rank, team name, completion %); never a
team's raw submission counts, team_id, or per-category breakdown (see
services/leaderboard_service.build_public_leaderboard).

Kept out of teams' hands so participants can't track a rival's progress
mid-event and adjust strategy off of it -- only people running/judging the
competition see standings.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from services.leaderboard_service import build_public_leaderboard
from utils.auth import require_admin_or_judge

logger = logging.getLogger(__name__)

router = APIRouter(tags=["leaderboard"])

ViewerSession = Annotated[dict, Depends(require_admin_or_judge)]


@router.get("/leaderboard")
def leaderboard(session: ViewerSession):
    # Only teams have a team_id to match against ("is_you"); admin/judge
    # sessions don't, so every row simply comes back as not-you.
    return build_public_leaderboard(session.get("team_id"))
