import os

from django.core.wsgi import get_wsgi_application

from config.bootstrap_env import load_env

load_env()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
