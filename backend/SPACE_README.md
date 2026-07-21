---
title: Nepali Bias Data Tool Backend
emoji: 🚂
colorFrom: purple
colorTo: gray
sdk: gradio
sdk_version: 5.31.0
app_file: app.py
pinned: false
---

# Nepali Bias Data Tool — Backend (Railway)

**This file is for reference only.** The backend is now deployed on Railway, not Hugging Face Spaces.

## Railway Deployment

This backend is deployed as a Docker container on Railway's free tier (~300MB RAM).

- **Dockerfile**: See `Dockerfile` in this directory
- **Config**: See `railway.json`
- **Dependencies**: `requirements.txt` (ML-free: no sentence-transformers, no transformers)

## Environment Variables

Set these in Railway's dashboard → Variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service role key |
| `SESSION_SECRET` | Yes | HMAC signing secret |
| `ADMIN_BOOTSTRAP_SECRET` | Yes | One-time admin bootstrap |
| `CORS_ALLOWED_ORIGINS` | Yes | Frontend URL(s) |
| `EMBEDDER_URL` | No | Remote embedder URL (optional) |
| `EMBEDDER_API_KEY` | No | Shared secret for embedder |

## Previous HF Space Deployment (archived)

This Space previously used the Gradio SDK for HF deployment. That approach
required mounting a Gradio UI at `/ui` and pre-downloading ML models.

The current Railway deployment removes:
- Gradio dependency and UI mount
- sentence-transformers and transformers dependencies
- ML model pre-download

Result: ~300MB RAM usage (down from ~2GB).
