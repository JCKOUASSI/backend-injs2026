from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .api_cache import bump_referentiels_cache_version
from .models import (
    RefBatiment,
    RefCategorie,
    RefFormation,
    RefGrade,
    RefModule,
    RefModuleVolumeHoraire,
    RefSalle,
    RefSite,
    RefTypeSecretariat,
    RefVague,
)

_REFERENTIEL_MODELS = (
    RefFormation,
    RefModule,
    RefModuleVolumeHoraire,
    RefSite,
    RefBatiment,
    RefSalle,
    RefCategorie,
    RefGrade,
    RefTypeSecretariat,
    RefVague,
)


def _invalidate_referentiels_cache(**kwargs):
    bump_referentiels_cache_version()


for _model in _REFERENTIEL_MODELS:
    post_save.connect(_invalidate_referentiels_cache, sender=_model, weak=False)
    post_delete.connect(_invalidate_referentiels_cache, sender=_model, weak=False)
