# Adım 1: NVIDIA'nın resmi CUDA imajını temel al.
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

# Apt'nin interaktif olmasını engelle
ENV DEBIAN_FRONTEND=noninteractive

# Adım 2: Gerekli sistem paketlerini kur
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.10 python3-pip git build-essential cmake && \
    rm -rf /var/lib/apt/lists/*

# python -> python3.10 için bir sembolik link oluştur
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Adım 3: Çalışma dizinini ayarla
WORKDIR /app

# === BASİT VE GARANTİ YÖNTEM ===
# Adım 4: Projenin TÜM dosyalarını kopyala
COPY . .

# Adım 5: CuPy ve proje bağımlılıklarını kur
RUN pip install --no-cache-dir cupy-cuda12x
RUN pip install --no-cache-dir -e .
# === BİTTİ ===

# Adım 6: Konteyner başlatıldığında çalıştırılacak komut
CMD ["start-worker"]