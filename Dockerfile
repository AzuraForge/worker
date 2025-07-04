# NVIDIA'nın resmi PyTorch imajını temel alıyoruz.
FROM nvcr.io/nvidia/pytorch:23.07-py3

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# === YENİ: Başlangıç script'lerini kopyala ve çalıştırılabilir yap ===
COPY ./scripts/wait-for-it.sh /usr/local/bin/wait-for-it.sh
COPY ./scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh /usr/local/bin/entrypoint.sh
# === BİTTİ ===

COPY . .

RUN python3 -m pip install --no-cache-dir -e .

# Konteynerin giriş noktası
ENTRYPOINT ["entrypoint.sh"]

# Varsayılan komut
CMD ["python3", "-m", "azuraforge_worker.main"]