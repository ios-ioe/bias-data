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
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "2"]
