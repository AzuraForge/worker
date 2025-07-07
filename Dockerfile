# worker/Dockerfile
FROM nvcr.io/nvidia/pytorch:23.07-py3

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Başlangıç script'lerini kopyala ve çalıştırılabilir yap
COPY ./scripts/wait-for-it.sh /usr/local/bin/wait-for-it.sh
COPY ./scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh /usr/local/bin/entrypoint.sh

# === YENİ VE DOĞRU YAPI ===
# 1. Önce kaynak kodunu ve bağımlılık dosyalarını kopyala
COPY src ./src
COPY pyproject.toml setup.py ./

# 2. Şimdi bağımlılıkları kur. pip artık 'src' klasörünü bulabilir.
RUN python3 -m pip install --no-cache-dir -e .

# 3. Geliştirme sırasında anında yansıma için geri kalan her şeyi kopyala
COPY . .
# === YAPI SONU ===

# Konteynerin giriş noktası
ENTRYPOINT ["entrypoint.sh"]

# Varsayılan komut (docker-compose'da override edilecek)
CMD ["python3", "-m", "azuraforge_worker.main"]