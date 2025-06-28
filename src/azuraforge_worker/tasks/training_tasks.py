# ========== DOSYA: worker/src/azuraforge_worker/tasks/training_tasks.py ==========
from ..celery_app import celery_app
from importlib.metadata import entry_points
import logging

# --- Eklenti Keşfi (Worker başladığında bir kez çalışır) ---
def discover_pipelines():
    logging.info("Discovering installed AzuraForge pipeline plugins...")
    discovered = {}
    try:
        eps = entry_points(group='azuraforge.pipelines')
        for ep in eps:
            logging.info(f"Found plugin: '{ep.name}' -> points to '{ep.value}'")
            discovered[ep.name] = ep.load() # Sınıfı yükle ve sakla
    except Exception as e:
        logging.error(f"Error discovering pipelines: {e}")
    return discovered

# Worker başladığında pipeline'ları yükle ve bir sözlükte tut
AVAILABLE_PIPELINES = discover_pipelines()
if not AVAILABLE_PIPELINES:
    logging.warning("No AzuraForge pipelines found! Please install a pipeline plugin, e.g., 'azuraforge-app-stock-predictor'.")


@celery_app.task(name="start_training_pipeline")
def start_training_pipeline(config: dict):
    pipeline_name = config.get("pipeline_name")
    if not pipeline_name:
        raise ValueError("'pipeline_name' is required in the task config.")

    if pipeline_name not in AVAILABLE_PIPELINES:
        raise ValueError(f"Pipeline '{pipeline_name}' is not an installed plugin. Available: {list(AVAILABLE_PIPELINES.keys())}")

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