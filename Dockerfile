# worker/Dockerfile

# NVIDIA'nın resmi PyTorch imajını temel alıyoruz.
FROM nvcr.io/nvidia/pytorch:23.07-py3

# APT'nin interaktif sorularını engelle
ENV DEBIAN_FRONTEND=noninteractive

# Gerekli sistem paketlerini kur (örn: git)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# ÖNCE sadece bağımlılık ve proje tanım dosyalarını kopyala.
# Docker katman önbelleklemesini (layer caching) optimize eder.
COPY requirements.txt pyproject.toml setup.py ./

# === 1. ADIM: DIŞ BAĞIMLILIKLARI KUR ===
# Önce requirements.txt içindeki tüm dış kütüphaneleri ve eklentileri kur.
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# === 2. ADIM: PROJENİN KENDİSİNİ KUR ===
# Şimdi projenin kaynak kodunu kopyala.
COPY src ./src

# Projenin kendisini "düzenlenebilir" modda kur.
# Bu komut, 'src/azuraforge_worker' paketini Python'un 'site-packages'
# dizinine bir link olarak ekler. Bu, 'ModuleNotFoundError' hatasını çözer.
RUN python3 -m pip install --no-cache-dir -e .

# Bu komut, 'docker-compose up' ile çalıştırıldığında worker'ı başlatır.
# Artık 'azuraforge_worker' modülü Python tarafından bulunabilir.
CMD ["python3", "-m", "azuraforge_worker.main"]