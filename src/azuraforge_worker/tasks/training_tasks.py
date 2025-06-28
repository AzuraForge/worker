# ========== DOSYA: worker/src/azuraforge_worker/tasks/training_tasks.py ==========
import logging
import os
import json
from datetime import datetime
from importlib.metadata import entry_points
from celery import current_task # Görevin durumunu güncellemek için
import time # Simülasyon için
import traceback # Hata detaylarını yakalamak için

# Celery uygulamasını import et
from ..celery_app import celery_app

# --- Eklenti Keşfi ---
def discover_pipelines():
    """Sisteme kurulmuş tüm AzuraForge pipeline'larını keşfeder."""
    logging.info("Worker: Discovering installed AzuraForge pipeline plugins...")
    discovered = {}
    try:
        eps = entry_points(group='azuraforge.pipelines')
        for ep in eps:
            logging.info(f"Worker: Found plugin: '{ep.name}' -> points to '{ep.value}'")
            # Giriş noktasını yükleyip sözlükte sakla
            discovered[ep.name] = ep.load() 
    except Exception as e:
        logging.error(f"Worker: Error discovering pipelines: {e}", exc_info=True)
    return discovered

# Worker ilk başladığında tüm pipeline'ları yükle
AVAILABLE_PIPELINES = discover_pipelines()
if not AVAILABLE_PIPELINES:
    logging.warning("Worker: No AzuraForge pipelines found! Please install a pipeline plugin, e.g., 'azuraforge-app-stock-predictor'.")

# Worker'ın raporları kaydedeceği yeri belirle (Ortam değişkeninden veya varsayılan)
# Docker'da bu yol, bir volume ile host makineye bağlanacak.
REPORTS_BASE_DIR = os.path.abspath(os.getenv("REPORTS_DIR", "reports"))
os.makedirs(REPORTS_BASE_DIR, exist_ok=True) # Dizinin var olduğundan emin ol

@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, config: dict):
    """
    API'dan gelen konfigürasyona göre doğru pipeline eklentisini bulur ve çalıştırır.
    Görev ilerlemesini Celery state'i olarak günceller.
    """
    pipeline_name = config.get("pipeline_name")
    if not pipeline_name:
        raise ValueError("'pipeline_name' is required in the task config.")

    if pipeline_name not in AVAILABLE_PIPELINES:
        raise ValueError(f"Pipeline '{pipeline_name}' not found. Installed plugins: {list(AVAILABLE_PIPELINES.keys())}")

    # --- Deney için benzersiz bir klasör ve ID oluştur ---
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # request.id, Celery'nin bu göreve atadığı benzersiz ID'dir.
    experiment_id = f"{pipeline_name}_{run_timestamp}_{self.request.id}" 
    
    # Raporlar için alt klasör oluştur
    pipeline_specific_report_dir = os.path.join(REPORTS_BASE_DIR, pipeline_name)
    os.makedirs(pipeline_specific_report_dir, exist_ok=True)
    experiment_dir = os.path.join(pipeline_specific_report_dir, experiment_id)
    os.makedirs(experiment_dir, exist_ok=True)
    
    # Konfigürasyona deney bilgilerini ekle
    config['experiment_id'] = experiment_id
    config['task_id'] = self.request.id
    config['experiment_dir'] = experiment_dir # Pipeline'ın yolu bilmesi için

    PipelineClass = AVAILABLE_PIPELINES[pipeline_name]
    logging.info(f"Worker: Instantiating pipeline '{PipelineClass.__name__}' for experiment {experiment_id}")
    
    # Başlangıç durumunu kaydet
    initial_report_data = {
        "task_id": self.request.id,
        "experiment_id": experiment_id,
        "status": "STARTED",
        "config": config,
        "results": {}
    }
    with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
        json.dump(initial_report_data, f, indent=4, default=str)

    try:
        pipeline_instance = PipelineClass(config)
        
        # Pipeline'ın çalışma metodunu çağırıyoruz.
        # Pipeline'dan beklenen: eğitim sırasında progress güncellemesi yapması.
        # Pipeline'dan beklenen: nihai sonuçları bir sözlük olarak döndürmesi.
        results = pipeline_instance.run() 

        # --- Görev Başarıyla Tamamlandı ---
        final_report_data = {
            "task_id": self.request.id,
            "experiment_id": experiment_id,
            "status": "SUCCESS",
            "config": config,
            "results": results, # Pipeline'dan gelen nihai sonuçlar
            "completed_at": datetime.now().isoformat()
        }
        with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
            json.dump(final_report_data, f, indent=4, default=str)
            
        logging.info(f"Worker: Task {self.request.id} for pipeline '{pipeline_name}' completed successfully. Results in {experiment_dir}")
        return final_report_data

    except Exception as e:
        error_traceback = traceback.format_exc()
        error_message = f"Pipeline execution failed for {pipeline_name}: {e}\n{error_traceback}"
        logging.error(error_message)
        
        # Hata durumunu ve detayları Celery'ye güncelle
        self.update_state(state='FAILURE', meta={'error_message': str(e), 'traceback': error_traceback})
        
        # Hata durumunda da rapor oluştur
        error_report_data = {
            "task_id": self.request.id,
            "experiment_id": experiment_id,
            "status": "FAILURE",
            "config": config,
            "error": error_message,
            "failed_at": datetime.now().isoformat()
        }
        with open(os.path.join(experiment_dir, "results.json"), 'w') as f:
            json.dump(error_report_data, f, indent=4, default=str)
            
        raise e # Celery'nin hatayı kaydetmesi için yeniden fırlat