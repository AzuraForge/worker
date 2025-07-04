# worker/src/azuraforge_worker/database.py
"""
Bu modül, worker görevleri içinde veritabanı session'ı sağlamak için
bir context manager sunar.
"""
import os
from sqlalchemy.orm import sessionmaker

# Her süreç için Session fabrikasını saklamak üzere global bir değişken.
_SessionLocal = None

def get_db_session():
    """
    Mevcut worker süreci için bir veritabanı session'ı oluşturur ve yield eder.
    Bu, 'with get_db_session() as db:' şeklinde kullanılmalıdır.
    """
    global _SessionLocal
    
    # Her süreçte bir kez oluşturulan 'engine' nesnesini celery_app'ten al.
    from .celery_app import engine
    
    if engine is None:
        raise RuntimeError(
            "Database engine is not initialized for this worker process. "
            "`worker_process_init` signal might have failed."
        )

    # Eğer bu süreç için Session fabrikası daha önce oluşturulmamışsa, şimdi oluştur.
    if _SessionLocal is None:
        print(f"WORKER: First-time session factory creation for PID: {os.getpid()}")
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()