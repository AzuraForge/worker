# worker/src/azuraforge_worker/database.py

from sqlalchemy.orm import sessionmaker

# Bu global değişken, her süreç için bir kere oluşturulacak Session fabrikasını tutar.
_SessionLocal = None

def get_db_session():
    """
    Mevcut worker süreci için bir veritabanı session'ı oluşturur ve döndürür.
    Bu fonksiyon, görevler içinde kullanılacak.
    """
    global _SessionLocal
    
    # celery_app'ten her süreç için özel olarak oluşturulmuş engine'i al
    from .celery_app import engine
    
    if engine is None:
        # Bu durum, init sinyalinin çalışmadığı veya başarısız olduğu anlamına gelir.
        raise RuntimeError("Database engine not initialized for this worker process. `worker_process_init` might have failed.")

    # Eğer bu süreç için Session fabrikası daha önce oluşturulmamışsa, şimdi oluştur.
    if _SessionLocal is None:
        print(f"WORKER: Creating SessionLocal factory for process PID: {os.getpid()}")
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Yeni bir session oluştur
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()