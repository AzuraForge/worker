# worker/Dockerfile

# NVIDIA'nın resmi PyTorch imajını temel alıyoruz.
# Bu, CUDA/cuDNN uyumluluğunu garanti eder.
FROM nvcr.io/nvidia/pytorch:23.07-py3

# APT'nin interaktif sorularını engelle
ENV DEBIAN_FRONTEND=noninteractive

# Gerekli sistem paketlerini kur (örn: git, pip'in git repolarını klonlaması için)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# ÖNCE sadece bağımlılık dosyasını kopyala.
# Bu, Docker katman önbelleklemesini (layer caching) optimize eder.
# requirements.txt değişmediği sürece bu katman yeniden çalıştırılmaz.
COPY requirements.txt ./

# ŞİMDİ tüm bağımlılıkları requirements.txt'den kur.
# Bu komut, Celery, SQLAlchemy VE TÜM EKLENTİLERİ (stock-predictor, weather-forecaster)
# Docker imajının içine kuracaktır.
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Bağımlılıklar kurulduktan sonra, geri kalan tüm proje kodunu kopyala.
# .dockerignore dosyası, gereksiz dosyaların kopyalanmasını engeller.
COPY . .

# Bu komut, 'docker-compose up' ile çalıştırıldığında worker'ı başlatır.
CMD ["python3", "-m", "azuraforge_worker.main"]