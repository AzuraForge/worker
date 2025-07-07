import logging
import os
import traceback
import json
from datetime import datetime
from importlib.metadata import entry_points
from importlib import resources
from contextlib import contextmanager
from typing import Optional, Dict, Any, Tuple, List
import pandas as pd
import numpy as np
import redis
from functools import lru_cache

from ..celery_app import celery_app
from ..database import get_db_session
from azuraforge_dbmodels import Experiment
from ..callbacks import RedisProgressCallback
from azuraforge_learner import TimeSeriesPipeline, Learner, BasePipeline # BasePipeline import edildi

REDIS_PIPELINES_KEY = "azuraforge:pipelines_catalog"
AVAILABLE_PIPELINES: Dict[str, Any] = {}
REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "/app/reports"))

@lru_cache(maxsize=16)
def get_shared_data(pipeline_name: str, full_config_json: str) -> pd.DataFrame:
    from azuraforge_learner.caching import get_cache_filepath, load_from_cache, save_to_cache
    pipeline_class = AVAILABLE_PIPELINES.get(pipeline_name)
    if not pipeline_class: raise ValueError(f"Paylaşımlı veri yüklenirken pipeline '{pipeline_name}' bulunamadı.")
    
    # Geçici pipeline örneği oluştururken, tam konfigürasyonu aktarın.
    full_config = json.loads(full_config_json)
    
    # Eğer pipeline'ın bir get_config_model'ı varsa ve Pydantic ile doğrulama yapıyorsa
    # burada oluşabilecek hataları yakalamak için try-except ekleyebiliriz.
    try:
        temp_pipeline_instance: BasePipeline = pipeline_class(full_config)
    except Exception as e:
        logging.error(f"Error instantiating pipeline '{pipeline_name}' for shared data loading: {e}", exc_info=True)
        raise ValueError(f"Pipeline '{pipeline_name}' could not be initialized with provided config.") from e

    caching_params = temp_pipeline_instance.get_caching_params()
    cache_dir = os.getenv("CACHE_DIR", ".cache")
    cache_filepath = get_cache_filepath(cache_dir, pipeline_name, caching_params)
    system_config = temp_pipeline_instance.config.get("system", {}); 
    cache_max_age = system_config.get("cache_max_age_hours", 24)
    
    # Önbellek etkinse ve geçerliyse cache'ten yükle
    if system_config.get("caching_enabled", False):
        cached_data = load_from_cache(cache_filepath, cache_max_age)
        if cached_data is not None: 
            logging.info(f"Paylaşımlı önbellek için veri diskten yüklendi: {cache_filepath}")
            return cached_data

    logging.info(f"Paylaşımlı önbellek için veri kaynaktan indiriliyor. Parametreler: {caching_params}")
    source_data = temp_pipeline_instance._load_data_from_source()
    
    # Önbelleğe kaydetme (sadece pandas DataFrame ise)
    if system_config.get("caching_enabled", False) and isinstance(source_data, pd.DataFrame) and not source_data.empty: 
        save_to_cache(source_data, cache_filepath)
        
    return source_data

def discover_and_register_pipelines():
    global AVAILABLE_PIPELINES; logging.info("Worker: Discovering and registering pipelines via entry_points...")
    try:
        pipeline_eps = entry_points(group='azuraforge.pipelines')
        config_eps = entry_points(group='azuraforge.configs') # config entry_points'i de alıyoruz
        
        pipeline_class_map = {ep.name: ep.load() for ep in pipeline_eps}
        config_func_map = {ep.name: ep.load() for ep in config_eps}
        
        catalog_to_register = {}
        for name, p_class in pipeline_class_map.items():
            # Varsayılan konfigürasyonu yükle
            default_config = {}
            if name in config_func_map:
                default_config = config_func_map[name]()
            
            # Form şemasını yükle
            form_schema = {}
            try:
                # Modül yolunu doğru şekilde bul
                # 'azuraforge_cifar10.pipeline:Cifar10Pipeline' -> 'azuraforge_cifar10'
                package_name = p_class.__module__.split('.')[0] 
                with resources.open_text(package_name, "form_schema.json") as f: 
                    form_schema = json.load(f)
            except Exception as e: 
                logging.warning(f"Worker: form_schema.json could not be loaded for '{name}': {e}")
            
            catalog_to_register[name] = json.dumps({
                "id": name, 
                "default_config": default_config, 
                "form_schema": form_schema
            })
            
        AVAILABLE_PIPELINES = pipeline_class_map
        if catalog_to_register: 
            r = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
            r.delete(REDIS_PIPELINES_KEY)
            r.hset(REDIS_PIPELINES_KEY, mapping=catalog_to_register)
            logging.info(f"Worker: {len(catalog_to_register)} pipelines registered.")
    except Exception as e: 
        logging.error(f"Worker: CRITICAL ERROR during pipeline discovery: {e}", exc_info=True)
        AVAILABLE_PIPELINES.clear()

discover_and_register_pipelines()
os.makedirs(REPORTS_BASE_DIR, exist_ok=True)

@contextmanager
def get_db(): yield from get_db_session()

