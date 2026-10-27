"""Référentiel INJS chargé en base par l'unité U3 (annexes A1 à A6 du recueil).

Ce package contient des DONNÉES auditées (aucune décision d'accès, aucune
vue) : modules et permissions atomiques (A3), rôles (A1), niveaux de la
matrice (A2), incompatibilités (J5) et table de correspondance avec les 12
rôles existants (A6). Le chargement est idempotent
(:mod:`habilitations.referentiel.chargement`) et reste modifiable en base
sans redéploiement.
"""
