"""Application dédiée à la diplômation et documents officiels (lot L4 — Prompt 14).

Délivre, trace et publie les diplômes LMD ainsi que les documents officiels
(attestation, certificat, relevé de notes, diplôme) en s'appuyant sur le
socle versionné existant : exports (moteur PDF), jurys (DecisionJury),
scolarite (InscriptionAdministrative, AnneeAcademique).
"""
from django.apps import AppConfig


class GraduationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'graduation'
    verbose_name = "LMD – Diplômation & Documents officiels"