def _prepare_and_log_initial_state(task_id: str, user_config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    pipeline_name = user_config.get("pipeline_name")
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_id = f"{pipeline_name}_{run_timestamp}_{task_id[:8]}"
    full_config = {**user_config, 
                   'experiment_id': experiment_id, 
                   'task_id': task_id, 
                   'experiment_dir': os.path.join(REPORTS_BASE_DIR, pipeline_name, experiment_id), 
                   'start_time': datetime.now().isoformat()}
    os.makedirs(full_config['experiment_dir'], exist_ok=True)
    
    with get_db() as db: 
        db.add(Experiment(id=experiment_id, task_id=task_id, pipeline_name=pipeline_name, status="STARTED", config=full_config, batch_id=user_config.get('batch_id'), batch_name=user_config.get('batch_name')))
        db.commit()
    logging.info(f"Experiment {experiment_id} logged to DB with status STARTED.")
    return experiment_id, full_config

def _update_experiment_on_completion(experiment_id, results, model_path):
    with get_db() as db: 
        exp = db.query(Experiment).filter_by(id=experiment_id).first()
        if exp:
            exp.status = "SUCCESS"
            exp.results = results
            exp.model_path = model_path
            exp.completed_at = datetime.now(datetime.utcnow().tzinfo)
            db.commit()
            logging.info(f"Experiment {experiment_id} updated to SUCCESS.")
        else:
            logging.warning(f"Experiment {experiment_id} not found for completion update.")

def _update_experiment_on_failure(experiment_id, error):
    tb_str = traceback.format_exc()
    error_message = str(error)
    error_code = getattr(error, 'error_code', "PIPELINE_EXECUTION_ERROR") # Özel hata kodunu al
    
    with get_db() as db: 
        exp = db.query(Experiment).filter_by(id=experiment_id).first()
        if exp:
            exp.status = "FAILURE"
            exp.error = {"error_code": error_code, "message": error_message, "traceback": tb_str}
            exp.failed_at = datetime.now(datetime.utcnow().tzinfo)
            db.commit()
            logging.info(f"Experiment {experiment_id} updated to FAILURE.")
        else:
            logging.error(f"CRITICAL: Experiment {experiment_id} not found for failure update. Error: {error_message}", exc_info=True)


@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, user_config: Dict[str, Any]):
    experiment_id = None
    try:
        experiment_id, full_config = _prepare_and_log_initial_state(self.request.id, user_config)
        pipeline_name = full_config['pipeline_name']
        PipelineClass = AVAILABLE_PIPELINES.get(pipeline_name)
        if not PipelineClass:
            raise ValueError(f"Pipeline '{pipeline_name}' is not registered.")
        
        # Pipeline örneğini oluştururken tam konfigürasyonu gönder
        pipeline_instance: BasePipeline = PipelineClass(full_config)
        
        run_kwargs = {}
        # Eğer zaman serisi pipeline ise, raw_data'yı shared cache'ten yükle
        if isinstance(pipeline_instance, TimeSeriesPipeline):
            run_kwargs['raw_data'] = get_shared_data(pipeline_name, json.dumps(full_config, sort_keys=True))
            
        results = pipeline_instance.run(callbacks=[RedisProgressCallback(task_id=self.request.id)], **run_kwargs)
        
        # Modeli kaydet
        model_path = os.path.join(full_config['experiment_dir'], "best_model.json")
        if hasattr(pipeline_instance.learner, 'save_model'):
            pipeline_instance.learner.save_model(model_path)
        else:
            logging.warning(f"Pipeline '{pipeline_name}' learner does not have save_model method.")
            model_path = None # Model kaydedilemediyse path'i null yap

        _update_experiment_on_completion(experiment_id, results, model_path)
        return {"experiment_id": experiment_id, "status": "SUCCESS", "model_path": model_path}
    except Exception as e:
        if experiment_id: _update_experiment_on_failure(experiment_id, e)
        else: logging.error(f"CRITICAL: Could not log failure for task {self.request.id}. Error: {e}", exc_info=True)
        raise e


