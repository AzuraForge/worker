# ========== DOSYA: src/azuraforge_worker/tasks/training_tasks.py ==========
import logging
from ..celery_app import celery_app
from importlib.metadata import entry_points

# --- Eklenti Keşfi (Worker başladığında bir kez çalışır) ---
def discover_pipelines():
    """Sisteme kurulmuş tüm AzuraForge pipeline'larını keşfeder."""
    logging.info("Discovering installed AzuraForge pipeline plugins...")
    discovered = {}
    try:
        # 'azuraforge.pipelines' grubuna kayıtlı tüm giriş noktalarını bul
        eps = entry_points(group='azuraforge.pipelines')
        for ep in eps:
            logging.info(f"Found plugin: '{ep.name}' -> points to '{ep.value}'")
            # ep.load(), 'azuraforge_stockapp.pipeline:StockPredictionPipeline' gibi bir string'i
            # gerçek bir Python sınıfına dönüştürür.
            discovered[ep.name] = ep.load() 
    except Exception as e:
        logging.error(f"Error discovering pipelines: {e}")
    return discovered

# Worker ilk başladığında, kurulu tüm eklentileri yükle ve bir sözlükte tut
AVAILABLE_PIPELINES = discover_pipelines()

if not AVAILABLE_PIPELINES:
    logging.warning("No AzuraForge pipelines found! Please install a pipeline plugin.")

@celery_app.task(name="start_training_pipeline")
def start_training_pipeline(config: dict):
    """
    API'dan gelen konfigürasyona göre doğru pipeline eklentisini bulur ve çalıştırır.
    """
    pipeline_name = config.get("pipeline_name")
    if not pipeline_name:
        raise ValueError("'pipeline_name' is required in the task config.")

    if pipeline_name not in AVAILABLE_PIPELINES:
        raise ValueError(f"Pipeline '{pipeline_name}' not found. Installed plugins: {list(AVAILABLE_PIPELINES.keys())}")

    # Keşfedilen sınıflardan doğru olanı al
    PipelineClass = AVAILABLE_PIPELINES[pipeline_name]
    
    logging.info(f"Worker: Instantiating pipeline '{PipelineClass.__name__}'...")
    
    try:
        pipeline_instance = PipelineClass(config)
        results = pipeline_instance.run()
        return {"status": "SUCCESS", "results": results}
    except Exception as e:
        logging.error(f"Worker: Pipeline execution failed for '{pipeline_name}'. Error: {e}", exc_info=True)
        raise e