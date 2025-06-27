# ========== YENİ DOSYA: src/azuraforge_worker/main.py ==========
import subprocess
import sys

def run_celery_worker():
    """'start-worker' komutu için giriş noktası."""
    print("👷‍♂️ Starting AzuraForge Worker...")
    command = [
        sys.executable, "-m", "celery",
        "-A", "azuraforge_worker.celery_app", "worker",
        "--pool=solo", # Windows uyumluluğu
        "--loglevel=info"
    ]
    subprocess.run(command)