@celery_app.task(name="predict_from_model_task")
def predict_from_model_task(experiment_id: str, request_data: Optional[List[Dict[str, Any]]] = None, prediction_steps: Optional[int] = 1) -> Dict[str, Any]:
    with get_db() as db:
        try:
            exp = db.query(Experiment).filter(Experiment.id == experiment_id).first()
            if not exp: raise ValueError(f"Experiment with ID '{experiment_id}' not found.")
            if not exp.model_path or not os.path.exists(exp.model_path): raise FileNotFoundError(f"No model artifact for experiment '{experiment_id}'.")

            PipelineClass = AVAILABLE_PIPELINES.get(exp.pipeline_name)
            if not PipelineClass: raise ValueError(f"Pipeline '{exp.pipeline_name}' is not registered.")
            
            # Tahmin için pipeline örneğini tam konfigürasyon ile oluştur
            pipeline_instance: BasePipeline = PipelineClass(exp.config)
            
            is_timeseries = isinstance(pipeline_instance, TimeSeriesPipeline)

            # Modeli yüklemeden önce scaler'ları eğit
            # Eğer zaman serisi ise, tarihsel veriyi al ve scaler'ları eğit
            if is_timeseries:
                full_config_json = json.dumps(exp.config, sort_keys=True)
                historical_data_df = get_shared_data(exp.pipeline_name, full_config_json)
                
                # Scaler'ları eğit
                pipeline_instance._fit_scalers(historical_data_df)

                # Tahmin için kullanılacak son N veriyi al
                seq_len = exp.config.get('model_params', {}).get('sequence_length', 60)
                # İstemciden gelen `request_data` varsa, bunu kullan
                if request_data:
                    # request_data'yı DataFrame'e çevir
                    input_df = pd.DataFrame(request_data)
                    # Eğer zaman sütunu varsa onu index yap
                    if 'time' in input_df.columns:
                        input_df['time'] = pd.to_datetime(input_df['time'])
                        input_df.set_index('time', inplace=True)
                    # Önemli: Input data sadece modelin feature_cols'larını içermelidir
                    # ve scaler'a uygun formda olmalıdır.
                    # Ancak şu anki tasarımda PredictionModal request.data göndermiyor.
                    # Bu durumda, her zaman `historical_data_df`'in son `seq_len`'ini kullanırız.
                    current_prediction_input_df = historical_data_df.tail(seq_len)
                else:
                    # Request data yoksa, genel tarihsel verinin sonunu kullan
                    if len(historical_data_df) < seq_len:
                        raise ValueError(f"Not enough historical data ({len(historical_data_df)}) for sequence of {seq_len}.")
                    current_prediction_input_df = historical_data_df.tail(seq_len)
            else:
                # Zaman serisi olmayan modeller için varsayılan model input şekli
                # (ör: görüntü için (N, C, H, W))
                model_input_shape = (1, 3, 32, 32) 
            
            # Modeli yükle
            # model_input_shape TimeSeriesPipeline dışındaki diğer pipeline'lar için gerekli.
            # TimeSeriesPipeline için ise bu değer _create_model içinde zaten input_shape olarak kullanılıyor.
            model_input_shape_for_create = exp.config.get('model_params', {}).get('input_shape', None)
            if not model_input_shape_for_create and is_timeseries:
                 # X_train'in shape'ini tahmin etmeye çalış (batch_size, seq_len, num_features)
                 num_features = len(pipeline_instance.feature_cols) if pipeline_instance.feature_cols else 1
                 model_input_shape_for_create = (1, seq_len, num_features)
            elif not model_input_shape_for_create and not is_timeseries:
                 # Görüntü sınıflandırma gibi durumlar için varsayılan
                 model_input_shape_for_create = (1, 3, 32, 32) # CIFAR-10 için örnek

            model = pipeline_instance._create_model(model_input_shape_for_create)
            learner = Learner(model=model)
            learner.load_model(exp.model_path)

            if is_timeseries:
                # Çok adımlı tahmin yap
                forecasted_df = pipeline_instance.forecast(
                    initial_df=current_prediction_input_df, 
                    learner=learner, 
                    num_steps=prediction_steps
                )
                
                # İlk tahmin edilen değer (PredictionModal'daki .predictionValue için)
                prediction_value = float(forecasted_df.iloc[0][forecasted_df.columns[0]]) if not forecasted_df.empty else None
                
                # Geçmiş veriyi string anahtarlı sözlüğe dönüştür
                actual_history_series = historical_data_df[pipeline_instance.target_col].tail(seq_len)
                actual_history_series.index = pd.to_datetime(actual_history_series.index).strftime('%Y-%m-%dT%H:%M:%S')
                string_keyed_actual_history = actual_history_series.to_dict()

                # Tahmin edilen seriyi string anahtarlı sözlüğe dönüştür
                forecasted_series_string_keyed = {}
                if not forecasted_df.empty:
                    # forecasted_df'in index'ini datetime nesnesine çevirip string yap
                    forecasted_df.index = pd.to_datetime(forecasted_df.index).strftime('%Y-%m-%dT%H:%M:%S')
                    forecasted_series_string_keyed = forecasted_df[forecasted_df.columns[0]].to_dict() # İlk sütunu al

                return {
                    "prediction": prediction_value, 
                    "experiment_id": experiment_id,
                    "target_col": pipeline_instance.target_col,
                    "actual_history": string_keyed_actual_history,
                    "forecasted_series": forecasted_series_string_keyed
                }
            else:
                # Zaman serisi olmayan modeller için tahmin (Örn: Sınıflandırma, Üretim)
                # Bu kısım henüz tam olarak implemente edilmediği için hata fırlatabiliriz.
                # Gelecekte, request_data kullanılarak uygun formatta tahmin yapılacaktır.
                raise NotImplementedError("Prediction for non-time-series models is not yet fully implemented for general purpose.")
            
        except Exception as e:
            logging.error(f"Prediction task failed for experiment {experiment_id}: {e}", exc_info=True)
            # Hata kodu ekleyerek frontend'in daha anlamlı mesaj göstermesini sağla
            raise ValueError(f"PREDICTION_TASK_FAILED: {str(e)}")