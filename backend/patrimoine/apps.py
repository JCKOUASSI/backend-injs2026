"""Application dédiée au patrimoine (lot L7).

Équipements, véhicules, inventaires, maintenances et réservations d'espaces.
Les espaces référencent ``formations.RefSite/RefBatiment/RefSalle`` (source
unique de vérité) et les mouvements sont tracés de manière append-only.
"""

from django.apps import AppConfig


class PatrimoineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'patrimoine'
    verbose_name = 'LMD – Patrimoine'