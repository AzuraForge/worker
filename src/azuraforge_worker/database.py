# worker/src/azuraforge_worker/database.py

import os
from sqlalchemy import create_engine, Column, String, JSON, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func

# Ortam değişkeninden veritabanı URL'sini al
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL ortam değişkeni ayarlanmamış!")

# Veritabanı motorunu oluştur
engine = create_engine(DATABASE_URL)

# Veritabanı oturumları oluşturmak için bir fabrika
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Tüm modellerimizin miras alacağı temel sınıf
Base = declarative_base()

# --- VERİTABANI MODELİ TANIMI ---

class Experiment(Base):
    """
    Veritabanındaki 'experiments' tablosunu temsil eden SQLAlchemy modeli.
    """
    __tablename__ = "experiments"

    # Sütunlar
    id = Column(String, primary_key=True, index=True) # Bu, bizim experiment_id'miz olacak
    task_id = Column(String, index=True, nullable=False)
    pipeline_name = Column(String, index=True, nullable=False)
    status = Column(String, index=True, default="PENDING")

    # JSONB tipi, esnek konfigürasyon ve sonuç depolama için idealdir
    config = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    error = Column(JSON, nullable=True)

    # Zaman damgaları
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Experiment(id='{self.id}', status='{self.status}')>"

def init_db():
    """
    Veritabanı tablolarını oluşturur.
    Bu fonksiyon, worker veya API ilk başladığında çağrılabilir.
    """
    Base.metadata.create_all(bind=engine)

# Worker ilk import edildiğinde veritabanının hazır olmasını sağla
init_db()