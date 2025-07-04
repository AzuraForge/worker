# worker/src/azuraforge_worker/tasks/training_tasks.py

import logging
import os
import traceback
import json
from datetime import datetime
from importlib.metadata import entry_points
from importlib import resources
from contextlib import contextmanager
import redis

from ..celery_app import celery_app
# DÜZELTME: Artık 'database.py'den sadece 'get_db_session'ı alıyoruz
from ..database import get_db_session
from azuraforge_dbmodels import Experiment

# ... (discover_and_register_pipelines ve diğer global tanımlar aynı kalıyor) ...
REDIS_PIPELINES_KEY = "azuraforge:pipelines_catalog"
AVAILABLE_PIPELINES = {}

def discover_and_register_pipelines():
    #... bu fonksiyonun içeriği aynı ...
    global AVAILABLE_PIPELINES
    logging.info("Worker: Discovering and registering pipelines...")
    try:
        pipeline_eps = entry_points(group='azuraforge.pipelines')
        config_eps = entry_points(group='azuraforge.configs')
        pipeline_class_map = {ep.name: ep.load() for ep in pipeline_eps}
        config_func_map = {ep.name: ep.load() for ep in config_eps}
        catalog_to_register = {}
        for name, pipeline_class in pipeline_class_map.items():
            default_config, form_schema = {}, {}
            if name in config_func_map:
                try: default_config = config_func_map[name]()
                except Exception as e: logging.error(f"Error loading config for '{name}': {e}", exc_info=True)
            try:
                package_name = pipeline_class.__module__.split('.')[0]
                with resources.open_text(package_name, "form_schema.json") as f:
                    form_schema = json.load(f)
            except Exception: logging.warning(f"No form_schema.json found for pipeline '{name}'.")
            catalog_to_register[name] = json.dumps({"id": name, "default_config": default_config, "form_schema": form_schema})
        AVAILABLE_PIPELINES = pipeline_class_map
        if not catalog_to_register:
            logging.warning("Worker: No pipelines found to register.")
            return
        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        r = redis.from_url(redis_url)
        r.hset(REDIS_PIPELINES_KEY, mapping=catalog_to_register)
        logging.info(f"Worker: Registration complete. {len(catalog_to_register)} pipelines registered.")
    except Exception as e:
        logging.error(f"Worker: CRITICAL ERROR during pipeline discovery: {e}", exc_info=True)
        AVAILABLE_PIPELINES = {}

discover_and_register_pipelines()

# DÜZELTME: Bu context manager artık yeni `get_db_session` fonksiyonunu kullanacak
@contextmanager
def get_db():
    # Bu, 'database.py'deki yield/finally bloğunu çağıracak
    yield from get_db_session()

REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "/app/reports"))
os.makedirs(REPORTS_BASE_DIR, exist_ok=True)

@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, config: dict):
    # ... (görev başlangıcındaki mantık aynı) ...
    task_id = self.request.id
    pipeline_name = config.get("pipeline_name", "unknown_pipeline")
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_id = f"{pipeline_name}_{run_timestamp}_{task_id[:8]}"
    experiment_dir = os.path.join(REPORTS_BASE_DIR, pipeline_name, experiment_id)
    os.makedirs(experiment_dir, exist_ok=True)
    config.update({'experiment_id': experiment_id, 'task_id': task_id, 'experiment_dir': experiment_dir, 'start_time': datetime.now().isoformat()})
    
    from ..callbacks import RedisProgressCallback
    
    try:
        # ... (pipeline bulma mantığı aynı) ...
        if pipeline_name not in AVAILABLE_PIPELINES:
            discover_and_register_pipelines()
            if pipeline_name not in AVAILABLE_PIPELINES:
                 raise ValueError(f"Pipeline '{pipeline_name}' not found after rediscovery.")

        PipelineClass = AVAILABLE_PIPELINES[pipeline_name]
        
        # 'with get_db()' şimdi her süreçte doğru çalışacak
        with get_db() as db:
            db.add(Experiment(id=experiment_id, task_id=task_id, pipeline_name=pipeline_name, status="STARTED", config=config, batch_id=config.get('batch_id'), batch_name=config.get('batch_name')))
            db.commit()

        pipeline_instance = PipelineClass(config)
        redis_callback = RedisProgressCallback(task_id=task_id)
        results = pipeline_instance.run(callbacks=[redis_callback])
        
        # ... (model kaydetme mantığı aynı) ...
        model_path = None
        if hasattr(pipeline_instance, 'learner') and pipeline_instance.learner:
            model_filename = "best_model.json"
            model_path = os.path.join(experiment_dir, model_filename)
            pipeline_instance.learner.save_model(model_path)
            logging.info(f"Model for experiment {experiment_id} saved to {model_path}")
        else:
            logging.warning(f"Learner instance not found for experiment {experiment_id}. Model not saved.")

        # 'with get_db()' şimdi her süreçte doğru çalışacak
        with get_db() as db:
            exp_to_update = db.query(Experiment).filter(Experiment.id == experiment_id).first()
            if exp_to_update:
                exp_to_update.status = "SUCCESS"
                exp_to_update.results = results
                exp_to_update.model_path = model_path
                exp_to_update.completed_at = datetime.now(datetime.utcnow().tzinfo)
                db.commit()
        
        return {"experiment_id": experiment_id, "status": "SUCCESS", "model_path": model_path}
        
    except Exception as e:
        # ... (hata yakalama bloğu aynı) ...
        tb_str = traceback.format_exc()
        error_message = str(e)
        error_code = "PIPELINE_EXECUTION_ERROR"
        if isinstance(e, ValueError): error_code = "PIPELINE_VALUE_ERROR"
        elif isinstance(e, FileNotFoundError): error_code = "PIPELINE_FILE_NOT_FOUND"
        logging.error(f"PIPELINE CRITICAL FAILURE in task {task_id}: ({error_code}) {error_message}\n{tb_str}")
        
        # 'with get_db()' şimdi her süreçte doğru çalışacak
        with get_db() as db:
            exp_to_update = db.query(Experiment).filter(Experiment.id == experiment_id).first()
            if exp_to_update:
                exp_to_update.status = "FAILURE"
                exp_to_update.error = {"error_code": error_code, "message": error_message, "traceback": tb_str}
                exp_to_update.failed_at = datetime.now(datetime.utcnow().tzinfo); 
                db.commit()
        raise e