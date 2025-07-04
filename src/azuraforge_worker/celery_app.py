# worker/src/azuraforge_worker/celery_app.py
"""
Bu modül, Celery uygulamasını ve worker süreçleri için sinyal (signal) 
yöneticilerini yapılandırır.
"""
import os
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

# Global değişken, her bir worker sürecinin kendi DB motorunu tutmasını sağlar.
# Başlangıçta None olarak ayarlanır.
engine = None

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "azuraforge_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["azuraforge_worker.tasks.training_tasks"]
)

def _create_database_url_for_worker() -> str:
    """Worker için DATABASE_URL'i ortam değişkenlerinden oluşturur."""
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_DB_PORT", "5432")
    db_name = os.environ.get("POSTGRES_DB", "azuraforge")

    if not all([user, password, host, port, db_name]):
        # Bu, entrypoint script'inin sırları doğru şekilde export edemediği anlamına gelir.
        raise ValueError("Database credentials not found in worker's environment.")
        
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"

@worker_process_init.connect
def init_worker_db_connection(**kwargs):
    """
    Her bir Celery alt süreci (worker process) başladığında tetiklenir.
    Bu fonksiyon, her alt sürece kendi veritabanı bağlantı havuzunu oluşturur.
    """
    global engine
    process_id = os.getpid()
    print(f"WORKER: Initializing DB connection for worker process PID: {process_id}")
    
    from azuraforge_dbmodels import sa_create_engine
    
    try:
        db_url = _create_database_url_for_worker()
        engine = sa_create_engine(db_url, pool_pre_ping=True)
        # Bağlantıyı test etmek için basit bir sorgu
        with engine.connect() as connection:
            print(f"WORKER: DB connection for process {process_id} validated successfully.")
    except Exception as e:
        print(f"WORKER: FATAL - DB connection for process {process_id} failed: {e}")
        # Hata durumunda motoru None olarak bırakarak görevin başarısız olmasını sağla
        engine = None
        raise

@worker_process_shutdown.connect
def shutdown_worker_db_connection(**kwargs):
    """Her bir Celery alt süreci kapandığında çağrılır."""
    global engine
    if engine:
        process_id = os.getpid()
        print(f"WORKER: Disposing DB connection for worker process PID: {process_id}...")
        engine.dispose()