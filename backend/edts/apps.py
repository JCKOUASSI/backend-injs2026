"""Application dédiée à la gestion des emplois du temps (lot L8).

Couplage avec le reste du socle INJS-LMD :
- lecture/écriture des créneaux, plannings et affectations ;
- détection de conflits via services métier ;
- journalisation via scolarite.JournalScolarite pour les opérations sensibles ;
- compatibilité avec le contrat /api/scolarite/edt/ en lecture seule.
"""

from django.apps import AppConfig


class EdtsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'edts'
    verbose_name = 'LMD – Emploi du temps'
