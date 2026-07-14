"""Supabase client and data access helpers."""

from typing import Optional

from fastapi import HTTPException
from supabase import Client, create_client

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

_supabase: Optional[Client] = None


def get_supabase() -> Client:
    """Return a singleton Supabase client using the service role key."""
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise HTTPException(
                status_code=500,
                detail="Server missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY secrets.",
            )
        _supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


def fetch_all_submissions(columns: str, limit: Optional[int] = None) -> list[dict]:
    """Fetch rows from submissions, paginating past Supabase's 1000-row cap."""
    sb = get_supabase()
    rows: list[dict] = []
    page = 0
    page_size = 1000

    while True:
        start = page * page_size
        end = start + page_size - 1
        query = (
            sb.table("submissions")
            .select(columns)
            .order("submitted_at", desc=True)
            .range(start, end)
        )
        result = query.execute()
        batch = result.data or []
        rows.extend(batch)

        if len(batch) < page_size:
            break
        if limit and len(rows) >= limit:
            break
        page += 1

    return rows[:limit] if limit else rows


def verify_access_code(code: str) -> Optional[dict]:
    """Look up a team by access code via the verify_access_code RPC, using the
    service role key (bypasses RLS — this is the only place access codes are checked)."""
    sb = get_supabase()
    result = sb.rpc("verify_access_code", {"code": code}).execute()
    rows = result.data or []
    row = rows[0] if isinstance(rows, list) else rows
    return row or None


def insert_submission(row: dict) -> dict:
    sb = get_supabase()
    result = sb.table("submissions").insert(row).select("id").execute()
    data = result.data or []
    if not data:
        raise HTTPException(status_code=500, detail="Insert did not return a row")
    return data[0]


def fetch_submissions_for_team(team_id: str, columns: str) -> list[dict]:
    sb = get_supabase()
    result = (
        sb.table("submissions")
        .select(columns)
        .eq("team_id", team_id)
        .order("submitted_at", desc=True)
        .execute()
    )
    return result.data or []


def count_submissions_for_team(team_id: str) -> int:
    sb = get_supabase()
    result = (
        sb.table("submissions")
        .select("id", count="exact", head=True)
        .eq("team_id", team_id)
        .execute()
    )
    return result.count or 0


def update_judge_reviewed(submission_id: str, reviewed: bool) -> None:
    sb = get_supabase()
    sb.table("submissions").update({"judge_reviewed": reviewed}).eq("id", submission_id).execute()


def list_teams() -> list[dict]:
    sb = get_supabase()
    result = sb.table("teams").select(
        "team_id,team_name,access_code,member_emails,created_at"
    ).order("created_at", desc=True).execute()
    return result.data or []


def create_team(team_id: str, team_name: str, access_code: str, member_emails: list[str]) -> dict:
    sb = get_supabase()
    result = (
        sb.table("teams")
        .insert(
            {
                "team_id": team_id,
                "team_name": team_name,
                "access_code": access_code,
                "member_emails": member_emails,
            }
        )
        .execute()
    )
    data = result.data or []
    if not data:
        raise HTTPException(status_code=500, detail="Insert did not return a row")
    return data[0]
