# worker/src/azuraforge_worker/main.py

import subprocess
import sys
import platform
import logging
import multiprocessing
import os # os'i import et

def determine_pool_and_concurrency():
    """İşletim sistemine ve cihaz türüne göre uygun pool ve concurrency değerini belirler."""
    current_platform = platform.system()
    device = os.environ.get("AZURAFORGE_DEVICE", "cpu").lower()

    if current_platform == "Windows":
        pool_type = "solo"
        concurrency = 1
        logging.info("Windows platformu algılandı. 'solo' pool kullanılıyor.")
    elif device == "gpu":
        # === DEĞİŞİKLİK BURADA: GPU için özel concurrency ayarı ===
        pool_type = "prefork"
        # Tek bir GPU varken, çok fazla paralel süreç başlatmak verimsizdir ve OOM'a yol açabilir.
        # 2 veya 4 gibi küçük bir değerle başlayalım.
        concurrency = 4 
        logging.info(f"GPU modu aktif. 'prefork' pool ve {concurrency} (sabit) concurrency kullanılıyor.")
        # === DEĞİŞİKLİK SONU ===
    else: # CPU-bound Linux
        pool_type = "prefork"
        concurrency = multiprocessing.cpu_count()
        logging.info(f"CPU-bound Linux/macOS platformu algılandı. 'prefork' pool ve {concurrency} concurrency kullanılıyor.")
    
    return pool_type, concurrency


def run_celery_worker():
    """'start-worker' komutu için giriş noktası."""

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
        stream=sys.stdout
    )

    logging.info("👷‍♂️ Starting AzuraForge Worker...")

    pool_type, concurrency = determine_pool_and_concurrency()

    logging.info(f"Platform: {platform.system()} - Using pool: {pool_type}, concurrency: {concurrency}")

    command = [
        # python -m celery ... yerine doğrudan celery komutunu kullanmak daha standarttır
        # ve PATH sorunları artık Dockerfile'da çözüldü.
        "celery",
        "-A", "azuraforge_worker.celery_app:celery_app",
        "worker",
        f"--pool={pool_type}",
        "--loglevel=INFO",
        f"--concurrency={concurrency}"
    ]

    subprocess.run(command)


if __name__ == "__main__":
    run_celery_worker()