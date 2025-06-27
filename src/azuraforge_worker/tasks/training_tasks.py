# ========== DOSYA: src/azuraforge_worker/tasks/training_tasks.py ==========
from ..celery_app import celery_app
import time

# Gerçek kütüphanelerimizi import edelim
from azuraforge_learner import Learner, Sequential, Linear, MSELoss, SGD

@celery_app.task(name="start_training_pipeline")
def start_training_pipeline(config: dict):
    """
    Verilen konfigürasyon ile bir eğitim pipeline'ını çalıştıran Celery görevi.
    """
    pipeline_name = config.get("pipeline_name", "unknown")
    epochs = config.get("training_params", {}).get("epochs", 10)
    
    print(f"Worker: Received task for pipeline '{pipeline_name}'. Starting training for {epochs} epochs.")
    
    # --- SAHTE EĞİTİM SİMÜLASYONU ---
    # Gerçekte burada 'applications' reposundan ilgili pipeline'ı yükleyip
    # learner.fit() metodunu çağıracağız.
    # Şimdilik, sadece çalıştığını görmek için basit bir döngü yapalım.
    try:
        total_steps = epochs
        for i in range(total_steps):
            # İlerleme durumunu güncelle (gerçek zamanlı takip için)
            progress = (i + 1) / total_steps * 100
            start_training_pipeline.update_state(
                state='PROGRESS',
                meta={'current': i + 1, 'total': total_steps, 'status': f'Epoch {i+1}/{total_steps} completed...'}
            )
            print(f"Epoch {i+1}/{total_steps}...")
            time.sleep(1) # Her epoch 1 saniye sürsün

        result_message = f"Training for '{pipeline_name}' completed successfully."
        print(f"Worker: {result_message}")
        return {"status": "SUCCESS", "message": result_message}
    except Exception as e:
        print(f"Worker: Training failed! Error: {e}")
        return {"status": "FAILURE", "message": str(e)}