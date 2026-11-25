import os

from django.core.asgi import get_asgi_application

from config.bootstrap_env import load_env

load_env()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()
