# ========== DOSYA: worker/Dockerfile ==========
FROM python:3.10-slim-bullseye

WORKDIR /app

COPY pyproject.toml .
COPY setup.py .

RUN pip install --no-cache-dir .

COPY src ./src

CMD ["start-worker"]