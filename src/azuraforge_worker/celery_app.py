# worker/src/azuraforge_worker/celery_app.py

import os
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "azuraforge_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["azuraforge_worker.tasks.training_tasks"]
)

# === YENİ BÖLÜM: Veritabanı Bağlantı Yönetimi ===
# Bu değişken, her bir worker sürecinin kendi motorunu tutmasını sağlar.
engine = None

@worker_process_init.connect
def init_worker_db_connection(**kwargs):
    """Her bir Celery alt süreci başladığında çağrılır."""
    global engine
    print("Initializing DB connection for worker process...")
    # database.py'den create_engine'i burada import ediyoruz
    from .database import create_engine as db_create_engine
    engine = db_create_engine(os.getenv("DATABASE_URL"))

@worker_process_shutdown.connect
def shutdown_worker_db_connection(**kwargs):
    """Her bir Celery alt süreci kapandığında çağrılır."""
    global engine
    if engine:
        print("Disposing DB connection for worker process...")
        engine.dispose()
# === DEĞİŞİKLİK SONU ===