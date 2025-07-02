# worker/Dockerfile

# NVIDIA'nın resmi PyTorch imajını temel alıyoruz.
# Bu, CUDA/cuDNN uyumluluğunu garanti eder.
FROM nvcr.io/nvidia/pytorch:23.07-py3

# APT'nin interaktif sorularını engelle
ENV DEBIAN_FRONTEND=noninteractive

# Gerekli sistem paketlerini kur (git, pip'in git repolarını klonlaması için)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# === YENİ VE DAHA SAĞLAM KURULUM STRATEJİSİ ===

# 1. Önce projenin TÜM dosyalarını kopyala.
# Bu, pyproject.toml, setup.py ve src klasörünü aynı anda içeri alır.
COPY . .

# 2. Şimdi, tüm dosyalar içerideyken, tek bir komutla her şeyi kur.
# `pip install -e .` komutu, pyproject.toml'daki `dependencies` listesini okur.
# Bu liste, Git repolarına işaret ettiği için, pip bu eklentileri klonlar
# ve kurar. Bu süreçte eklentilerin kendi entry_point'leri de
# (pipelines, configs VE schemas dahil) doğru bir şekilde kaydedilir.
# Bu, önceki `requirements.txt` yönteminden daha standart ve güvenilirdir.
RUN python3 -m pip install --no-cache-dir -e .

# Bu komut, 'docker-compose up' ile çalıştırıldığında worker'ı başlatır.
# Kurulum doğru yapıldığı için 'azuraforge_worker' modülü bulunacaktır.
CMD ["python3", "-m", "azuraforge_worker.main"]