# ========== GÜNCELLENECEK DOSYA: worker/Dockerfile ==========
FROM python:3.10-slim-bullseye

RUN apt-get update && apt-get install -y git --no-install-recommends && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY setup.py .
# --- KRİTİK DÜZELTME: src klasörünü pip install'dan ÖNCE kopyala ---
COPY src ./src 

# Worker'ın tüm bağımlılıklarını kur
RUN pip install --no-cache-dir .

CMD ["start-worker"]