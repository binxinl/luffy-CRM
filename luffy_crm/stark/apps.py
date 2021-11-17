from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules

class StarkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stark'

    def ready(self):
        autodiscover_modules('stark')  # 优先再app下查找stark.py文件
