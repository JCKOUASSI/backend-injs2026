"""Fichiers statiques servis à la racine (/sw.js, /favicon.ico)."""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404


def _static_file(name):
    path = Path(settings.BASE_DIR) / 'static' / name
    if not path.is_file():
        raise Http404
    return path


def service_worker(request):
    return FileResponse(_static_file('sw.js').open('rb'), content_type='application/javascript')


def favicon(request):
    return FileResponse(
        _static_file('img/logo-injs.png').open('rb'),
        content_type='image/png',
    )
