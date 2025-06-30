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
    # ... (kod aynı)
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
    pipeline_name = config.get("pipeline_name")
    
    if not pipeline_name or pipeline_name not in AVAILABLE_PIPELINES_AND_CONFIGS:
        raise ValueError(f"Pipeline '{pipeline_name}' not found or installed.")

    PipelineClass = AVAILABLE_PIPELINES_AND_CONFIGS[pipeline_name]['pipeline_class']

    task_id = self.request.id
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

    try:
        # Pipeline'ı konfigürasyon ile başlat
        pipeline_instance = PipelineClass(config)
        
        # Raporlama için callback'i oluştur
        redis_callback = RedisProgressCallback(task_id=task_id)
        
        # Pipeline'ın standart run metodunu çağır ve callback'i parametre olarak geçir.
        # Bu, BasePipeline'de henüz tam desteklenmiyor, bu yüzden eklenti bunu kendi yönetmeli.
        # Bu nedenle, eklentinin `run` metodunu `callbacks` alacak şekilde güncelledik.
        results = pipeline_instance.run(callbacks=[redis_callback])

        final_report_data = {"task_id": task_id, "experiment_id": experiment_id, "status": "SUCCESS", "config": config, "results": results, "completed_at": datetime.now().isoformat()}
        with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
            json.dump(final_report_data, f, indent=4, default=str)
            
        logging.info(f"Worker: Task {task_id} completed successfully.")
        return final_report_data

    except Exception as e:
        error_traceback = traceback.format_exc()
        error_message = f"Pipeline execution failed for {pipeline_name}: {e}\n{error_traceback}"
        logging.error(error_message)
        
        self.update_state(state='FAILURE', meta={'error_message': str(e), 'traceback': error_traceback})
        
        error_report_data = {"task_id": task_id, "experiment_id": experiment_id, "status": "FAILURE", "config": config, "error": error_message, "failed_at": datetime.now().isoformat()}
        with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
            json.dump(error_report_data, f, indent=4, default=str)
            
        raise e