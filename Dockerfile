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
# KRİTİK: Lütfen sisteminizdeki NVIDIA CUDA sürümüne uygun CuPy paketini seçin!
# Sisteminizde yüklü olan CUDA sürümünü (örn: nvidia-smi komutu ile) kontrol edin.
# Eğer CUDA 12.x kullanıyorsanız:
RUN pip install --no-cache-dir cupy-cuda12x
# Eğer CUDA 11.x kullanıyorsanız:
# RUN pip install --no-cache-dir cupy-cuda11x
# Emin değilseniz veya test etmek için generic versiyon (bazı durumlarda uyumlu olabilir, bazen tam performans vermeyebilir):
# RUN pip install --no-cache-dir cupy

RUN pip install --no-cache-dir -e .
# === BİTTİ ===

# Adım 6: Konteyner başlatıldığında çalıştırılacak komut
CMD ["start-worker"]