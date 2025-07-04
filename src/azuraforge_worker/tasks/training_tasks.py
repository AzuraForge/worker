# worker/src/azuraforge_worker/tasks/training_tasks.py
"""
Bu modül, platformun ana model eğitim görevlerini içerir. Celery tarafından
keşfedilir ve çalıştırılır.
"""
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
from ..database import get_db_session
from azuraforge_dbmodels import Experiment
from ..callbacks import RedisProgressCallback

# --- Global Değişkenler ve Başlangıç Yapılandırması ---

REDIS_PIPELINES_KEY = "azuraforge:pipelines_catalog"
AVAILABLE_PIPELINES = {}
REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "/app/reports"))

def discover_and_register_pipelines():
    """
    Sisteme `entry_points` ile kurulmuş tüm pipeline eklentilerini keşfeder
    ve Redis'e bir katalog olarak kaydeder. Bu, API'nin hangi pipeline'ların
    kullanılabilir olduğunu bilmesini sağlar.
    """
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
            
            # Varsayılan konfigürasyonu yüklemeye çalış
            if name in config_func_map:
                try:
                    default_config = config_func_map[name]()
                except Exception as e:
                    logging.error(f"Error loading default config for '{name}': {e}", exc_info=True)
            
            # Form şemasını yüklemeye çalış
            try:
                package_name = pipeline_class.__module__.split('.')[0]
                with resources.open_text(package_name, "form_schema.json") as f:
                    form_schema = json.load(f)
            except (FileNotFoundError, ModuleNotFoundError):
                logging.warning(f"No form_schema.json found for pipeline '{name}'.")
            except Exception as e:
                 logging.error(f"Error loading form_schema for '{name}': {e}", exc_info=True)

            catalog_to_register[name] = json.dumps({
                "id": name, 
                "default_config": default_config, 
                "form_schema": form_schema
            })
            
        AVAILABLE_PIPELINES = pipeline_class_map
        if not catalog_to_register:
            logging.warning("Worker: No pipelines found to register.")
            return

        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        r = redis.from_url(redis_url)
        # Önceki kaydı temizleyip yenisini yazmak daha güvenli
        r.delete(REDIS_PIPELINES_KEY)
        r.hset(REDIS_PIPELINES_KEY, mapping=catalog_to_register)
        logging.info(f"Worker: Registration complete. {len(catalog_to_register)} pipelines registered to Redis.")
        
    except Exception as e:
        logging.error(f"Worker: CRITICAL ERROR during pipeline discovery: {e}", exc_info=True)
        AVAILABLE_PIPELINES = {}

# Worker modülü yüklendiğinde bu fonksiyonu hemen çalıştır.
discover_and_register_pipelines()
os.makedirs(REPORTS_BASE_DIR, exist_ok=True)

@contextmanager
def get_db():
    """Veritabanı session'ı için bir context manager."""
    yield from get_db_session()

def _prepare_and_log_initial_state(task_id: str, user_config: dict) -> dict:
    """Deney için gerekli ID'leri, dizinleri oluşturur ve veritabanına ilk kaydı atar."""
    pipeline_name = user_config.get("pipeline_name")
    if not pipeline_name:
        raise ValueError("'pipeline_name' must be provided in the configuration.")

    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_id = f"{pipeline_name}_{run_timestamp}_{task_id[:8]}"
    
    # Sistemsel ve pipeline'a özel tüm bilgileri içeren tam konfigürasyon
    full_config = {
        **user_config,
        'experiment_id': experiment_id, 
        'task_id': task_id,
        'experiment_dir': os.path.join(REPORTS_BASE_DIR, pipeline_name, experiment_id),
        'start_time': datetime.now().isoformat(),
    }
    
    os.makedirs(full_config['experiment_dir'], exist_ok=True)

    with get_db() as db:
        new_experiment = Experiment(
            id=experiment_id, 
            task_id=task_id, 
            pipeline_name=pipeline_name, 
            status="STARTED", 
            config=full_config,
            batch_id=user_config.get('batch_id'), 
            batch_name=user_config.get('batch_name')
        )
        db.add(new_experiment)
        db.commit()
        logging.info(f"Experiment {experiment_id} logged to DB with status STARTED.")
    
    return full_config

def _update_experiment_on_completion(experiment_id: str, results: dict, model_path: Optional[str]):
    """Deney başarıyla tamamlandığında veritabanını günceller."""
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
    """Deney başarısız olduğunda veritabanını günceller."""
    tb_str = traceback.format_exc()
    error_message = str(e)
    error_code = "PIPELINE_EXECUTION_ERROR"
    if isinstance(e, (ValueError, TypeError)):
        error_code = "PIPELINE_VALUE_ERROR"
    elif isinstance(e, FileNotFoundError):
        error_code = "PIPELINE_FILE_NOT_FOUND"
    
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
def start_training_pipeline(self, user_config: dict):
    """
    API'den gelen ana Celery görevi. Bir pipeline'ı uçtan uca çalıştırır.
    """
    full_config = None
    try:
        # 1. Konfigürasyonları hazırla ve veritabanına ilk kaydı at.
        full_config = _prepare_and_log_initial_state(self.request.id, user_config)
        experiment_id = full_config['experiment_id']
        pipeline_name = full_config['pipeline_name']

        # 2. Doğru Pipeline sınıfını bul ve örneğini oluştur.
        PipelineClass = AVAILABLE_PIPELINES.get(pipeline_name)
        if not PipelineClass:
            raise ValueError(f"Pipeline '{pipeline_name}' is not registered or could not be found.")
        
        pipeline_instance = PipelineClass(full_config)
        
        # 3. Pipeline'ı çalıştır.
        redis_callback = RedisProgressCallback(task_id=self.request.id)
        results = pipeline_instance.run(callbacks=[redis_callback])

        # 4. Model varsa kaydet.
        model_path = None
        if hasattr(pipeline_instance, 'learner') and pipeline_instance.learner:
            model_filename = "best_model.json"
            model_path = os.path.join(full_config['experiment_dir'], model_filename)
            pipeline_instance.learner.save_model(model_path)
            logging.info(f"Model for experiment {experiment_id} saved to {model_path}")

        # 5. Başarılı sonuçları veritabanına yaz.
        _update_experiment_on_completion(experiment_id, results, model_path)
        
        return {"experiment_id": experiment_id, "status": "SUCCESS", "model_path": model_path}
        
    except Exception as e:
        # Hata durumunda, veritabanını güncelle ve hatayı yeniden fırlat ki Celery görevi "FAILURE" olarak işaretlensin.
        if full_config and 'experiment_id' in full_config:
            _update_experiment_on_failure(full_config['experiment_id'], e)
        else:
            # Bu durum, _prepare_and_log_initial_state içinde hata olursa gerçekleşir.
            logging.error(f"CRITICAL: Could not log failure to DB for task {self.request.id} as experiment_id was not generated. Original error: {e}", exc_info=True)
        raise e