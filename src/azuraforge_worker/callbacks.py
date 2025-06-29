# worker/src/azuraforge_worker/callbacks.py

import json
import os
from typing import Any, Optional
import redis
from azuraforge_learner import Callback

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
            # Worker konteyneri içinden Redis URL'sini ortam değişkeninden alır.
            redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
            self._redis_client = redis.from_url(redis_url)
        except Exception as e:
            print(f"HATA: RedisProgressCallback içinde Redis'e bağlanılamadı: {e}")

    def on_epoch_end(self, event: Any) -> None:
        """
        Her epoch sonunda Learner tarafından tetiklenir ve
        ilerleme verisini ilgili Redis kanalına yayınlar.
        """
        if not self._redis_client or not self.task_id:
            return
            
        # Learner tarafından _publish metodu ile gönderilen payload'u (epoch_logs) alır.
        payload = event.payload
        if not payload:
            return

        try:
            channel = f"task-progress:{self.task_id}"
            message = json.dumps(payload)
            self._redis_client.publish(channel, message)
        except Exception as e:
            # Eğitimi durdurmamak için hatayı sadece logluyoruz.
            print(f"HATA: Redis'e ilerleme durumu yayınlanamadı: {e}")