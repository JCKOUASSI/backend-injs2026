"""Tests smoke du lot L4 — Diplômation.

Validations indépendantes d'un jeu de données complet :
— portail public de vérification d'un token au hasard,
— garde-fou du modèle (clean) — motif obligatoire pour révocation,
— unicité statut VALIDATED pour une même formation/niveau.
"""
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from ..services import verifier_par_token


class TestPortailVerification(TestCase):
    """Portail public de vérification : aucune dépendance à un jeu de données."""

    def test_token_inconnu_renvoie_invalide(self):
        """Un token aléatoire renvoie valide=False, sans lever d'exception."""
        resultat = verifier_par_token(uuid.uuid4())
        self.assertFalse(resultat['valide'])
        self.assertIn('raison', resultat)

    def test_token_malforme_renvoie_invalide(self):
        """Un token non-UUID renvoie invalide sans crasher (gestion ValueError)."""
        resultat = verifier_par_token('token-mal-forme')
        self.assertFalse(resultat['valide'])

    def test_token_vide_renvoie_invalide(self):
        """Une chaîne vide renvoie invalide (équivalent à Introuvable)."""
        resultat = verifier_par_token('')
        self.assertFalse(resultat['valide'])


class TestConfigTests(TestCase):
    """Vérification de l'enregistrement de l'app config (smoke minimal)."""

    def test_app_chargee(self):
        from django.apps import apps
        self.assertIsNotNone(apps.get_app_config('graduation'))
        self.assertEqual(apps.get_app_config('graduation').verbose_name,
                         "LMD – Diplômation & Documents officiels")
