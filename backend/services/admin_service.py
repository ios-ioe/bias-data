"""Admin account management -- password hashing/verification lives here,
kept separate from database.py so the bcrypt dependency and comparison
logic are in one obvious place rather than scattered across callers.

Passwords are never compared in SQL. verify_admin_email (the Supabase RPC)
only returns the stored bcrypt hash for a given email; the actual
credential check happens here, in Python, with bcrypt.checkpw -- a
constant-time comparison against the hash, same security property
hmac.compare_digest gave the old single ADMIN_PASSWORD check.
"""

import logging
from typing import Optional

import bcrypt

import database

logger = logging.getLogger(__name__)

_BCRYPT_ROUNDS = 12


def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(_BCRYPT_ROUNDS)).decode("utf-8")


def verify_admin_credentials(email: str, password: str) -> Optional[dict]:
    """Look up an admin by email and check the password against the stored
    bcrypt hash. Returns {admin_id, admin_name} on success, None on any
    mismatch (wrong email OR wrong password -- deliberately not
    distinguished, so a login failure never reveals whether the email
    exists)."""
    row = database.fetch_admin_by_email(email)
    if not row:
        # Still run a bcrypt check against a dummy hash so a nonexistent
        # email doesn't return measurably faster than a wrong password for
        # a real one (timing side-channel on account enumeration).
        bcrypt.checkpw(b"", bcrypt.gensalt(_BCRYPT_ROUNDS))
        return None

    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8"))
    except (ValueError, TypeError) as exc:
        logger.error("Admin password hash for %s is malformed: %s", email, exc)
        return None

    if not ok:
        return None

    return {"admin_id": row["admin_id"], "admin_name": row["admin_name"]}
