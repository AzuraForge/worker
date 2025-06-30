# worker/src/azuraforge_worker/tasks/training_tasks.py

import logging
import os
import json
from datetime import datetime
from importlib.metadata import entry_points
import traceback

from ..celery_app import celery_app
from ..callbacks import RedisProgressCallback

def discover_pipelines():
    logging.info("Worker: Discovering installed AzuraForge pipeline plugins and configurations...")
    discovered = {}
    try:
        pipeline_entry_points = entry_points(group='azuraforge.pipelines')
        for ep in pipeline_entry_points:
            logging.info(f"Worker: Found pipeline plugin: '{ep.name}' -> points to '{ep.value}'")
            discovered[ep.name] = {'pipeline_class': ep.load()} 
        
        config_entry_points = entry_points(group='azuraforge.configs')
        for ep in config_entry_points:
            logging.info(f"Worker: Found config entry point: '{ep.name}' -> points to '{ep.value}'")
            if ep.name in discovered:
                discovered[ep.name]['get_config_func'] = ep.load()
            else:
                logging.warning(f"Worker: Found config for '{ep.name}' but no corresponding pipeline. Skipping config.")
    except Exception as e:
        logging.error(f"Worker: Error discovering pipelines or configs: {e}", exc_info=True)
    
    for p_id, p_info in discovered.items():
        logging.info(f"Worker: Discovered pipeline '{p_id}' (Config available: {'get_config_func' in p_info})")
    return discovered

AVAILABLE_PIPELINES_AND_CONFIGS = discover_pipelines()
if not AVAILABLE_PIPELINES_AND_CONFIGS:
    logging.warning("Worker: No AzuraForge pipelines found!")

REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "/app/reports"))
os.makedirs(REPORTS_BASE_DIR, exist_ok=True)

@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, config: dict):
    task_id = self.request.id
    pipeline_name = config.get("pipeline_name", "unknown_pipeline")
    experiment_id = "" # Hata durumunda bile ID'nin var olması için başlat

    try:
        if not pipeline_name or pipeline_name not in AVAILABLE_PIPELINES_AND_CONFIGS:
            raise ValueError(f"Pipeline '{pipeline_name}' not found or installed.")

        PipelineClass = AVAILABLE_PIPELINES_AND_CONFIGS[pipeline_name]['pipeline_class']

        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        experiment_id = f"{pipeline_name}_{run_timestamp}_{task_id}" 
        
        experiment_dir = os.path.join(REPORTS_BASE_DIR, pipeline_name, experiment_id)
        os.makedirs(experiment_dir, exist_ok=True)
        
        config['experiment_id'] = experiment_id
        config['task_id'] = task_id
        config['experiment_dir'] = experiment_dir
        config['start_time'] = datetime.now().isoformat()

        logging.info(f"Worker: Instantiating pipeline '{PipelineClass.__name__}' for experiment {experiment_id}")
        
        initial_report_data = {"task_id": task_id, "experiment_id": experiment_id, "status": "STARTED", "config": config, "results": {}}
        with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
            json.dump(initial_report_data, f, indent=4, default=str)

        pipeline_instance = PipelineClass(config)
        redis_callback = RedisProgressCallback(task_id=task_id)
        
        results = pipeline_instance.run(callbacks=[redis_callback])

        final_report_data = {"task_id": task_id, "experiment_id": experiment_id, "status": "SUCCESS", "config": config, "results": results, "completed_at": datetime.now().isoformat()}
        with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
            json.dump(final_report_data, f, indent=4, default=str)
            
        logging.info(f"Worker: Task {task_id} completed successfully.")
        return final_report_data

    except Exception as e:
        tb_str = traceback.format_exc()
        logging.error(f"PIPELINE CRITICAL FAILURE in task {task_id} (experiment: {experiment_id}): {e}")
        logging.error(f"FULL TRACEBACK:\n{tb_str}")
        
        # Hata durumunda bile results.json'ı güncelle
        error_report_data = {
            "task_id": task_id, "experiment_id": experiment_id, "status": "FAILURE", 
            "config": config, "error": {"message": str(e), "traceback": tb_str}, 
            "failed_at": datetime.now().isoformat()
        }
        if experiment_id: # Eğer experiment_id oluşturulduysa dosyayı yaz
            error_report_path = os.path.join(REPORTS_BASE_DIR, pipeline_name, experiment_id, "results.json")
            os.makedirs(os.path.dirname(error_report_path), exist_ok=True)
            with open(error_report_path, 'w') as f:
                json.dump(error_report_data, f, indent=4)
        
        # Celery'nin hatayı düzgün işlemesi için yeniden fırlat
        raise e