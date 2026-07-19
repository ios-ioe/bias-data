"""
Signed, stateless session tokens for teams and organizers.

Why this exists: the frontend used to talk to Supabase directly with the anon
key, trusting whatever team_id the browser sent on every request. That let any
client insert/update rows under any team_id. Instead, /login and /admin/login
(in routers/auth.py) are the only places that mint a token, and every other
endpoint re-derives the caller's identity from the token instead of trusting
client-supplied fields.

Token format: "<payload_b64>.<hmac_hex>" where payload_b64 is base64url(JSON).
This is intentionally NOT a JWT library dependency — HMAC-SHA256 over a small
JSON payload is all we need, and it keeps requirements.txt unchanged.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Literal, TypedDict

from fastapi import Header, HTTPException

from config import SESSION_SECRET, SESSION_TTL_SECONDS

Role = Literal["team", "admin", "judge"]


class SessionPayload(TypedDict):
    role: Role
    team_id: str | None
    team_name: str | None
    judge_id: str | None
    judge_name: str | None
    admin_id: str | None
    admin_name: str | None
    exp: int


def _require_secret() -> bytes:
    if not SESSION_SECRET:
        # Fail loudly rather than silently signing with an empty/default key.
        raise HTTPException(
            status_code=500,
            detail="Server missing SESSION_SECRET secret — cannot issue or verify sessions.",
        )
    return SESSION_SECRET.encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(
    role: Role,
    team_id: str | None = None,
    team_name: str | None = None,
    judge_id: str | None = None,
    judge_name: str | None = None,
    admin_id: str | None = None,
    admin_name: str | None = None,
    ttl_seconds: int | None = None,
) -> str:
    secret = _require_secret()
    payload: SessionPayload = {
        "role": role,
        "team_id": team_id,
        "team_name": team_name,
        "judge_id": judge_id,
        "judge_name": judge_name,
        "admin_id": admin_id,
        "admin_name": admin_name,
        "exp": int(time.time()) + (ttl_seconds or SESSION_TTL_SECONDS),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64encode(payload_bytes)
    signature = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def _verify_raw(token: str) -> SessionPayload:
    secret = _require_secret()
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed session token")

    expected_signature = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid session token")

    try:
        payload: SessionPayload = json.loads(_b64decode(payload_b64))
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed session token")

    if payload.get("exp", 0) < time.time():
        raise HTTPException(status_code=401, detail="Session expired — please log in again")

    return payload


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer <token> header")
    return authorization.split(" ", 1)[1].strip()


def require_team(authorization: str | None = Header(default=None)) -> SessionPayload:
    """FastAPI dependency: verifies the token and requires role == team (or admin, which
    can act as any team for support/debugging purposes)."""
    token = _extract_bearer(authorization)
    payload = _verify_raw(token)
    if payload["role"] not in ("team", "admin"):
        raise HTTPException(status_code=403, detail="Team session required")
    if payload["role"] == "team" and not payload.get("team_id"):
        raise HTTPException(status_code=401, detail="Invalid session token")
    return payload


def require_admin(authorization: str | None = Header(default=None)) -> SessionPayload:
    """FastAPI dependency: verifies the token and requires role == admin."""
    token = _extract_bearer(authorization)
    payload = _verify_raw(token)
    if payload["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin session required")
    return payload


def require_judge(authorization: str | None = Header(default=None)) -> SessionPayload:
    """FastAPI dependency: verifies the token and requires role == judge.
    Judges are a separate identity from teams/admin -- a judge session
    carries no team_id and must never be usable against team-scoped routes
    (require_team explicitly does not accept role="judge")."""
    token = _extract_bearer(authorization)
    payload = _verify_raw(token)
    if payload["role"] != "judge":
        raise HTTPException(status_code=403, detail="Judge session required")
    return payload


def require_admin_or_judge(authorization: str | None = Header(default=None)) -> SessionPayload:
    """FastAPI dependency for routes that should stay hidden from
    participants entirely -- e.g. the leaderboard, so teams can't see each
    other's standings, only organizers and judges can."""
    token = _extract_bearer(authorization)
    payload = _verify_raw(token)
    if payload["role"] not in ("admin", "judge"):
        raise HTTPException(status_code=403, detail="Admin or judge session required")
    return payload
