# NOTE: unused as of the switch to sdk: gradio (HF Docker SDK is now a paid
# feature; Gradio SDK is still free CPU-Basic). Kept only for local
# reference / in case you move back to Docker later. See app.py's Gradio
# mount + SPACE_README.md for the current deployment method.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache \
    SENTENCE_TRANSFORMERS_HOME=/home/user/.cache \
    TRANSFORMERS_CACHE=/home/user/.cache

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

ARG MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('${MODEL_NAME}')"

EXPOSE 7860

# 2 workers to use both vCPUs on HF's free "CPU Basic" tier (2 vCPU / 16GB).
# Each worker loads its own copy of the embedding model (~500MB) and keeps
# its own in-process duplicate-check cache (see services/duplicate_service.py)
# — well within the 16GB RAM budget, and there's no shared-state requirement
# between workers since session tokens are stateless (HMAC-signed) and the
# duplicate cache self-heals via ensure_fresh()'s row-count poll.
# If you upgrade off the free tier to more vCPUs, raise this accordingly.
# --proxy-headers + --forwarded-allow-ips='*' makes uvicorn read the real
# client IP from X-Forwarded-For, set by whatever reverse proxy sits in
# front of this container (HF Spaces / Render / Railway / etc. all do this).
# Without this, request.client.host in app.py's rate limiter would see the
# proxy's IP for every request, collapsing every participant into a single
# shared rate-limit bucket -- exactly the scenario this event will hit at
# the start, when everyone logs in around the same time. '*' trusts
# whichever single hop connects directly to this container, which is
# appropriate here since nothing external reaches this container directly
# (the platform's own front door already terminates and forwards traffic) --
# it is NOT appropriate if this were reachable directly from the internet
# without a managed platform's proxy in front of it.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
