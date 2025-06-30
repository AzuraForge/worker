# Base image olarak Python 3.10'un slim versiyonunu kullan
FROM python:3.10-slim-bullseye

# Gerekli sistem paketlerini kur
RUN apt-get update && \
    apt-get install -y git --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# === BASİT VE GARANTİ YÖNTEM ===
# Önce projenin TÜM dosyalarını kopyala
COPY . .

# Adım 5: CuPy ve proje bağımlılıklarını kur
# RUN pip install --no-cache-dir cupy-cuda12x
RUN pip install --no-cache-dir -e .
# === BİTTİ ===

# Adım 6: Konteyner başlatıldığında çalıştırılacak komut
CMD ["start-worker"]