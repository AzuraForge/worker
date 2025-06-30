# worker/src/azuraforge_worker/main.py

import subprocess
import sys
import platform
import logging
import multiprocessing

def determine_pool_and_concurrency():
    """İşletim sistemine göre uygun pool ve concurrency değerini belirler."""
    current_platform = platform.system()

    if current_platform == "Windows":
        pool_type = "solo"
        concurrency = 1
    else:
        pool_type = "prefork"
        concurrency = multiprocessing.cpu_count()  # Docker içinde de doğru sayıyı verir

    return pool_type, concurrency


def run_celery_worker():
    """'start-worker' komutu için giriş noktası."""

    # Genel loglama yapılandırması
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
        stream=sys.stdout
    )

    logging.info("👷‍♂️ Starting AzuraForge Worker...")

    # Ortama göre pool ve concurrency belirle
    pool_type, concurrency = determine_pool_and_concurrency()

    logging.info(f"Platform: {platform.system()} - Using pool: {pool_type}, concurrency: {concurrency}")

    # Celery komutu
    command = [
        sys.executable, "-m", "celery",
        "-A", "azuraforge_worker.celery_app:celery_app",
        "worker",
        f"--pool={pool_type}",
        "--loglevel=INFO",
        f"--concurrency={concurrency}"
    ]

    # Komutu çalıştır
    subprocess.run(command)


if __name__ == "__main__":
    run_celery_worker()
