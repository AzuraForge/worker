# worker/src/azuraforge_worker/database.py

import os
from sqlalchemy import create_engine, Column, String, JSON, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL ortam değişkeni ayarlanmamış!")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, index=True, nullable=False)
    
    # === YENİ ALANLAR ===
    batch_id = Column(String, index=True, nullable=True) # Bir grup deneyi birleştirmek için
    batch_name = Column(String, nullable=True) # Kullanıcının verdiği grup adı
    # === DEĞİŞİKLİK SONU ===
    
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

def init_db():
    Base.metadata.create_all(bind=engine)

init_db()