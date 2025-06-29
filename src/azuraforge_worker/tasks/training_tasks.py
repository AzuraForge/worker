import logging
import os
import json
from datetime import datetime
from importlib.metadata import entry_points
from celery import current_task # Görevin durumunu güncellemek için
import time # Simülasyon için
import traceback # Hata detaylarını yakalamak için

from ..celery_app import celery_app
# applications reposundan pipeline'ı import etmek için bu kodun olduğu yerde değil,
# pip tarafından paket olarak kurulmuş azuraforge_stockapp'tan import edilecek.

# --- Eklenti Keşfi ---
def discover_pipelines():
    """
    Sisteme kurulmuş tüm AzuraForge pipeline'larını ve varsa varsayılan konfigürasyon
    fonksiyonlarını keşfeder.
    Dönüş değeri: { 'pipeline_id': { 'pipeline_class': Class, 'get_config_func': Function | None } }
    """
    logging.info("Worker: Discovering installed AzuraForge pipeline plugins and configurations...")
    discovered = {}
    try:
        # Pipeline sınıflarını keşfet
        pipeline_entry_points = entry_points(group='azuraforge.pipelines')
        for ep in pipeline_entry_points:
            logging.info(f"Worker: Found pipeline plugin: '{ep.name}' -> points to '{ep.value}'")
            discovered[ep.name] = {'pipeline_class': ep.load()} 
        
        # Konfigürasyon fonksiyonlarını keşfet (aynı isimle eşleşmeli)
        config_entry_points = entry_points(group='azuraforge.configs')
        for ep in config_entry_points:
            logging.info(f"Worker: Found config entry point: '{ep.name}' -> points to '{ep.value}'")
            if ep.name in discovered:
                discovered[ep.name]['get_config_func'] = ep.load()
            else:
                logging.warning(f"Worker: Found config for '{ep.name}' but no corresponding pipeline. Skipping config.")
                
    except Exception as e:
        logging.error(f"Worker: Error discovering pipelines or configs: {e}", exc_info=True)
    
    # Debug için keşfedilenleri logla
    for p_id, p_info in discovered.items():
        logging.info(f"Worker: Discovered pipeline '{p_id}' (Config available: {'get_config_func' in p_info})")

    return discovered

AVAILABLE_PIPELINES_AND_CONFIGS = discover_pipelines() # Değiştirildi
if not AVAILABLE_PIPELINES_AND_CONFIGS: # Değiştirildi
    logging.warning("Worker: No AzuraForge pipelines found! Please install a pipeline plugin, e.g., 'azuraforge-app-stock-predictor'.")

REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "/app/reports"))
os.makedirs(REPORTS_BASE_DIR, exist_ok=True) # Dizinin var olduğundan emin ol

@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, config: dict):
    pipeline_name = config.get("pipeline_name")
    
    # Değiştirildi: AVAILABLE_PIPELINES_AND_CONFIGS kullan
    if not pipeline_name or pipeline_name not in AVAILABLE_PIPELINES_AND_CONFIGS:
        raise ValueError(f"Pipeline '{pipeline_name}' not found or installed.")

    PipelineInfo = AVAILABLE_PIPELINES_AND_CONFIGS[pipeline_name]
    PipelineClass = PipelineInfo['pipeline_class']

    # --- Deney için benzersiz bir klasör ve ID oluştur ---
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_id = f"{pipeline_name}_{run_timestamp}_{self.request.id}" 
    
    pipeline_specific_report_dir = os.path.join(REPORTS_BASE_DIR, pipeline_name)
    os.makedirs(pipeline_specific_report_dir, exist_ok=True)
    experiment_dir = os.path.join(pipeline_specific_report_dir, experiment_id)
    os.makedirs(experiment_dir, exist_ok=True)
    
    config['experiment_id'] = experiment_id
    config['task_id'] = self.request.id
    config['experiment_dir'] = experiment_dir
    config['start_time'] = datetime.now().isoformat() # Yeni: Başlangıç zamanını ekle

    logging.info(f"Worker: Instantiating pipeline '{PipelineClass.__name__}' for experiment {experiment_id}")
    
    initial_report_data = {
        "task_id": self.request.id, "experiment_id": experiment_id, "status": "STARTED", "config": config, "results": {}
    }
    with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
        json.dump(initial_report_data, f, indent=4, default=str)

    try:
        # --- KRİTİK DÜZELTME: Pipeline'a Celery Task objesini iletiyoruz ---
        # Bu, pipeline'ın içindeki Learner'ın Celery state'i güncelleyebilmesini sağlar.
        pipeline_instance = PipelineClass(config, celery_task=self) # <- Yeni parametre
        results = pipeline_instance.run() 

        final_report_data = {
            "task_id": self.request.id, "experiment_id": experiment_id, "status": "SUCCESS", "config": config, "results": results, "completed_at": datetime.now().isoformat()
        }
        with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
            json.dump(final_report_data, f, indent=4, default=str)
            
        logging.info(f"Worker: Task {self.request.id} for pipeline '{pipeline_name}' completed successfully. Results in {experiment_dir}")
        return final_report_data

    except Exception as e:
        error_traceback = traceback.format_exc()
        error_message = f"Pipeline execution failed for {pipeline_name}: {e}\n{error_traceback}"
        logging.error(error_message)
        
        self.update_state(state='FAILURE', meta={'error_message': str(e), 'traceback': error_traceback})
        
        error_report_data = {
            "task_id": self.request.id, "experiment_id": experiment_id, "status": "FAILURE", "config": config, "error": error_message, "failed_at": datetime.now().isoformat()
        }
        with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
            json.dump(error_report_data, f, indent=4)
            
        raise e