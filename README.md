# Nepali Bias Data Collection Tool

Production-quality internal platform for a one-day data collection competition. Teams log in with an access code, submit Nepali sentences labeled across 10 bias categories, and track their own quota progress in real time. Organizers get an admin-only leaderboard and review panel, QA batch processing, and JSON export.

```
React (Vercel)  ──signed session token──▶  HF Space (FastAPI, holds service key)  ──▶  Supabase (Postgres)
```

| Layer | Role |
|-------|------|
| **Frontend** | Login, submit, dashboard, admin — talks only to the backend, never to Supabase directly |
| **HF Space backend** | Auth (access code / admin password), all submission reads & writes, duplicate detection, PII scanning, organizer QA batch, leaderboard |
| **Supabase** | PostgreSQL database — RLS has no anon policies; only the backend's service role key can read or write |

The **service role key** and **session-signing secret** live only in the Hugging Face Space. Neither ever ships to the browser. Team and admin sessions are signed, short-lived tokens minted only by `/login` and `/admin/login` — the frontend never sends a `team_id` that the backend trusts blindly, and a team can only ever see or write its own rows. The public leaderboard has been removed; only an authenticated admin session can see team rankings (see `/admin/leaderboard`).

---

## Folder structure

```
nepali-bias-data-tool/
├── supabase/
│   ├── schema.sql          # Full database schema — run in Supabase SQL editor
│   └── seed.sql            # Sample teams and access codes
├── backend/
│   ├── app.py              # FastAPI entry point
│   ├── config.py           # Environment configuration
│   ├── database.py         # Supabase client + query helpers
│   ├── routers/
│   │   ├── health.py       # Health endpoint
│   │   ├── auth.py         # /login, /admin/login — the only places that mint tokens
│   │   ├── submission.py   # /check-submission, /submit, /my-submissions, /my-count
│   │   └── admin.py        # /admin/* — leaderboard, full table, QA batch, export
│   ├── models/
│   │   └── schemas.py      # Pydantic request/response models
│   ├── services/           # duplicate, PII, QA batch
│   └── utils/
│       ├── auth.py         # signed session token issuing/verification
│       └── exceptions.py   # Application exceptions
│   ├── Dockerfile          # HF Space deployment
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── components/     # Nav, ProgressBar, Toast, Dialog, Skeleton, etc.
    │   ├── pages/          # Login, Submit, Dashboard, Admin (leaderboard is a tab inside Admin)
    │   ├── context/        # Team session + Toast notifications
    │   ├── config/         # Quotas and category definitions
    │   └── lib/            # api.js — the single client for all backend calls
    ├── vercel.json         # SPA routing for Vercel
    └── package.json
```

---

## Environment variables

### Frontend (`frontend/.env` or Vercel)

| Variable | Description |
|----------|-------------|
| `VITE_HF_SPACE_URL` | Hugging Face Space URL — the frontend talks only to this backend now |

### Backend (`backend/.env` or HF Space secrets)

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key — **keep secret** |
| `MODEL_NAME` | Sentence-transformers model (default: `paraphrase-multilingual-MiniLM-L12-v2`) |
| `SIMILARITY_THRESHOLD` | Cosine similarity threshold for duplicate warnings (default: `0.90`) |
| `SESSION_SECRET` | Random secret used to sign team/admin session tokens — **required**, set to a long random string |
| `ADMIN_PASSWORD` | Organizer password, checked server-side only (replaces the old `VITE_ADMIN_PASSWORD`, which shipped in the browser bundle) |
| `SESSION_TTL_SECONDS` | How long a login stays valid (default: `72000` = 20h, covers a one-day event) |

Optional tuning: `FUZZ_PREFILTER_THRESHOLD`, `FUZZ_TOP_K`, `BATCH_SIMILARITY_THRESHOLD`.

---

## Hosting — how to deploy, and the best way to do it for a 100+ participant event

This app is designed to run entirely on free tiers (Vercel + Hugging Face Spaces + Supabase). That's genuinely enough for a one-day, 100+ participant event — but "enough" depends on deploying it the right way and doing a few things before the event, not just pushing code and hoping.

### Two deployment shapes

**A. Single-Space (simple).** Frontend on Vercel, one backend Docker Space that also loads the embedding model in-process. Fewer moving parts, fine for smaller events or quick setup. Leave `EMBEDDER_URL` unset.

**B. Split-embedder (recommended for 100+ concurrent participants).** Frontend on Vercel, a lightweight auth/submit backend Space, and a *second*, separate Docker Space (`embedder/`) that does nothing but turn text into embeddings. The backend calls it over HTTP with a short timeout and a circuit breaker, and automatically falls back to fuzzy-string matching if it's ever slow or unreachable — so the embedder Space being down can never block a submission.

