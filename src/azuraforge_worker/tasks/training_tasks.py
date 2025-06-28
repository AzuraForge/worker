# ========== GÜNCELLENECEK DOSYA: worker/src/azuraforge_worker/tasks/training_tasks.py ==========
import logging
import time
from ..celery_app import celery_app
from importlib.metadata import entry_points
from celery import current_task

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
PIPELINES = discover_pipelines() # Bu satır da aynı

if not PIPELINES:
    logging.warning("No AzuraForge pipelines found! Please install a pipeline plugin.")

@celery_app.task(bind=True, name="start_training_pipeline")
def start_training_pipeline(self, config: dict): # 'self' parametresini ekliyoruz (bind=True sayesinde)
    pipeline_name = config.get("pipeline_name")
    if not pipeline_name: raise ValueError("'pipeline_name' is required.")
    if pipeline_name not in PIPELINES: raise ValueError(f"Pipeline '{pipeline_name}' not found.")

    PipelineClass = PIPELINES[pipeline_name]
    logging.info(f"Worker: Instantiating pipeline '{PipelineClass.__name__}'...")
    
    try:
        # Gerçek pipeline'ı çağırmak yerine, canlı takip için bir simülasyon yapalım
        # pipeline_instance = PipelineClass(config)
        # results = pipeline_instance.run() # Bu satırı şimdilik yorumluyoruz

        # --- CANLI TAKİP SİMÜLASYONU ---
        epochs = config.get("training_params", {}).get("epochs", 10)
        for i in range(epochs):
            # Her epoch'ta durumu güncelle ve meta verisi gönder
            # Bu bilgi Redis'e yazılacak ve API tarafından okunabilecek.
            loss = 1 / (i + 1) # Azalan bir kayıp değeri simüle et
            self.update_state(
                state='PROGRESS',
                meta={
                    'epoch': i + 1, 
                    'total_epochs': epochs, 
                    'loss': loss,
                    'status_text': f'Epoch {i+1}/{epochs} tamamlandı...'
                }
            )
            logging.info(f"Epoch {i+1}/{epochs} - Loss: {loss:.4f}")
            time.sleep(1.5) # Her epoch'un 1.5 saniye sürdüğünü varsayalım

        final_results = {'status': 'completed', 'final_loss': loss}
        return {"status": "SUCCESS", "results": final_results}

    except Exception as e:
        logging.error(f"Worker: Pipeline execution failed. Error: {e}", exc_info=True)
        # Hata durumunda da durumu güncelle
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e