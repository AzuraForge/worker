# worker/src/azuraforge_worker/tasks/training_tasks.py
import logging
import os
import traceback
import json
from datetime import datetime
from importlib.metadata import entry_points
from importlib import resources
from contextlib import contextmanager
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import redis
from functools import lru_cache

from ..celery_app import celery_app
from ..database import get_db_session
from azuraforge_dbmodels import Experiment
from ..callbacks import RedisProgressCallback

REDIS_PIPELINES_KEY = "azuraforge:pipelines_catalog"
AVAILABLE_PIPELINES: Dict[str, Any] = {}
REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "/app/reports"))

@lru_cache(maxsize=16)
def get_shared_data(pipeline_name: str, full_config_json: str) -> pd.DataFrame:
    """
    Verilen pipeline ve parametreler için veriyi disk önbelleğinden veya kaynaktan yükler.
    LRU cache sayesinde bu fonksiyon aynı parametrelerle tekrar çağrılmaz.
    """
    from azuraforge_learner.caching import get_cache_filepath, load_from_cache, save_to_cache
    
    pipeline_class = AVAILABLE_PIPELINES.get(pipeline_name)
    if not pipeline_class:
        raise ValueError(f"Paylaşımlı veri yüklenirken pipeline '{pipeline_name}' bulunamadı.")

    # === KRİTİK DÜZELTME BAŞLANGICI: Pydantic Hatasını Çözme ===
    # Geçici pipeline örneğini, tam ve geçerli bir konfigürasyonla oluşturuyoruz.
    # Bu, Pydantic doğrulamasından geçmesini sağlar.
    full_config = json.loads(full_config_json)
    temp_pipeline_instance = pipeline_class(full_config)
    # === KRİTİK DÜZELTME SONU ===
    
    caching_params = temp_pipeline_instance.get_caching_params()
    cache_dir = os.getenv("CACHE_DIR", ".cache")
    cache_filepath = get_cache_filepath(cache_dir, pipeline_name, caching_params)
    
    system_config = temp_pipeline_instance.config.get("system", {})
    cache_max_age = system_config.get("cache_max_age_hours", 24)

    cached_data = load_from_cache(cache_filepath, cache_max_age)
    if cached_data is not None:
        logging.info(f"Paylaşımlı önbellek için veri diskten yüklendi: {cache_filepath}")
        return cached_data
    
    logging.info(f"Paylaşımlı önbellek için veri kaynaktan indiriliyor. Parametreler: {caching_params}")
    source_data = temp_pipeline_instance._load_data_from_source()
    if isinstance(source_data, pd.DataFrame) and not source_data.empty:
        save_to_cache(source_data, cache_filepath)

    return source_data

# ... (discover_and_register_pipelines ve diğer yardımcı fonksiyonlar aynı kalıyor) ...
def discover_and_register_pipelines():
    global AVAILABLE_PIPELINES
    logging.info("Worker: Discovering and registering pipelines via entry_points...")
    
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
                except Exception as e: logging.error(f"Error loading default config for '{name}': {e}", exc_info=True)
            
            try:
                package_name = pipeline_class.__module__.split('.')[0]
                with resources.open_text(package_name, "form_schema.json") as f:
                    form_schema = json.load(f)
            except (FileNotFoundError, ModuleNotFoundError):
                logging.warning(f"No form_schema.json found for pipeline '{name}'.")
            except Exception as e:
                 logging.error(f"Error loading form_schema for '{name}': {e}", exc_info=True)

            catalog_to_register[name] = json.dumps({
                "id": name, "default_config": default_config, "form_schema": form_schema
            })
            
        AVAILABLE_PIPELINES = pipeline_class_map
        if not catalog_to_register:
            logging.warning("Worker: No pipelines found to register.")
            return

        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        r = redis.from_url(redis_url)
        r.delete(REDIS_PIPELINES_KEY)
        r.hset(REDIS_PIPELINES_KEY, mapping=catalog_to_register)
        logging.info(f"Worker: Registration complete. {len(catalog_to_register)} pipelines registered to Redis.")
        
    except Exception as e:
        logging.error(f"Worker: CRITICAL ERROR during pipeline discovery: {e}", exc_info=True)
        AVAILABLE_PIPELINES.clear()

discover_and_register_pipelines()
os.makedirs(REPORTS_BASE_DIR, exist_ok=True)

@contextmanager
def get_db():
    yield from get_db_session()