Why (B) is worth the extra setup step for a real event:
- **Isolation.** ML inference (CPU-heavy, bursty) can't compete with or block auth/login/submit traffic — they're different processes on different Spaces.
- **More total headroom.** Two free CPU-Basic Spaces = 4 vCPUs total instead of 2 shared between everything.
- **Independent recovery.** You can restart the embedder mid-event without taking submissions down.
- **Least privilege.** The embedder holds zero Supabase secrets and touches no participant data — it only ever sees the raw sentence text being checked.

### 1. Supabase (~5 min)

Same as before — see the Setup section below. **Before the event:** open the project and run a query at least once every few days leading up to it (free-tier projects auto-pause after ~1 week of inactivity — a paused project on event morning is a bad surprise). Don't upgrade off free tier for this app's data volume; the free tier's real limits (rows, bandwidth, compute) are well beyond what a one-day, few-thousand-row event produces. The only thing to actually manage is keeping it awake.

### 2. Backend Space(s) on Hugging Face

**Single-Space:** push `backend/` as a Docker Space as before. Leave `EMBEDDER_URL` unset.

**Split-embedder (recommended):**
1. Create Docker Space #1 from `backend/` — same secrets as before (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SESSION_SECRET`, `ADMIN_PASSWORD`), plus:
   - `EMBEDDER_URL` — the embedder Space's URL (step 2 below)
   - `EMBEDDER_API_KEY` — optional shared secret, must match the embedder Space's own `EMBEDDER_API_KEY`
2. Create Docker Space #2 from `embedder/`. Its only required secret is `EMBEDDER_API_KEY` (optional but recommended — without it, anyone who finds the URL can call it, since it holds no other secrets to protect but can still burn your compute quota). Confirm `GET /health` returns `model_loaded: true` once it builds.
3. Back on Space #1, confirm `GET /health` shows `"embedding_mode": "remote"` and `"embedder_reachable": true`.

Both Spaces run on the free **CPU Basic** tier (2 vCPU / 16GB RAM, no autoscaling/replicas). That's sufficient for this app's traffic pattern (100 participants making occasional requests over several hours, not a sustained firehose) — the fixes in this patch (in-process duplicate-check cache instead of full-table re-embeds, semaphore-bounded encode concurrency, 2 Uvicorn workers) are what make "sufficient" actually true under a simultaneous burst, rather than the free tier alone.

**Before the event:** set up a free external cron/uptime pinger (e.g. cron-job.org, UptimeRobot, or a GitHub Actions scheduled workflow) hitting `GET /health` on both Spaces every 20–30 minutes starting a few hours before the event. Free Spaces sleep after inactivity, and a cold start (model reload, container boot) taking 30–60+ seconds right as your first participants arrive is a far more likely failure mode than the traffic itself.

### 3. Frontend on Vercel

Unchanged from before — set `VITE_HF_SPACE_URL` to the *main backend* Space (not the embedder — the frontend never talks to the embedder directly). Vercel's free tier is a non-issue at this scale; it's a static SPA on a CDN.

### Pre-event checklist (do this, not optional)

1. Ping `/health` on every Space (and confirm Supabase responds) the morning of the event, not just once during setup weeks earlier. `python3 scripts/smoke_test.py --backend <url> --embedder <url> --access-code <code>` automates this in under a minute — health checks, login, and a live `/check-submission` timing check, all in one run.
2. Load-test `/check-submission` specifically — not just `/submit` — with ~100 concurrent virtual users against a staging deploy. That endpoint is the one with real compute behind it; `/submit`/`/login` are cheap by comparison and were never the actual risk.
3. If using the split-embedder setup, deliberately stop the embedder Space during a test and confirm `/check-submission` still returns (degraded, fuzzy-only) instead of erroring, and that `/submit` is completely unaffected.
4. Seed 2–3 test teams and dry-run the full flow (see "Dry run before the event" below) against the *actual* deployed Spaces, not localhost.
5. If you have any budget at all, the single highest-leverage upgrade is bumping the Spaces off free CPU-Basic for just event day — but it is not required; the free tier holds up for this app's actual load pattern once the fixes above are applied.

---

### 1. Supabase (~5 min)

