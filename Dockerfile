# worker/Dockerfile

# KESİN VE GARANTİ ÇÖZÜM İÇİN: NVIDIA's PyTorch/CUDA/cuDNN/Python içeren resmi imajını kullanın.
FROM nvcr.io/nvidia/pytorch:23.07-py3

# apt-get sorularını engellemek için
ENV DEBIAN_FRONTEND=noninteractive

# Sadece git ve curl gibi ek sistem paketleri
RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /var/cache/apt/archives/*

# Çalışma dizinini ayarla
WORKDIR /app

# Projenin tüm dosyalarını kopyala (root olarak kopyalıyoruz)
COPY . .

# PYTHONPATH'i ayarlayın ki Python, 'azuraforge_worker' paketini ve kopyalanan kodları bulabilsin.
# '/app/src' dizini, azuraforge_worker paketinin kök dizinidir.
ENV PYTHONPATH="/app/src:${PYTHONPATH}"

# TÜM PİP BAĞIMLILIKLARINI VE WORKER PAKETİNİN KENDİSİNİ requirements.txt'den ROOT OLARAK KUR
# Bu, tüm 'ModuleNotFoundError' ve diğer pip kurulum sorunlarını çözmelidir.
RUN python3 -m pip install --no-cache-dir -r requirements.txt


# Konteyner başlatıldığında çalıştırılacak komut
CMD python3 -m azuraforge_worker.main