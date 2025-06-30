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

# === DEĞİŞİKLİK BURADA: Sıralamayı garanti altına alıyoruz ===

# Adım 4: Önce SADECE bağımlılık dosyalarını kopyala
COPY pyproject.toml .
COPY setup.py .

# Adım 5: SADECE dış bağımlılıkları kur
# Bu, 'pip install .' komutunun gerektirdiği tüm paketleri önceden kurar.
RUN pip install --no-cache-dir -r <(grep -E '^[a-zA-Z]' pyproject.toml | sed -e 's/\[.*\]//' -e "s/ //g" -e "s/==.*//")

# Adım 6: CuPy'yi ayrıca kur
RUN pip install --no-cache-dir cupy-cuda12x

# Adım 7: Şimdi kaynak kodunu kopyala
COPY src ./src

# Adım 8: Son olarak projenin kendisini "düzenlenebilir" modda kur
# Bu, `start-worker` gibi scriptlerin PATH'e eklenmesini sağlar.
RUN pip install --no-cache-dir -e .

# === DEĞİŞİKLİK SONU ===

# Adım 9: Konteyner başlatıldığında çalıştırılacak komut
CMD ["start-worker"]