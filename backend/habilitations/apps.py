"""Configuration de l'application CURP « habilitations » (unité U1).

U1 est un socle de données **strictement additif** : ``ready()`` ne branche
aucun signal décisionnaire, aucune permission DRF, aucune route n'est mise
sous contrôle. Le moteur d'autorisation, le mode observation et les
basculements par drapeaux arrivent en U2 et au-delà. L'application peut donc
être installée (ou retirée d'``INSTALLED_APPS``) sans modifier le
comportement du dispositif d'authentification existant.
"""
from django.apps import AppConfig


class HabilitationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'habilitations'
    verbose_name = 'Comptes, rôles & permissions (CURP)'

    def ready(self):
        # Volontairement vide en U1 : aucun branchement sur le socle
        # d'authentification existant (règle R2 — additif d'abord).
        return
