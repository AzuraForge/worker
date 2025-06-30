# worker/src/azuraforge_worker/main.py

import logging
import sys
import platform
import multiprocessing
import os

from .celery_app import celery_app

def get_concurrency():
    """Cihaz türüne göre uygun concurrency değerini belirler."""
    device = os.environ.get("AZURAFORGE_DEVICE", "cpu").lower()
    if device == "gpu":
        # Tek bir GPU varken, çok fazla paralel süreç başlatmak verimsizdir.
        concurrency = 4
        logging.info(f"GPU modu aktif. Concurrency = {concurrency} (sabit).")
        return concurrency
    else:
        concurrency = multiprocessing.cpu_count() / 4
        logging.info(f"CPU modu aktif. Concurrency = {concurrency} (CPU çekirdek sayısı).")
        return concurrency

def run_azuraforge_worker():
    """
    Bu fonksiyon, worker'ı programatik olarak, subprocess kullanmadan başlatır.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    logging.info("👷‍♂️ Starting AzuraForge Worker via Celery's programmatic API...")
    
    # Celery worker'ını başlatmak için argüman listesi oluştur
    worker_argv = [
        'worker',
        '--loglevel=info',
        # 'prefork' Linux'ta varsayılan olduğu için belirtmeye gerek yok.
        # 'solo' da hata ayıklama modundan kaldırıldı.
        f'--concurrency={get_concurrency()}',
    ]
    
    # Celery uygulamasının worker_main metodunu bu argümanlarla çağır
    celery_app.worker_main(argv=worker_argv)

if __name__ == "__main__":
    run_azuraforge_worker()