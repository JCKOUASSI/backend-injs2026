"""Application dédiée à l'administration générale (lot L7).

Courriers, documents officiels (notes de service, arrêtés, décisions),
réunions/commissions et missions. Le cycle de vie est auditée via
``scolarite.JournalScolarite`` (bonnes pratiques du socle INJS-LMD).
"""

from django.apps import AppConfig


class AdministrationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'administrations'
    verbose_name = 'LMD – Administration'