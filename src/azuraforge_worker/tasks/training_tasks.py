# ========== GÜNCELLENECEK DOSYA: worker/src/azuraforge_worker/tasks/training_tasks.py ==========
from ..celery_app import celery_app
from importlib.metadata import entry_points
import logging

# --- Eklenti Keşfi ---
def discover_pipelines():
    """Sisteme kurulmuş tüm AzuraForge pipeline'larını keşfeder."""
    discovered = {}
    try:
        # 'azuraforge.pipelines' giriş noktasını ara
        eps = entry_points(group='azuraforge.pipelines')
        for ep in eps:
            discovered[ep.name] = ep.load() # Sınıfı yükle
            logging.info(f"Discovered pipeline: '{ep.name}' -> {ep.value}")
    except Exception as e:
        logging.error(f"Error discovering pipelines: {e}")
    return discovered

PIPELINES = discover_pipelines()

@celery_app.task(name="start_training_pipeline")
def start_training_pipeline(config: dict):
    pipeline_name = config.get("pipeline_name")
    if not pipeline_name:
        raise ValueError("'pipeline_name' is required.")

    if pipeline_name not in PIPELINES:
        raise ValueError(f"Pipeline '{pipeline_name}' not found or installed as a plugin.")

    # Keşfedilen sınıflardan doğru olanı al
    PipelineClass = PIPELINES[pipeline_name]
    
    print(f"Worker: Found pipeline '{pipeline_name}'. Instantiating {PipelineClass.__name__}...")
    
    try:
        pipeline_instance = PipelineClass(config)
        results = pipeline_instance.run()
        return {"status": "SUCCESS", "results": results}
    except Exception as e:
        error_message = f"Worker: Pipeline '{pipeline_name}' failed! Error: {e}"
        print(error_message)
        import traceback
        traceback.print_exc() # Detaylı hata logu için
        raise Exception(error_message)