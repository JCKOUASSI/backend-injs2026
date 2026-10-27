"""
Signaux du module Paramètres.

L'historique des modifications reste géré dans ``ParametreUpdateSerializer``
(voir le commentaire historique ci-dessous) ; ce module n'ajoute que
l'invalidation du cache des feature flags (P00-08) afin qu'une bascule soit
prise en compte immédiatement, quelle que soit la voie d'écriture
(API, admin Django, script, migration).
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .flags import FLAG_PREFIX, invalidate_flags_cache
from .models import Parametre


@receiver(post_save, sender=Parametre)
def parametre_flags_invalidation_on_save(sender, instance, **kwargs):
    if instance.cle and instance.cle.startswith(FLAG_PREFIX):
        invalidate_flags_cache()


@receiver(post_delete, sender=Parametre)
def parametre_flags_invalidation_on_delete(sender, instance, **kwargs):
    if instance.cle and instance.cle.startswith(FLAG_PREFIX):
        invalidate_flags_cache()
