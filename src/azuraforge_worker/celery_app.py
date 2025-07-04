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

def get_worker_database_url() -> str:
    """Worker için DATABASE_URL'i ortam değişkenlerinden oluşturur."""
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "postgres")
    db_name = os.environ.get("POSTGRES_DB", "azuraforge")

    if not all([user, password, host, db_name]):
        raise ValueError("Database credentials not found in environment for worker.")
        
    return f"postgresql+psycopg2://{user}:{password}@{host}:5432/{db_name}"

@worker_process_init.connect
def init_worker_db_connection(**kwargs):
    """Her bir Celery alt süreci başladığında çağrılır."""
    global engine
    print(f"WORKER: Initializing DB connection for worker process PID: {os.getpid()}")
    
    # dbmodels'dan sadece engine oluşturucuyu al
    from azuraforge_dbmodels import sa_create_engine
    
    db_url = get_worker_database_url()
    engine = sa_create_engine(db_url)
    print(f"WORKER: DB connection for process {os.getpid()} initialized successfully.")

@worker_process_shutdown.connect
def shutdown_worker_db_connection(**kwargs):
    """Her bir Celery alt süreci kapandığında çağrılır."""
    global engine
    if engine:
        print(f"WORKER: Disposing DB connection for worker process PID: {os.getpid()}...")
        engine.dispose()