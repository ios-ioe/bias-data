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


def count_all_submissions() -> int:
    """Cheap row count, used to decide whether the in-process duplicate-check
    cache needs a full reload (see services/duplicate_service.py)."""
    sb = get_supabase()
    result = sb.table("submissions").select("id", count="exact", head=True).execute()
    return result.count or 0


def verify_access_code(code: str, email: str) -> Optional[dict]:
    """Look up a team by access code AND member email via the
    verify_access_code RPC, using the service role key (bypasses RLS — this
    is the only place access codes are checked). Both must match: the code
    alone is not enough."""
    sb = get_supabase()
    result = sb.rpc("verify_access_code", {"code": code, "member_email": email}).execute()
    rows = result.data or []
    row = rows[0] if isinstance(rows, list) else rows
    return row or None


def insert_submission(row: dict) -> dict:
    sb = get_supabase()
    try:
        result = sb.table("submissions").insert(row).select("id").execute()
    except Exception as exc:
        client_submission_id = row.get("client_submission_id")
        team_id = row.get("team_id")
        # Unique violation on (team_id, client_submission_id) means this is a
        # retried submit (offline outbox) whose earlier attempt actually
        # succeeded server-side but never got its response back to the
        # client. Treat that as success and hand back the existing row
        # instead of erroring the retry.
        if client_submission_id and "duplicate key" in str(exc).lower():
            existing = (
                sb.table("submissions")
                .select("id")
                .eq("team_id", team_id)
                .eq("client_submission_id", client_submission_id)
                .limit(1)
                .execute()
            )
            if existing.data:
                return existing.data[0]
        raise HTTPException(status_code=500, detail=f"Insert failed: {exc}") from exc

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


# --- Judging (post-event blind review) --------------------------------------


def verify_judge_code(code: str) -> Optional[dict]:
    """Look up a judge by access code via the verify_judge_code RPC, same
    pattern as verify_access_code for teams -- service role only."""
    sb = get_supabase()
    result = sb.rpc("verify_judge_code", {"code": code}).execute()
    rows = result.data or []
    row = rows[0] if isinstance(rows, list) else rows
    return row or None


def create_judge(judge_name: str, access_code: str) -> dict:
    sb = get_supabase()
    result = sb.table("judges").insert(
        {"judge_name": judge_name, "access_code": access_code}
    ).execute()
    data = result.data or []
    if not data:
        raise HTTPException(status_code=500, detail="Insert did not return a row")
    return data[0]


def list_judges() -> list[dict]:
    sb = get_supabase()
    result = (
        sb.table("judges")
        .select("judge_id,judge_name,access_code,created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def fetch_unsampled_submission_ids_by_team() -> dict[str, list[str]]:
    """Candidates for judging, grouped by team_id: not already sampled, and
    not already flagged as a duplicate -- no point spending judge time on a
    row that won't be credited anyway. Grouped so sampling can be done
    per-team (stratified), rather than one flat pool that could leave some
    teams with zero items sampled just by chance."""
    rows = fetch_all_submissions("id,team_id,sampled_for_judging,flag_duplicate")
    by_team: dict[str, list[str]] = {}
    for row in rows:
        if row.get("sampled_for_judging") or row.get("flag_duplicate"):
            continue
        team_id = row.get("team_id")
        if not team_id:
            continue
        by_team.setdefault(team_id, []).append(row["id"])
    return by_team


def mark_sampled_for_judging(submission_ids: list[str]) -> None:
    sb = get_supabase()
    for start in range(0, len(submission_ids), 200):
        batch = submission_ids[start : start + 200]
        if batch:
            sb.table("submissions").update(
                {"sampled_for_judging": True, "sampled_at": "now()"}
            ).in_("id", batch).execute()


def fetch_judge_queue(judge_id: str) -> list[dict]:
    """All sampled submissions this judge hasn't labeled yet. Text only --
    callers (routers/judge.py) must not select or return original labels."""
    sb = get_supabase()
    already = (
        sb.table("judge_labels")
        .select("submission_id")
        .eq("judge_id", judge_id)
        .execute()
    )
    already_ids = {row["submission_id"] for row in (already.data or [])}

    result = (
        sb.table("submissions")
        .select("id,text")
        .eq("sampled_for_judging", True)
        .execute()
    )
    rows = result.data or []
    return [row for row in rows if row["id"] not in already_ids]


def upsert_judge_label(judge_id: str, row: dict) -> dict:
    sb = get_supabase()
    payload = {**row, "judge_id": judge_id}
    result = (
        sb.table("judge_labels")
        .upsert(payload, on_conflict="submission_id,judge_id")
        .execute()
    )
    data = result.data or []
    if not data:
        raise HTTPException(status_code=500, detail="Judge label upsert did not return a row")
    return data[0]


def fetch_sampled_submissions_with_labels(columns: str) -> list[dict]:
    """Sampled submissions (with their original labels) for the admin
    judge-report -- admin-only, never exposed to judges."""
    sb = get_supabase()
    result = (
        sb.table("submissions")
        .select(columns)
        .eq("sampled_for_judging", True)
        .execute()
    )
    return result.data or []


def fetch_all_judge_labels() -> list[dict]:
    sb = get_supabase()
    result = sb.table("judge_labels").select("*").execute()
    return result.data or []


# --- Admin accounts (multiple named organizer logins) ----------------------


def fetch_admin_by_email(email: str) -> Optional[dict]:
    """Look up an admin by email via the verify_admin_email RPC (service
    role only) -- returns the bcrypt hash for admin_service.py to check,
    never compared in SQL."""
    sb = get_supabase()
    result = sb.rpc("verify_admin_email", {"admin_email": email}).execute()
    rows = result.data or []
    row = rows[0] if isinstance(rows, list) else rows
    return row or None


def count_admins() -> int:
    sb = get_supabase()
    result = sb.table("admins").select("admin_id", count="exact").execute()
    return result.count or 0


def create_admin(admin_name: str, email: str, password_hash: str) -> dict:
    sb = get_supabase()
    result = (
        sb.table("admins")
        .insert({"admin_name": admin_name, "email": email, "password_hash": password_hash})
        .execute()
    )
    data = result.data or []
    if not data:
        raise HTTPException(status_code=500, detail="Insert did not return a row")
    return data[0]


def list_admins() -> list[dict]:
    sb = get_supabase()
    result = (
        sb.table("admins")
        .select("admin_id,admin_name,email,created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


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
