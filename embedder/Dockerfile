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
# Single worker is enough here: each worker would load its own ~500MB model
# copy, and this Space's only job is CPU-bound encode() calls anyway, so
# extra workers mostly just duplicate memory rather than add real throughput
# on a 2 vCPU box. Bump if you upgrade this Space's hardware.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
