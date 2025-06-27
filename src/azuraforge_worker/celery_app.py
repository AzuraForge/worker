# ========== YENİ DOSYA: src/azuraforge_worker/celery_app.py ==========
from celery import Celery
import os

# REDIS_URL ortam değişkenini kullan, yoksa localhost'a bağlan
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery uygulamasını oluştur
# 'tasks' dizinindeki görevleri otomatik olarak bulacak
celery_app = Celery(
    "azuraforge_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["azuraforge_worker.tasks.training_tasks"]
)

# Opsiyonel Celery ayarları
celery_app.conf.update(
    task_track_started=True,
)