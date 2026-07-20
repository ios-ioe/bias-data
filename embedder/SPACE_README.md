---
title: Nepali Bias Data Tool Embedder
emoji: 🧠
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: 5.31.0
app_file: app.py
pinned: false
---

# Nepali Bias Data Tool — Embedder

Internal-only microservice (`/embed`, `/ner`, `/health`) called by the main
backend Space. Runs on the Gradio SDK (free CPU-Basic) instead of Docker —
see `../backend/SPACE_README.md` for the full rationale.

Push this file as `README.md` in this component's HF Space repo.

Only required secret: `EMBEDDER_API_KEY` (optional but recommended — this
Space holds no other secrets, but an unauthenticated open endpoint can still
burn your compute quota).
