# worker/src/azuraforge_worker/main.py

import subprocess
import sys
import logging # YENİ

def run_celery_worker():
    """'start-worker' komutu için giriş noktası."""
    
    # YENİ: Platform genelinde loglama yapılandırmasını burada yap
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
        stream=sys.stdout  # Logların konsola basıldığından emin ol
    )
    
    logging.info("👷‍♂️ Starting AzuraForge Worker...")
    command = [
        sys.executable, "-m", "celery",
        "-A", "azuraforge_worker.celery_app:celery_app",
        "worker",
        "--pool=solo",
        "--loglevel=INFO"
    ]
    # Celery'nin kendi log formatını kullanmasını engellemek için --logfile= olmadan çalıştırıyoruz
    # ve kendi yapılandırmamıza güveniyoruz.
    subprocess.run(command)