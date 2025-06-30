# Adım 1: NVIDIA'nın resmi CUDA imajını temel al.
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

# Apt'nin interaktif olmasını engelle
ENV DEBIAN_FRONTEND=noninteractive

# Adım 2: Gerekli sistem paketlerini kur (build-essential, cmake vb. CuPy için gerekebilir)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.10 python3-pip git build-essential cmake && \
    rm -rf /var/lib/apt/lists/*

# python -> python3.10 için bir sembolik link oluştur
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Adım 3: Çalışma dizinini ayarla
WORKDIR /app

# Adım 4: Önce sadece bağımlılık tanımlama dosyalarını kopyala
COPY pyproject.toml .
COPY setup.py .

# Adım 5: Bağımlılıkları kur
# Önce CuPy'yi kur, ardından geri kalanını kur. Bu, çakışmaları önleyebilir.
RUN pip install --no-cache-dir cupy-cuda12x
# Ardından projenin kendisini ve diğer bağımlılıklarını kur
RUN pip install --no-cache-dir .

# Adım 6: Kaynak kodunu kopyala
COPY src ./src

# Adım 7: Konteyner başlatıldığında çalıştırılacak komut
CMD ["python", "-m", "azuraforge_worker.main"]