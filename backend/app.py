"""
Nepali Bias Data Collection — backend (FastAPI, Railway deployment).

ML-free version optimized for Railway's free tier (~300MB RAM). Uses RapidFuzz
for duplicate detection and regex for PII — no sentence-transformers, no
transformers, no Gradio.

All reads and writes to `submissions`/`teams` go through this service using the
Supabase service role key — the frontend no longer talks to Supabase directly
with the anon key for CRUD. Routes:
  POST /login                 — access code -> signed team session token
  POST /admin/login           — organizer password -> signed admin session token
  POST /check-submission      — live duplicate + PII soft-check (no auth; advisory only)
  POST /submit                — insert a submission for the logged-in team
  GET  /my-submissions        — the logged-in team's own rows only
  GET  /my-count               — the logged-in team's own submission count
  GET  /leaderboard            — any logged-in team: rank/name/% only, no
                                  team_id or raw counts of other teams
  GET  /admin/leaderboard      — admin-only: full ranked team standings
  GET  /admin/submissions      — admin-only: full table
  POST /admin/qa-batch         — admin-only: organizer batch QA after close
  POST /admin/mark-reviewed    — admin-only
  GET  /admin/export           — admin-only: JSON export

The Supabase service role key and SESSION_SECRET live only here, never in the
browser. Admin credentials now live in Supabase (hashed), not an env var --
see routers/auth.py for /admin/login and the one-time /admin/bootstrap.

Optional: Set EMBEDDER_URL to enable remote ML inference (embeddings + NER).
Without it, the backend uses RapidFuzz-only dedup and regex-only PII.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import CORS_ALLOWED_ORIGINS, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from routers.admin import router as admin_router
from routers.auth import router as auth_router
from routers.health import router as health_router
from routers.judge import router as judge_router
from routers.leaderboard import router as leaderboard_router
from routers.submission import router as submission_router
from services.duplicate_service import init_cache
from utils.exceptions import AppError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Initialize the corpus cache (loads submission texts from Supabase).
    # No ML models to load — duplicate detection uses RapidFuzz only.
    try:
        init_cache()
    except Exception as exc:
        logger.error("Failed to initialize corpus cache at startup: %s", exc)
    yield


app = FastAPI(
    title="Nepali Bias Data QA Backend",
    description="Duplicate detection and PII scanning for the bias data collection tool.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _RateLimiter:
    """Minimal in-memory sliding-window limiter, per client IP + path.

    Not a substitute for a real edge rate limiter (it's per-process, so it
    resets on restart and doesn't share state across replicas), but for a
    single-Space one-day event it's enough to stop:
      - /login being brute-forced against the access-code space, and
      - a runaway client/bug hammering /check-submission (the CPU-heavy
        endpoint) and starving other participants.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


_rate_limiter = _RateLimiter()

# path -> (max requests, window seconds) per rate-limit key
_RATE_LIMITS = {
    # /login is unauthenticated, so IP is the only key we have. Loosened
    # vs. a typical login endpoint because a whole venue/conference room of
    # participants is often behind a handful of shared NAT/WiFi IPs -- this
    # still meaningfully slows down brute-forcing a single access code
    # (100,000 possible 5-digit suffixes) without throttling a real crowd.
    "/login": (40, 60.0),
    # Admin/judge logins are a much smaller pool of legitimate users than
    # the whole participant crowd, so these can (and should) be much
    # stricter -- there's no shared-venue-WiFi excuse for hundreds of
    # attempts/minute against an admin password or judge code.
    "/admin/login": (10, 60.0),
    "/admin/bootstrap": (5, 300.0),
    "/judge/login": (10, 60.0),
    # /check-submission IS authenticated (team Bearer token) even though it
    # doesn't require it structurally -- key by team when present so one
    # team's rapid typing/editing can't eat into another team's quota on
    # shared venue WiFi, and fall back to IP only for the rare caller with
    # no token at all.
    "/check-submission": (30, 60.0),
}


def _rate_limit_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return f"token:{auth.split(' ', 1)[1].strip()}"
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    limit_config = _RATE_LIMITS.get(request.url.path)
    if limit_config:
        limit, window = limit_config
        key = f"{request.url.path}:{_rate_limit_key(request)}"
        if not _rate_limiter.allow(key, limit, window):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — please slow down and try again shortly."},
            )
    return await call_next(request)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(submission_router)
app.include_router(leaderboard_router)
app.include_router(judge_router)
app.include_router(admin_router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
