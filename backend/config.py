"""Application configuration loaded from environment variables."""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Comma-separated list of origins allowed to call this API from a browser.
# Defaults cover local dev (Vite's default port) only -- before hosting,
# set CORS_ALLOWED_ORIGINS to your deployed frontend's actual origin(s),
# e.g. "https://your-frontend.vercel.app". Using "*" here (the old default)
# meant any website could make browser-based calls to this API; tightening
# this doesn't affect server-to-server calls (e.g. Postman, curl), only
# what a browser will permit a *different* website's JS to call.
_default_cors_origins = "http://localhost:5173,http://127.0.0.1:5173"
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", _default_cors_origins).split(",")
    if origin.strip()
]

# Secret used to sign team/admin session tokens issued by this backend.
# MUST be set in production — a missing secret means sessions cannot be trusted.
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")

# One-time bootstrap secret for creating the FIRST admin account (see
# POST /admin/bootstrap in routers/admin.py). Admins now live in Supabase
# (see the `admins` table + services/admin_service.py), each with their own
# email/password -- this replaces the old single shared ADMIN_PASSWORD env
# var. This secret only works while the admins table is empty; once at least
# one admin exists, /admin/bootstrap always 403s regardless of this value,
# so it can't be used to keep minting admin accounts if it ever leaks.
# Unset (empty) disables bootstrapping entirely -- set it temporarily, create
# your first admin, then you can remove it (not required, but tidy).
ADMIN_BOOTSTRAP_SECRET = os.environ.get("ADMIN_BOOTSTRAP_SECRET", "")

# Resend (https://resend.com) is used to email each team's access code to all
# of its member_emails when a team is created. If RESEND_API_KEY is unset,
# email sending is skipped (logged as a warning) and the organizer falls back
# to copying the access code from the admin Teams tab -- team creation is
# never blocked on email delivery succeeding.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "onboarding@resend.dev")

# How long a team/admin session token stays valid, in seconds. Default: 20 hours
# (covers a one-day event with margin) so all 2-4 members of a team can stay logged
# in on separate devices without re-entering the access code.
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", str(20 * 60 * 60)))

SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.90"))

# --- Optional standalone embedder Space -------------------------------------
# If set, this backend calls out to a separate HF Space (see embedder/) that
# does nothing but text -> embedding, instead of loading the model in this
# process. Keeps ML compute off the box that holds Supabase secrets and auth,
# and lets you restart/scale the embedder independently. If unset, falls back
# to loading the model in-process exactly as before (single-Space deploy).
EMBEDDER_URL = os.environ.get("EMBEDDER_URL", "").rstrip("/")
# Shared secret sent as X-API-Key to the embedder Space, if it's deployed
# with EMBEDDER_API_KEY set there too (see embedder/app.py's _check_auth).
# Without this being set on BOTH sides, a publicly-deployed embedder Space
# is an open, unauthenticated compute endpoint anyone on the internet can
# call -- set it here to match whatever you set on the Space itself.
EMBEDDER_API_KEY = os.environ.get("EMBEDDER_API_KEY", "")
EMBEDDER_TIMEOUT_SECONDS = float(os.environ.get("EMBEDDER_TIMEOUT_SECONDS", "3.0"))
# After this many consecutive embedder failures, stop calling it for
# EMBEDDER_CIRCUIT_COOLDOWN_SECONDS and fall back to fuzzy-only matching
# (duplicate checks degrade gracefully instead of piling up slow timeouts).
EMBEDDER_CIRCUIT_FAILURE_THRESHOLD = int(os.environ.get("EMBEDDER_CIRCUIT_FAILURE_THRESHOLD", "3"))
EMBEDDER_CIRCUIT_COOLDOWN_SECONDS = float(os.environ.get("EMBEDDER_CIRCUIT_COOLDOWN_SECONDS", "30"))

# NER (used only by the organizer's QA batch, not per-submission) shares the
# same EMBEDDER_URL/embedder Space as embeddings, but needs a much longer
# timeout: it's a single one-off call across every submission at once
# (possibly hundreds), and the Space may need to cold-start and download the
# NER model on its very first call. No circuit breaker here -- unlike /embed,
# this is never called per-request, so there's no risk of pile-up.
NER_TIMEOUT_SECONDS = float(os.environ.get("NER_TIMEOUT_SECONDS", "60.0"))

# RapidFuzz pre-filter: skip embedding when string similarity is below this score.
FUZZ_PREFILTER_THRESHOLD = int(os.environ.get("FUZZ_PREFILTER_THRESHOLD", "55"))
FUZZ_TOP_K = int(os.environ.get("FUZZ_TOP_K", "25"))

# Batch QA uses a slightly stricter threshold than live checks.
BATCH_SIMILARITY_THRESHOLD = float(
    os.environ.get("BATCH_SIMILARITY_THRESHOLD", str(SIMILARITY_THRESHOLD))
)

# Category columns — names must match the published dataset exactly.
CATEGORIES = [
    "gender",
    "religional",
    "caste",
    "religion",
    "appearence",
    "socialstatus",
    "amiguity",
    "political",
    "Age",
    "Disablity",
]

QUOTAS = {
    "gender": 20,
    "caste": 16,
    "religional": 16,
    "religion": 14,
    "appearence": 14,
    "socialstatus": 14,
    "Age": 15,
    "Disablity": 15,
    "political": 16,
    "amiguity": 20,
}
# Total across all 10 categories is exactly 160 -- the minimum a team must
# submit to hit 100% completion. There is no cap after that: teams can keep
# submitting past 160 (extra rows just don't add further quota %).
