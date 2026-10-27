"""Application dédiée aux stages et conventions (lot L5 — Prompt 14).

Gestion des stages LMD : organismes d'accueil, tuteurs externes, conventions
de stage, workflow de validation administrative, évaluations, soutenance.

Adossé à ``scolarite.DossierEtudiant`` et ``scolarite.AnneeAcademique``.
Une convention VALIDEE_JURY valide l'une des conditions de diplômation L4
(``Diplome.verifier_conditions_validation``).
"""
from django.apps import AppConfig


class StagesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stages'
    verbose_name = "LMD – Stages & Conventions"
