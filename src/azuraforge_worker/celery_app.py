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

# Bu global değişken, her bir worker sürecinin kendi DB motorunu tutmasını sağlar.
engine = None

@worker_process_init.connect
def init_worker_db_connection(**kwargs):
    """
    Her bir Celery alt süreci (worker process) başladığında çağrılır.
    Bu, her sürece kendi veritabanı bağlantı havuzunu oluşturma imkanı tanır.
    """
    global engine
    print(f"WORKER: Initializing DB connection for worker process PID: {os.getpid()}")
    
    # dbmodels kütüphanesinden veritabanı URL'ini ve motor oluşturucuyu al
    from azuraforge_dbmodels.database import DATABASE_URL, sa_create_engine
    
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL could not be determined. Worker cannot start.")
        
    engine = sa_create_engine(DATABASE_URL)
    print(f"WORKER: DB connection for process {os.getpid()} initialized successfully.")

@worker_process_shutdown.connect
def shutdown_worker_db_connection(**kwargs):
    """Her bir Celery alt süreci kapandığında çağrılır."""
    global engine
    if engine:
        print(f"WORKER: Disposing DB connection for worker process PID: {os.getpid()}...")
        engine.dispose()