# Backend (Railway)

FastAPI service for duplicate detection, PII scanning, and organizer QA batch.

**ML-free version** optimized for Railway's free tier (~300MB RAM). Uses RapidFuzz for duplicate detection and regex for PII — no sentence-transformers, no transformers, no Gradio.

See the root [README](../README.md) for full project setup.

## Architecture

```
┌─────────────────┐         ┌──────────────────────┐
│  React Frontend  │────────▶│  Supabase (Postgres)  │
│  (Vercel)        │  direct │  - submissions table   │
│                  │  reads/ │  - teams table         │
│                  │  writes │  - RLS policies         │
└────────┬─────────┘         └──────────▲───────────┘
         │                              │
         ▼                              │
┌────────────────────────────────────┐   │
│  Railway Backend (FastAPI)          │───┘
│  - /check-submission (RapidFuzz)   │
│  - /submit, /admin, /judge         │
│  - holds Supabase service key      │
│  - regex + name list for PII       │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│  Embedder (optional, separate)     │
│  - /embed (sentence-transformers)  │
│  - /ner (Nepali NER)               │
│  - Deploy later if needed          │
└────────────────────────────────────┘
```

## Local Development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in Supabase credentials
uvicorn app:app --reload --port 8000
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service role key (bypasses RLS) |
| `SESSION_SECRET` | Yes | HMAC signing secret |
| `ADMIN_BOOTSTRAP_SECRET` | Yes | One-time admin bootstrap |
| `CORS_ALLOWED_ORIGINS` | Yes | Frontend URL(s) |
| `EMBEDDER_URL` | No | Remote embedder URL (optional) |
| `EMBEDDER_API_KEY` | No | Shared secret for embedder |
| `RESEND_API_KEY` | No | Email service |
| `RESEND_FROM` | No | Sender email |

## Railway Deployment

### Quick Start

1. Push this `backend/` directory to GitHub
2. Go to [Railway](https://railway.app) → New Project → Deploy from GitHub
3. Select repo, set root directory to `backend/`
4. Add environment variables (see above)
5. Deploy

### Resource Usage

| Resource | Estimated | Free Tier Limit |
|----------|-----------|-----------------|
| RAM | ~300MB | 1GB |
| CPU | Low (RapidFuzz is C-backed) | 2 vCPU |
| Disk | ~100MB | 1GB |
| Cost | ~$0.30/day | $5 credit (30 days) |

### Health Check

- Path: `/health`
- Timeout: 30 seconds
- Expected: `{"status": "ok", ...}`

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Service health + config status |
| POST | `/login` | None | Team login (access code) |
| POST | `/admin/login` | None | Admin login (email + password) |
| POST | `/admin/bootstrap` | None | Create first admin |
| POST | `/check-submission` | Optional | Live duplicate + PII check |
| POST | `/submit` | Team token | Insert submission |
| GET | `/my-submissions` | Team token | Team's own rows |
| GET | `/my-count` | Team token | Team's submission count |
| GET | `/leaderboard` | Admin/Judge | Public leaderboard |
| GET | `/admin/submissions` | Admin | Full submissions table |
| GET | `/admin/leaderboard` | Admin | Full ranked standings |
| POST | `/admin/qa-batch` | Admin | Run QA batch (dedup + PII) |
| POST | `/admin/mark-reviewed` | Admin | Mark submission reviewed |
| GET | `/admin/export` | Admin | JSON export |
| GET | `/admin/quota-report` | Admin | Per-team quota progress |
| GET | `/admin/teams` | Admin | List teams |
| POST | `/admin/teams` | Admin | Create team |
| GET | `/admin/judges` | Admin | List judges |
| POST | `/admin/judges` | Admin | Create judge |
| GET | `/admin/admins` | Admin | List admin accounts |
| POST | `/admin/admins` | Admin | Create admin |
| POST | `/admin/judge-sample` | Admin | Sample for judging |
| GET | `/admin/judge-report` | Admin | Judge vs participant labels |
| POST | `/judge/login` | None | Judge login |
| GET | `/judge/queue` | Judge token | Blind judging queue |
| POST | `/judge/label` | Judge token | Submit judge label |

## Performance

### Live `/check-submission`

- Corpus size: 2.5k texts
- RapidFuzz top-K extraction: ~50-100ms
- Total latency: ~100-200ms (acceptable)

### QA Batch (one-time, post-event)

- Pairwise RapidFuzz: 2.5k × 2.5k = 6.25M comparisons
- Time: ~1-10 minutes (depending on text length)
- PII scan: ~5-10 seconds (regex is fast)
- Total: ~2-10 minutes

## Structure

```
backend/
├── app.py                  # FastAPI entry, middleware, routers
├── config.py               # Environment + quotas
├── database.py             # Supabase client + data access
├── Dockerfile              # Railway deployment
├── railway.json            # Railway config
├── requirements.txt        # Dependencies (ML-free)
├── routers/
│   ├── auth.py             # Team/admin/judge login
│   ├── admin.py            # Organizer endpoints
│   ├── submission.py       # Check + submit
│   ├── leaderboard.py      # Leaderboard
│   ├── judge.py            # Blind judging
│   └── health.py           # Health check
├── models/
│   └── schemas.py          # Pydantic models
├── services/
│   ├── duplicate_service.py    # RapidFuzz-only dedup
│   ├── pii_service.py          # Regex + name list PII
│   ├── embedder_client.py      # Remote embedder (optional)
│   ├── qa_batch.py             # QA batch orchestration
│   ├── leaderboard_service.py  # Ranking logic
│   ├── admin_service.py        # Password hashing
│   ├── email_service.py        # Resend emails
│   └── judge_service.py        # Judge report
└── utils/
    ├── auth.py             # HMAC session tokens
    └── exceptions.py       # Application exceptions
```

## Degraded Mode

Without `EMBEDDER_URL` set (current default):

| Feature | Behavior |
|---------|----------|
| Live dedup | RapidFuzz string matching |
| Live PII | Regex + name list |
| QA batch dedup | RapidFuzz pairwise (O(n^2)) |
| QA batch PII | Regex + name list |

## Optional: Embedder Service

The `embedder/` directory contains a separate ML inference service. Deploy it later if:
- Semantic similarity dedup is needed
- NER-based PII detection is needed

To enable: set `EMBEDDER_URL` on the backend to point to the deployed embedder.
