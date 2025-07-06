# worker/src/azuraforge_worker/tasks/training_tasks.py
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
from azuraforge_learner import TimeSeriesPipeline, Learner

REDIS_PIPELINES_KEY = "azuraforge:pipelines_catalog"
AVAILABLE_PIPELINES: Dict[str, Any] = {}
REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "/app/reports"))

@lru_cache(maxsize=16)
def get_shared_data(pipeline_name: str, full_config_json: str) -> pd.DataFrame:
    from azuraforge_learner.caching import get_cache_filepath, load_from_cache, save_to_cache
    pipeline_class = AVAILABLE_PIPELINES.get(pipeline_name)
    if not pipeline_class: raise ValueError(f"Paylaşımlı veri yüklenirken pipeline '{pipeline_name}' bulunamadı.")
    full_config = json.loads(full_config_json); temp_pipeline_instance = pipeline_class(full_config)
    caching_params = temp_pipeline_instance.get_caching_params(); cache_dir = os.getenv("CACHE_DIR", ".cache")
    cache_filepath = get_cache_filepath(cache_dir, pipeline_name, caching_params)
    system_config = temp_pipeline_instance.config.get("system", {}); cache_max_age = system_config.get("cache_max_age_hours", 24)
    cached_data = load_from_cache(cache_filepath, cache_max_age)
    if cached_data is not None: logging.info(f"Paylaşımlı önbellek için veri diskten yüklendi: {cache_filepath}"); return cached_data
    logging.info(f"Paylaşımlı önbellek için veri kaynaktan indiriliyor. Parametreler: {caching_params}")
    source_data = temp_pipeline_instance._load_data_from_source()
    if isinstance(source_data, pd.DataFrame) and not source_data.empty: save_to_cache(source_data, cache_filepath)
    return source_data

def discover_and_register_pipelines():
    global AVAILABLE_PIPELINES; logging.info("Worker: Discovering and registering pipelines via entry_points...")
    try:
        pipeline_eps, config_eps = entry_points(group='azuraforge.pipelines'), entry_points(group='azuraforge.configs')
        pipeline_class_map, config_func_map = {ep.name: ep.load() for ep in pipeline_eps}, {ep.name: ep.load() for ep in config_eps}
        catalog_to_register = {}
        for name, p_class in pipeline_class_map.items():
            default_config = config_func_map[name]() if name in config_func_map else {}
            try:
                with resources.open_text(p_class.__module__.split('.')[0], "form_schema.json") as f: form_schema = json.load(f)
            except Exception: form_schema = {}
            catalog_to_register[name] = json.dumps({"id": name, "default_config": default_config, "form_schema": form_schema})
        AVAILABLE_PIPELINES = pipeline_class_map
        if catalog_to_register: r = redis.from_url(os.environ.get("REDIS_URL")); r.delete(REDIS_PIPELINES_KEY); r.hset(REDIS_PIPELINES_KEY, mapping=catalog_to_register); logging.info(f"Worker: {len(catalog_to_register)} pipelines registered.")
    except Exception as e: logging.error(f"Worker: CRITICAL ERROR during pipeline discovery: {e}", exc_info=True); AVAILABLE_PIPELINES.clear()

discover_and_register_pipelines()
os.makedirs(REPORTS_BASE_DIR, exist_ok=True)
@contextmanager
def get_db(): yield from get_db_session()
def _prepare_and_log_initial_state(task_id: str, user_config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    pipeline_name = user_config.get("pipeline_name"); run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S"); experiment_id = f"{pipeline_name}_{run_timestamp}_{task_id[:8]}"; full_config = {**user_config, 'experiment_id': experiment_id, 'task_id': task_id, 'experiment_dir': os.path.join(REPORTS_BASE_DIR, pipeline_name, experiment_id), 'start_time': datetime.now().isoformat()}; os.makedirs(full_config['experiment_dir'], exist_ok=True)
    with get_db() as db: db.add(Experiment(id=experiment_id, task_id=task_id, pipeline_name=pipeline_name, status="STARTED", config=full_config, batch_id=user_config.get('batch_id'), batch_name=user_config.get('batch_name'))); db.commit()
    logging.info(f"Experiment {experiment_id} logged to DB with status STARTED."); return experiment_id, full_config
def _update_experiment_on_completion(experiment_id, results, model_path):
    with get_db() as db: exp = db.query(Experiment).filter_by(id=experiment_id).first(); exp.status, exp.results, exp.model_path, exp.completed_at = "SUCCESS", results, model_path, datetime.now(datetime.utcnow().tzinfo); db.commit(); logging.info(f"Experiment {experiment_id} updated to SUCCESS.")
def _update_experiment_on_failure(experiment_id, error):
    tb_str, error_message, error_code = traceback.format_exc(), str(error), "PIPELINE_EXECUTION_ERROR"
    with get_db() as db: exp = db.query(Experiment).filter_by(id=experiment_id).first(); exp.status, exp.error, exp.failed_at = "FAILURE", {"error_code": error_code, "message": error_message, "traceback": tb_str}, datetime.now(datetime.utcnow().tzinfo); db.commit(); logging.info(f"Experiment {experiment_id} updated to FAILURE.")

@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, user_config: Dict[str, Any]):
    experiment_id = None
    try:
        experiment_id, full_config = _prepare_and_log_initial_state(self.request.id, user_config); pipeline_name = full_config['pipeline_name']; PipelineClass = AVAILABLE_PIPELINES.get(pipeline_name); pipeline_instance = PipelineClass(full_config); run_kwargs = {};
        if isinstance(pipeline_instance, TimeSeriesPipeline): run_kwargs['raw_data'] = get_shared_data(pipeline_name, json.dumps(full_config, sort_keys=True))
        results = pipeline_instance.run(callbacks=[RedisProgressCallback(task_id=self.request.id)], **run_kwargs); model_path = os.path.join(full_config['experiment_dir'], "best_model.json"); pipeline_instance.learner.save_model(model_path); _update_experiment_on_completion(experiment_id, results, model_path); return {"experiment_id": experiment_id, "status": "SUCCESS", "model_path": model_path}
    except Exception as e:
        if experiment_id: _update_experiment_on_failure(experiment_id, e)
        else: logging.error(f"CRITICAL: Could not log failure for task {self.request.id}. Error: {e}", exc_info=True)
        raise e