def _prepare_and_log_initial_state(task_id: str, user_config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    pipeline_name = user_config.get("pipeline_name")
    if not pipeline_name: raise ValueError("'pipeline_name' must be provided in the configuration.")
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_id = f"{pipeline_name}_{run_timestamp}_{task_id[:8]}"
    full_config = {
        **user_config, 'experiment_id': experiment_id, 'task_id': task_id,
        'experiment_dir': os.path.join(REPORTS_BASE_DIR, pipeline_name, experiment_id),
        'start_time': datetime.now().isoformat(),
    }
    os.makedirs(full_config['experiment_dir'], exist_ok=True)
    with get_db() as db:
        new_experiment = Experiment(
            id=experiment_id, task_id=task_id, pipeline_name=pipeline_name, status="STARTED", 
            config=full_config, batch_id=user_config.get('batch_id'), batch_name=user_config.get('batch_name')
        )
        db.add(new_experiment)
        db.commit()
        logging.info(f"Experiment {experiment_id} logged to DB with status STARTED.")
    return experiment_id, full_config

def _update_experiment_on_completion(experiment_id: str, results: Dict[str, Any], model_path: Optional[str]):
    with get_db() as db:
        exp_to_update = db.query(Experiment).filter(Experiment.id == experiment_id).first()
        if exp_to_update:
            exp_to_update.status = "SUCCESS"
            exp_to_update.results = results
            exp_to_update.model_path = model_path
            exp_to_update.completed_at = datetime.now(datetime.utcnow().tzinfo)
            db.commit()
            logging.info(f"Experiment {experiment_id} updated in DB with status SUCCESS.")

def _update_experiment_on_failure(experiment_id: str, error: Exception):
    tb_str = traceback.format_exc()
    error_message = str(error)
    error_code = "PIPELINE_EXECUTION_ERROR"
    if isinstance(error, (ValueError, TypeError)): error_code = "PIPELINE_VALUE_ERROR"
    elif isinstance(error, FileNotFoundError): error_code = "PIPELINE_FILE_NOT_FOUND"
    logging.error(f"PIPELINE CRITICAL FAILURE: ({error_code}) {error_message}\n{tb_str}")
    with get_db() as db:
        exp_to_update = db.query(Experiment).filter(Experiment.id == experiment_id).first()
        if exp_to_update:
            exp_to_update.status = "FAILURE"
            exp_to_update.error = {"error_code": error_code, "message": error_message, "traceback": tb_str}
            exp_to_update.failed_at = datetime.now(datetime.utcnow().tzinfo)
            db.commit()
            logging.info(f"Experiment {experiment_id} updated in DB with status FAILURE.")

@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, user_config: Dict[str, Any]):
    experiment_id = None
    try:
        experiment_id, full_config = _prepare_and_log_initial_state(self.request.id, user_config)
        pipeline_name = full_config['pipeline_name']

        PipelineClass = AVAILABLE_PIPELINES.get(pipeline_name)
        if not PipelineClass:
            discover_and_register_pipelines()
            PipelineClass = AVAILABLE_PIPELINES.get(pipeline_name)
            if not PipelineClass: raise ValueError(f"Pipeline '{pipeline_name}' is not registered or could not be found.")

        pipeline_instance = PipelineClass(full_config)
        
        run_kwargs = {}
        from azuraforge_learner.pipelines import TimeSeriesPipeline
        if isinstance(pipeline_instance, TimeSeriesPipeline):
            # === KRİTİK DÜZELTME BAŞLANGICI: Pydantic Hatasını Çözme ===
            # get_shared_data fonksiyonuna tam konfigürasyonu gönderiyoruz.
            full_config_json = json.dumps(full_config, sort_keys=True)
            shared_data = get_shared_data(pipeline_name, full_config_json)
            # === KRİTİK DÜZELTME SONU ===
            run_kwargs['raw_data'] = shared_data

        redis_callback = RedisProgressCallback(task_id=self.request.id)
        results = pipeline_instance.run(callbacks=[redis_callback], **run_kwargs)

        model_path = None
        if hasattr(pipeline_instance, 'learner') and pipeline_instance.learner:
            model_filename = "best_model.json"
            model_path = os.path.join(full_config['experiment_dir'], model_filename)
            pipeline_instance.learner.save_model(model_path)
            logging.info(f"Model for experiment {experiment_id} saved to {model_path}")

        _update_experiment_on_completion(experiment_id, results, model_path)
        return {"experiment_id": experiment_id, "status": "SUCCESS", "model_path": model_path}
        
    except Exception as e:
        if experiment_id: _update_experiment_on_failure(experiment_id, e)
        else: logging.error(f"CRITICAL: Could not log failure for task {self.request.id}. Error: {e}", exc_info=True)
        raise e