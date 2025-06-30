# Base image olarak Python 3.10'un slim versiyonunu kullan
FROM python:3.10-slim-bullseye

# Gerekli sistem paketlerini kur (Git, pip'in Git repolarından kurulum yapması için gerekli)
RUN apt-get update && \
    apt-get install -y git --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# Önce sadece bağımlılık dosyalarını kopyala (Docker katman cache'ini optimize etmek için)
COPY pyproject.toml .
COPY setup.py .
# Kaynak kodunu kopyala
COPY src ./src

# API'nin tüm bağımlılıklarını kur
RUN pip install --no-cache-dir .

# === DEĞİŞİKLİK BURADA ===
CMD ["python", "-m", "azuraforge_api.main"]
# === DEĞİŞİKLİK SONU ===