@celery_app.task(name="predict_from_model_task")
def predict_from_model_task(experiment_id: str, request_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    with get_db() as db:
        try:
            exp = db.query(Experiment).filter(Experiment.id == experiment_id).first()
            if not exp: raise ValueError(f"Experiment with ID '{experiment_id}' not found.")
            if not exp.model_path or not os.path.exists(exp.model_path): raise FileNotFoundError(f"No model artifact for experiment '{experiment_id}'.")

            PipelineClass = AVAILABLE_PIPELINES.get(exp.pipeline_name)
            if not PipelineClass: raise ValueError(f"Pipeline '{exp.pipeline_name}' is not registered.")
            
            pipeline_instance = PipelineClass(exp.config)
            is_timeseries = isinstance(pipeline_instance, TimeSeriesPipeline)

            if is_timeseries:
                full_config_json = json.dumps(exp.config, sort_keys=True)
                historical_data = get_shared_data(exp.pipeline_name, full_config_json)
                pipeline_instance._fit_scalers(historical_data)

            num_features = len(exp.results.get('feature_cols', [])) if exp.results else 1
            seq_len = exp.config.get('model_params', {}).get('sequence_length', 60)
            model_input_shape = (1, seq_len, num_features) if is_timeseries else (1, 3, 32, 32)
            model = pipeline_instance._create_model(model_input_shape)
            
            learner = Learner(model=model)
            learner.load_model(exp.model_path)

            request_df = None
            if request_data:
                request_df = pd.DataFrame(request_data)
            elif is_timeseries:
                if 'historical_data' not in locals():
                    full_config_json = json.dumps(exp.config, sort_keys=True)
                    historical_data = get_shared_data(exp.pipeline_name, full_config_json)
                if len(historical_data) < seq_len: raise ValueError(f"Not enough historical data ({len(historical_data)}) for sequence of {seq_len}.")
                request_df = historical_data.tail(seq_len)
            else:
                raise ValueError("Prediction data is required for non-time-series models.")
            
            if not hasattr(pipeline_instance, 'prepare_data_for_prediction'): raise NotImplementedError("Pipeline does not implement 'prepare_data_for_prediction'.")
            
            prepared_data = pipeline_instance.prepare_data_for_prediction(request_df)
            scaled_prediction = learner.predict(prepared_data)
            
            if not hasattr(pipeline_instance, 'target_scaler'): raise RuntimeError("Pipeline's target_scaler is not available.")
            
            unscaled_prediction = pipeline_instance.target_scaler.inverse_transform(scaled_prediction)
            
            final_prediction = np.expm1(unscaled_prediction) if exp.config.get("feature_engineering", {}).get("target_col_transform") == 'log' else unscaled_prediction
            
            prediction_value = float(final_prediction.flatten()[0])
            
            # === DEĞİŞİKLİK BURADA: Sonuca geçmiş veriyi de ekliyoruz ===
            history_for_chart = request_df[pipeline_instance.target_col].to_dict()

            return {
                "prediction": prediction_value, 
                "experiment_id": experiment_id,
                "target_col": pipeline_instance.target_col,
                "history": history_for_chart
            }
            
        except Exception as e:
            logging.error(f"Prediction task failed for experiment {experiment_id}: {e}", exc_info=True)
            raise