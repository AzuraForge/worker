# worker/src/azuraforge_worker/celery_app.py
"""
Bu modül, Celery uygulamasını ve worker süreçleri için sinyal (signal) 
yöneticilerini yapılandırır.
"""
import os
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

engine = None

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "azuraforge_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["azuraforge_worker.tasks.training_tasks"]
)

def _get_database_url_for_worker() -> str:
    # --- DEĞİŞİKLİK BURADA BAŞLIYOR ---
    # 1. Öncelik: Ortamdan gelen hazır DATABASE_URL
    if db_url := os.getenv("DATABASE_URL"):
        return db_url
    
    # 2. Öncelik: Parçalardan birleştirme (sır dosyaları veya .env'den gelenler)
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_DB_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB")

    if all([user, password, host, port, db_name]):
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"
        
    # 3. Öncelik: Hiçbiri yoksa hata ver
    raise ValueError(
        "Could not determine DATABASE_URL. "
        "Please set either DATABASE_URL directly, or all of "
        "POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_HOST."
    )
    # --- DEĞİŞİKLİK BURADA BİTİYOR ---


@worker_process_init.connect
def init_worker_db_connection(**kwargs):
    global engine
    process_id = os.getpid()
    print(f"WORKER: Initializing DB connection for worker process PID: {process_id}")
    
    from azuraforge_dbmodels import sa_create_engine
    
    try:
        db_url = _get_database_url_for_worker()
        engine = sa_create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as connection:
            print(f"WORKER: DB connection for process {process_id} validated successfully.")
    except Exception as e:
        print(f"WORKER: FATAL - DB connection for process {process_id} failed: {e}")
        engine = None
        raise

@worker_process_shutdown.connect
def shutdown_worker_db_connection(**kwargs):
    global engine
    if engine:
        process_id = os.getpid()
        print(f"WORKER: Disposing DB connection for worker process PID: {process_id}...")
        engine.dispose()