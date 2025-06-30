# worker/src/azuraforge_worker/database.py

import os
from sqlalchemy import create_engine as sa_create_engine, Column, String, JSON, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Experiment(Base):
    __tablename__ = "experiments"
    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, index=True, nullable=False)
    batch_id = Column(String, index=True, nullable=True)
    batch_name = Column(String, nullable=True)
    pipeline_name = Column(String, index=True, nullable=False)
    status = Column(String, index=True, default="PENDING")
    config = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    error = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Experiment(id='{self.id}', status='{self.status}')>"

_SessionLocal = None

def get_session_local():
    """SessionLocal fabrikasını yalnızca gerektiğinde oluşturur (singleton)."""
    global _SessionLocal
    if _SessionLocal is None:
        # celery_app'ten her süreç için özel olarak oluşturulmuş engine'i al
        from .celery_app import engine
        if engine is None:
            raise RuntimeError("Database engine not initialized for this worker process.")
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal

def init_db():
    """Ana süreçte veritabanı tablolarını oluşturur."""
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL ortam değişkeni ayarlanmamış!")
    
    # Tablo oluşturma işlemi için geçici bir motor oluştur.
    engine = sa_create_engine(DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    engine.dispose()