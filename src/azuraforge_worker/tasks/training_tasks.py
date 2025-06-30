# worker/src/azuraforge_worker/tasks/training_tasks.py

import logging
import os
import traceback
from datetime import datetime
from importlib.metadata import entry_points
from contextlib import contextmanager

from ..celery_app import celery_app
from ..callbacks import RedisProgressCallback
from ..database import SessionLocal, Experiment # YENİ: Veritabanı modelini ve oturumunu import et

# --- Veritabanı Oturum Yönetimi ---
@contextmanager
def get_db():
    """Veritabanı oturumu için bir context manager sağlar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pipeline Keşfi (Değişiklik Yok) ---
def discover_pipelines():
    logging.info("Worker: Discovering installed AzuraForge pipeline plugins and configurations...")
    discovered = {}
    try:
        pipeline_entry_points = entry_points(group='azuraforge.pipelines')
        for ep in pipeline_entry_points:
            discovered[ep.name] = {'pipeline_class': ep.load()}
        
        config_entry_points = entry_points(group='azuraforge.configs')
        for ep in config_entry_points:
            if ep.name in discovered:
                discovered[ep.name]['get_config_func'] = ep.load()
    except Exception as e:
        logging.error(f"Worker: Error discovering pipelines or configs: {e}", exc_info=True)
    
    for p_id, p_info in discovered.items():
        logging.info(f"Worker: Discovered pipeline '{p_id}' (Config available: {'get_config_func' in p_info})")
    return discovered

AVAILABLE_PIPELINES_AND_CONFIGS = discover_pipelines()
REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "/app/reports"))
os.makedirs(REPORTS_BASE_DIR, exist_ok=True)

# --- Celery Görevi (Tamamen Yenilendi) ---
@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, config: dict):
    task_id = self.request.id
    pipeline_name = config.get("pipeline_name", "unknown_pipeline")
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_id = f"{pipeline_name}_{run_timestamp}_{task_id[:8]}"

    # Raporlama için hala dosya sistemini kullanabiliriz
    experiment_dir = os.path.join(REPORTS_BASE_DIR, pipeline_name, experiment_id)
    os.makedirs(experiment_dir, exist_ok=True)
    
    # Konfigürasyonu zenginleştir
    config['experiment_id'] = experiment_id
    config['task_id'] = task_id
    config['experiment_dir'] = experiment_dir
    config['start_time'] = datetime.now().isoformat()

    try:
        if not pipeline_name or pipeline_name not in AVAILABLE_PIPELINES_AND_CONFIGS:
            raise ValueError(f"Pipeline '{pipeline_name}' not found or installed.")

        # --- Veritabanı Kaydı Başlatma ---
        with get_db() as db:
            new_experiment = Experiment(
                id=experiment_id,
                task_id=task_id,
                pipeline_name=pipeline_name,
                status="STARTED",
                config=config
            )
            db.add(new_experiment)
            db.commit()
            logging.info(f"Worker: Experiment {experiment_id} 'STARTED' olarak veritabanına kaydedildi.")

        # Pipeline'ı çalıştır
        PipelineClass = AVAILABLE_PIPELINES_AND_CONFIGS[pipeline_name]['pipeline_class']
        pipeline_instance = PipelineClass(config)
        redis_callback = RedisProgressCallback(task_id=task_id)
        results = pipeline_instance.run(callbacks=[redis_callback])

        # --- Veritabanı Kaydını Başarıyla Güncelleme ---
        with get_db() as db:
            exp_to_update = db.query(Experiment).filter(Experiment.id == experiment_id).first()
            if exp_to_update:
                exp_to_update.status = "SUCCESS"
                exp_to_update.results = results
                exp_to_update.completed_at = datetime.now(datetime.utcnow().tzinfo)
                db.commit()
                logging.info(f"Worker: Experiment {experiment_id} 'SUCCESS' olarak güncellendi.")
        
        logging.info(f"Worker: Task {task_id} completed successfully.")
        return {"experiment_id": experiment_id, "status": "SUCCESS"}

    except Exception as e:
        tb_str = traceback.format_exc()
        logging.error(f"PIPELINE CRITICAL FAILURE in task {task_id} (experiment: {experiment_id}): {e}")
        logging.error(f"FULL TRACEBACK:\n{tb_str}")
        
        # --- Veritabanı Kaydını Hatayla Güncelleme ---
        with get_db() as db:
            exp_to_update = db.query(Experiment).filter(Experiment.id == experiment_id).first()
            if exp_to_update:
                exp_to_update.status = "FAILURE"
                exp_to_update.error = {"message": str(e), "traceback": tb_str}
                exp_to_update.failed_at = datetime.now(datetime.utcnow().tzinfo)
                db.commit()
                logging.error(f"Worker: Experiment {experiment_id} 'FAILURE' olarak güncellendi.")
        
        raise e