1. Create a project at [supabase.com](https://supabase.com).
2. Open **SQL Editor** → paste and run **`supabase/schema.sql`**.
3. Edit team names/codes in **`supabase/seed.sql`**, then run it.
4. From **Project → Settings → API**, copy:
   - Project URL → `SUPABASE_URL` / `VITE_SUPABASE_URL`
   - `anon` public key → `VITE_SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY` (backend only)

### 2. Hugging Face Space (~10 min)

1. Create a **Docker** Space (New Space → SDK: Docker).
2. Push the contents of **`backend/`** to it.
3. In Space → **Settings → Variables and secrets**, add:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `MODEL_NAME` (optional)
   - `SIMILARITY_THRESHOLD` (optional)
4. Wait for the build (model pre-downloads at build time).
5. Confirm `GET /health` returns `secrets_configured: true`.
6. Copy the Space URL → `VITE_HF_SPACE_URL`.

### 3. Frontend (~5 min)

**Local:**
```bash
cd frontend
cp .env.example .env   # fill in all VITE_ values
npm install
npm run dev             # http://localhost:5173
```

**Vercel:**
1. Import the `frontend/` folder.
2. Set `VITE_HF_SPACE_URL`.
3. Deploy (framework preset: Vite). `vercel.json` handles client-side routing.

---

## Routes

| Route | Access | Purpose |
|-------|--------|---------|
| `/login` | Public | Access code → `POST /login` on the backend → signed team session token |
| `/submit` | Team | Sentence + 10 Yes/No labels + optional source metadata → `POST /submit` |
| `/dashboard` | Team | Own quota progress only, via `GET /my-submissions` / `GET /my-count` |
| `/admin` | Password (server-verified) | Submissions table, admin-only leaderboard tab, filters, QA batch, JSON export |

Team session token persists in `localStorage`; admin session token persists only for the browser tab (`sessionStorage`) and must be re-entered next visit. Both expire server-side after `SESSION_TTL_SECONDS`.

There is no public leaderboard route — team rankings are only visible under `/admin`, and each team's dashboard shows only that team's own data.

---

## Submission flow

1. User fills Nepali text + category labels → **Check & save**
2. Frontend calls `POST /check-submission` on the HF Space (advisory only, no auth required)
3. Warnings shown in a confirmation dialog (duplicate similarity, PII matches)
4. User confirms → frontend calls `POST /submit` with the team's session token; the backend reads `team_id` from the token (never from the request body) and inserts using the service role key
5. Success toast; form clears

**Warnings never block.** If the HF Space's check step is slow/unreachable, users can still save — `/submit` itself is a separate call. The organizer QA batch is the safety net.

---

## Quotas (hardcoded)

| Category | Target |
|----------|--------|
| gender | 15 |
| caste | 12 |
| religional | 12 |
| religion | 10 |
| appearence | 10 |
| socialstatus | 10 |
| Age | 8 |
| Disablity | 8 |
| political | 12 |
| amiguity | 15 |
| **Non-biased** (all zeros) | **20** |

Defined in `frontend/src/config/quotas.js` and `backend/config.py`.

---

## Export

In `/admin`, click **Export JSON** (calls `GET /admin/export`, admin token required). Output uses exact dataset column names:

`team_id`, `text`, `gender`, `religional`, `caste`, `religion`, `appearence`, `socialstatus`, `amiguity`, `political`, `Age`, `Disablity`, `source_platform`, `source_date`, `submitted_at`, `flag_duplicate`, `flag_pii`, `judge_reviewed`

Column names (including typos like `religional`, `appearence`, `amiguity`, `Disablity`) are intentional — they match the published dataset.

---

## Dry run before the event

1. Log in as 2–3 seeded teams in different browser tabs; submit ~10 rows each.
2. Submit the same sentence twice → confirm duplicate warning appears.
3. Include a phone number or common Nepali name → confirm PII warning appears.
4. Confirm each team's `/dashboard` only ever shows that team's own count — try editing localStorage/requests to claim a different team_id and confirm the backend still returns only the real one.
5. In `/admin`, log in with the organizer password, check the **Leaderboard** tab, run QA batch, and export JSON → verify field names and counts.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Blank screen on load | Check `VITE_HF_SPACE_URL` in `.env` or Vercel |
| Login fails | Re-run `seed.sql`; verify `verify_access_code` RPC exists; check backend logs for `SESSION_SECRET` missing |
| Check & save always fails | Verify `VITE_HF_SPACE_URL`; test `GET /health` on the Space |
| Submit succeeds but dashboard/count doesn't update | Session token may have expired (`SESSION_TTL_SECONDS`) — log in again |
| Admin won't unlock | Set `ADMIN_PASSWORD` in **backend** secrets (not a `VITE_` frontend var anymore) |
| Admin leaderboard/table empty | Confirm the admin token is present (log out and back in); check `/admin/submissions` directly |
| QA batch slow | Normal for large datasets; batch timeout is 120s |

---

## Screenshots

<!-- Add screenshots after deploy -->
- `docs/screenshots/login.png` — Team login
- `docs/screenshots/submit.png` — Submission form with warnings
- `docs/screenshots/dashboard.png` — Quota progress (own team only)
- `docs/screenshots/admin.png` — Admin table + leaderboard tab + QA report

---

## License

Internal event tool. Adjust quotas, team seeds, and PII name lists as needed for your event.
