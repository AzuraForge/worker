# worker/src/azuraforge_worker/callbacks.py

import json
import os
import redis
from typing import Any, Optional
from azuraforge_learner import Callback
import logging # Loglama modülünü import ediyoruz

class RedisProgressCallback(Callback):
    """
    Learner'dan gelen olayları dinler ve Redis Pub/Sub kanalı üzerinden
    ilerleme durumunu yayınlar.
    """
    def __init__(self, task_id: str):
        super().__init__()
        self.task_id = task_id
        self._redis_client: Optional[redis.Redis] = None
        try:
            redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
            self._redis_client = redis.from_url(redis_url)
            logging.info(f"RedisProgressCallback initialized for task {task_id}. Connected to Redis.")
        except Exception as e:
            logging.error(f"HATA: RedisProgressCallback içinde Redis'e bağlanılamadı: {e}")

    def on_epoch_end(self, event: Any) -> None:
        """
        Her epoch sonunda Learner tarafından tetiklenir ve
        ilerleme verisini ilgili Redis kanalına yayınlar.
        """
        if not self._redis_client or not self.task_id:
            return
            
        payload = event.payload
        if not payload:
            logging.warning(f"RedisProgressCallback: Empty payload for task {self.task_id}.")
            return

        try:
            channel = f"task-progress:{self.task_id}"
            
            # --- YENİ LOGLAMA İLE TEŞHİS ---
            validation_data = payload.get('validation_data')
            if validation_data:
                y_true_len = len(validation_data.get('y_true', []))
                y_pred_len = len(validation_data.get('y_pred', []))
                x_axis_len = len(validation_data.get('x_axis', []))
                logging.info(f"RedisProgressCallback: Publishing progress for task {self.task_id}, epoch {payload.get('epoch')}. Loss: {payload.get('loss'):.4f}. Validation data size: y_true={y_true_len}, y_pred={y_pred_len}, x_axis={x_axis_len}")
            else:
                logging.info(f"RedisProgressCallback: Publishing progress for task {self.task_id}, epoch {payload.get('epoch')}. Loss: {payload.get('loss'):.4f}. No validation data in payload.")
            # --- TEŞHİS SONU ---

            message = json.dumps(payload)
            self._redis_client.publish(channel, message)
            
        except Exception as e:
            logging.error(f"HATA: Redis'e ilerleme durumu yayınlanamadı: {e}", exc_info=True)