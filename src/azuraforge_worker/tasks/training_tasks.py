import logging
import os
import traceback
import json
from datetime import datetime
from importlib.metadata import entry_points
from importlib import resources
from contextlib import contextmanager
import redis

from ..celery_app import celery_app, engine
from ..callbacks import RedisProgressCallback
from azuraforge_dbmodels import Experiment, get_session_local

# --- Redis ve Pipeline Kaydı ---
REDIS_PIPELINES_KEY = "azuraforge:pipelines_catalog"
AVAILABLE_PIPELINES = {}

def discover_and_register_pipelines():
    """
    Yüklü pipeline eklentilerini, konfigürasyonlarını ve UI şemalarını
    keşfeder, Redis'e kaydeder ve global AVAILABLE_PIPELINES değişkenini günceller.
    """
    global AVAILABLE_PIPELINES
    logging.info("Worker: Discovering and registering pipelines...")
    
    try:
        pipeline_eps = entry_points(group='azuraforge.pipelines')
        config_eps = entry_points(group='azuraforge.configs')

        pipeline_class_map = {ep.name: ep.load() for ep in pipeline_eps}
        config_func_map = {ep.name: ep.load() for ep in config_eps}

        catalog_to_register = {}
        logging.info(f"Processing {len(pipeline_class_map)} discovered pipeline classes...")

        for name, pipeline_class in pipeline_class_map.items():
            logging.info(f"  -> Processing pipeline: '{name}'")
            
            default_config = {}
            if name in config_func_map:
                try: default_config = config_func_map[name]()
                except Exception as e: logging.error(f"    - Error loading config for '{name}': {e}", exc_info=True)

            form_schema = {}
            try:
                package_name = pipeline_class.__module__.split('.')[0]
                with resources.open_text(package_name, "form_schema.json") as f:
                    form_schema = json.load(f)
            except (ModuleNotFoundError, FileNotFoundError):
                logging.warning(f"    - NO form_schema.json FOUND for pipeline '{name}'.")
            except Exception as e:
                logging.error(f"    - Error loading form_schema.json for '{name}': {e}", exc_info=True)
            
            catalog_to_register[name] = json.dumps({
                "id": name, "default_config": default_config, "form_schema": form_schema
            })
        
        AVAILABLE_PIPELINES = pipeline_class_map

        if not catalog_to_register:
            logging.warning("Worker: No pipelines found to register.")
            return

        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        r = redis.from_url(redis_url)
        pipe = r.pipeline()
        pipe.delete(REDIS_PIPELINES_KEY)
        if catalog_to_register:
            pipe.hmset(REDIS_PIPELINES_KEY, catalog_to_register)
        pipe.execute()
        
        logging.info(f"Worker: Registration complete. {len(catalog_to_register)} pipelines registered to Redis.")

    except Exception as e:
        logging.error(f"Worker: CRITICAL ERROR during pipeline discovery/registration: {e}", exc_info=True)
        AVAILABLE_PIPELINES = {}

discover_and_register_pipelines()

@contextmanager
def get_db():
    """Veritabanı oturumu için bir context manager sağlar."""
    if engine is None:
        raise RuntimeError("Database engine not initialized for this worker process.")
    
    SessionLocal = get_session_local(engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "/app/reports"))
os.makedirs(REPORTS_BASE_DIR, exist_ok=True)

@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, config: dict):
    task_id = self.request.id
    pipeline_name = config.get("pipeline_name", "unknown_pipeline")
    
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_id = f"{pipeline_name}_{run_timestamp}_{task_id[:8]}"

    experiment_dir = os.path.join(REPORTS_BASE_DIR, pipeline_name, experiment_id)
    os.makedirs(experiment_dir, exist_ok=True)
    
    config.update({
        'experiment_id': experiment_id, 'task_id': task_id, 
        'experiment_dir': experiment_dir, 'start_time': datetime.now().isoformat()
    })

    try:
        if pipeline_name not in AVAILABLE_PIPELINES:
            logging.warning(f"Pipeline '{pipeline_name}' not in cache. Retrying discovery...")
            discover_and_register_pipelines()
            if pipeline_name not in AVAILABLE_PIPELINES:
                 raise ValueError(f"Pipeline '{pipeline_name}' not found after rediscovery.")

        PipelineClass = AVAILABLE_PIPELINES[pipeline_name]
        
        with get_db() as db:
            new_experiment = Experiment(
                id=experiment_id, task_id=task_id, pipeline_name=pipeline_name,
                status="STARTED", config=config, batch_id=config.get('batch_id'),
                batch_name=config.get('batch_name')
            )
            db.add(new_experiment)
            db.commit()

        pipeline_instance = PipelineClass(config)
        redis_callback = RedisProgressCallback(task_id=task_id)
        results = pipeline_instance.run(callbacks=[redis_callback])

        with get_db() as db:
            exp_to_update = db.query(Experiment).filter(Experiment.id == experiment_id).first()
            if exp_to_update:
                exp_to_update.status = "SUCCESS"
                exp_to_update.results = results
                exp_to_update.completed_at = datetime.now(datetime.utcnow().tzinfo)
                db.commit()
        
        return {"experiment_id": experiment_id, "status": "SUCCESS"}

    except Exception as e:
        tb_str = traceback.format_exc()
        logging.error(f"PIPELINE CRITICAL FAILURE in task {task_id}: {e}\n{tb_str}")
        
        with get_db() as db:
            exp_to_update = db.query(Experiment).filter(Experiment.id == experiment_id).first()
            if exp_to_update:
                exp_to_update.status = "FAILURE"
                exp_to_update.error = {"message": str(e), "traceback": tb_str}
                exp_to_update.failed_at = datetime.now(datetime.utcnow().tzinfo)
                db.commit()
        
        raise e