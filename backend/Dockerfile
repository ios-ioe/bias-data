# Railway deployment — ML-free backend (~300MB RAM)
# Uses RapidFuzz for dedup and regex for PII — no sentence-transformers.

FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Railway provides $PORT env var
EXPOSE 8000

# Run with uvicorn, reading PORT from environment (Railway sets this)
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
