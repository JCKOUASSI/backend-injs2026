"""Application dédiée aux finances étudiantes (L6).

Socle L6 : paiements, échéanciers, factures, quittances, remboursements et
rapprochement bancaire.
Ce module est STRICTEMENT distinct du module des finances de formateurs
(formations.FinanceSettings/Ajustement).
Rattaché à l'inscription administrative L2 et à l'année académique L3.
"""
from django.apps import AppConfig


class FinancesEtudiantesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finances_etudiantes'
    verbose_name = "Finances Étudiantes"
