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

# === YENİ VE DAHA SAĞLAM YAPI ===
# Önce projenin TÜM dosyalarını kopyala.
# Bu, kardeş repolardaki (dbmodels, learner vb.) değişikliklerin de
# Docker tarafından algılanmasını ve cache'in kırılmasını sağlar.
COPY . .

# Şimdi bağımlılıkları kur. Bu katman, kaynak kodundaki herhangi bir
# değişiklikte yeniden çalışacaktır.
RUN python3 -m pip install --no-cache-dir -e .
# === YAPI SONU ===

# Konteynerin giriş noktası
ENTRYPOINT ["entrypoint.sh"]

# Varsayılan komut (docker-compose'da override edilecek)
CMD ["python3", "-m", "azuraforge_worker.main"]
