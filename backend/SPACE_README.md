---
title: Nepali Bias Data Tool Backend
emoji: 🐳
colorFrom: purple
colorTo: gray
sdk: gradio
sdk_version: 5.31.0
app_file: app.py
pinned: false
---

# Nepali Bias Data Tool — Backend

FastAPI service mounted under a minimal Gradio UI (see `app.py`) so this
Space can run on HF's free CPU-Basic tier — the Docker SDK is currently a
paid feature; the Gradio SDK is not.

All real routes are plain FastAPI, unchanged: `/login`, `/submit`,
`/my-submissions`, `/my-count`, `/leaderboard`, `/admin/*`, `/health`,
`/docs`. The Gradio widget itself only lives at `/ui` and is not part of
the API surface the frontend calls.

Push this file as `README.md` in the HF Space repo (it's separate from the
GitHub repo's `backend/README.md`, which stays as local-dev documentation).

Set the same secrets as before in Space → Settings → Variables and secrets:
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SESSION_SECRET`,
`ADMIN_PASSWORD`, and (if using the split-embedder setup) `EMBEDDER_URL` /
`EMBEDDER_API_KEY`.
