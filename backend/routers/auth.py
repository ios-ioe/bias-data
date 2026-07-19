"""Login endpoints — the only places that mint session tokens."""

import logging

from fastapi import APIRouter, HTTPException

import database
from config import ADMIN_BOOTSTRAP_SECRET
from database import verify_access_code
from models.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    BootstrapAdminRequest,
    LoginRequest,
    LoginResponse,
)
from services.admin_service import hash_password, verify_admin_credentials
from utils.auth import create_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    """Verify a team's email + access code server-side (service role key) and
    issue a signed session token. The frontend never queries the teams table
    directly. Both must match the same team -- an access code alone is not
    enough (it's shared by the whole team and could leak more easily than a
    specific member's email)."""
    row = verify_access_code(body.access_code.strip(), body.email.strip())
    if not row:
        raise HTTPException(
            status_code=401, detail="That email and access code don't match a team."
        )

    token = create_token(role="team", team_id=row["team_id"], team_name=row["team_name"])
    return LoginResponse(team_id=row["team_id"], team_name=row["team_name"], token=token)


@router.post("/admin/login", response_model=AdminLoginResponse)
def admin_login(body: AdminLoginRequest):
    """Verify an admin's email + password against the bcrypt hash stored in
    Supabase (see services/admin_service.py) and issue a signed session
    token. Replaces the old single shared ADMIN_PASSWORD env-var check --
    each organizer now has their own account."""
    admin = verify_admin_credentials(body.email.strip(), body.password)
    if not admin:
        raise HTTPException(status_code=401, detail="Wrong email or password.")

    token = create_token(role="admin", admin_id=admin["admin_id"], admin_name=admin["admin_name"])
    return AdminLoginResponse(admin_id=admin["admin_id"], admin_name=admin["admin_name"], token=token)


@router.post("/admin/bootstrap", response_model=AdminLoginResponse)
def bootstrap_admin(body: BootstrapAdminRequest):
    """Create the FIRST admin account. Only works if:
      1. ADMIN_BOOTSTRAP_SECRET is set on the server, AND
      2. the provided bootstrap_secret matches it, AND
      3. no admin account exists yet.
    Once at least one admin exists, this always 403s regardless of the
    secret -- so a leaked bootstrap secret can't be used to keep minting
    admin accounts after the first one. Further admins are created via the
    authenticated POST /admin/admins endpoint instead (see routers/admin.py)."""
    if not ADMIN_BOOTSTRAP_SECRET:
        raise HTTPException(status_code=403, detail="Bootstrap is disabled on this server.")
    if body.bootstrap_secret != ADMIN_BOOTSTRAP_SECRET:
        raise HTTPException(status_code=403, detail="Invalid bootstrap secret.")
    if database.count_admins() > 0:
        raise HTTPException(
            status_code=403,
            detail="An admin account already exists — bootstrap is only for the very first one. "
            "Use an existing admin account to create more from the Admin panel.",
        )

    password_hash = hash_password(body.password)
    row = database.create_admin(body.admin_name.strip(), body.email.strip(), password_hash)

    logger.info("Bootstrap: created first admin account admin_id=%s", row["admin_id"])
    token = create_token(role="admin", admin_id=row["admin_id"], admin_name=row["admin_name"])
    return AdminLoginResponse(admin_id=row["admin_id"], admin_name=row["admin_name"], token=token)
