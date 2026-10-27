"""Application dédiée aux ressources humaines (lot L7).

Agents, services, fonctions, affectations et disponibilités. Indépendante du
socle ``formations.Formateur`` (paie formateurs inchangée) : un agent peut être
fermé sur un utilisateur ``authentication.User``.
"""

from django.apps import AppConfig


class RessourcesHumainesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ressources_humaines'
    verbose_name = 'LMD – Ressources Humaines'