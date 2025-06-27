# ========== DOSYA: worker/src/azuraforge_worker/__init__.py ==========
from .celery_app import celery_app

# Bu, diğer projelerin 'from azuraforge_worker import celery_app' yapabilmesini sağlar.
__all__ = ("celery_app",)