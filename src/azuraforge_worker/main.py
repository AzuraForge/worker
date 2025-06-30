# worker/src/azuraforge_worker/main.py

import subprocess
import sys
import platform
import logging
import multiprocessing

def determine_pool_and_concurrency():
    """İşletim sistemine göre uygun pool ve concurrency değerini belirler."""
    current_platform = platform.system()

    # === DEĞİŞİKLİK BURADA: Orijinal mantığa geri dönüyoruz ===
    if current_platform == "Windows":
        # Windows 'prefork'u desteklemez, 'solo' veya 'gevent' kullanılmalıdır.
        # Yerel Windows geliştirmesi için 'solo' en güvenlisidir.
        pool_type = "solo"
        concurrency = 1
        logging.info("Windows platformu algılandı. 'solo' pool kullanılıyor.")
    else:
        # Linux ve macOS için 'prefork' varsayılan ve en verimli seçenektir.
        pool_type = "prefork"
        # Mevcut CPU çekirdeği sayısı kadar paralel işçi çalıştır.
        concurrency = multiprocessing.cpu_count()
        logging.info(f"Linux/macOS platformu algılandı. 'prefork' pool ve {concurrency} concurrency kullanılıyor.")
    
    return pool_type, concurrency
    # === DEĞİŞİKLİK SONU ===


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