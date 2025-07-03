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
    """Her bir Celery alt süreci başladığında çağrılır."""
    global engine
    print("Initializing DB connection for worker process...")
    from azuraforge_dbmodels import sa_create_engine
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set, cannot initialize DB engine.")
        
    engine = sa_create_engine(db_url)
    print(f"DB connection for worker process {os.getpid()} initialized.")

@worker_process_shutdown.connect
def shutdown_worker_db_connection(**kwargs):
    """Her bir Celery alt süreci kapandığında çağrılır."""
    global engine
    if engine:
        print(f"Disposing DB connection for worker process {os.getpid()}...")
        engine.dispose()