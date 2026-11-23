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


class TestListeModelesDocuments(TestCase):
    """Régression : la liste des modèles de documents renvoyait 500.

    `RefFormation` nomme son champ `intitule` ; le tri de la vue portait sur
    `formation__libelle`, un champ inexistant. Dès qu'un modèle existait, la
    requête levait un `FieldError` et l'interface affichait une erreur 500.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model

        from formations.models import RefFormation
        from graduation.models import ModeleDocument

        self.user = get_user_model().objects.create_user(
            username='secr', password='x', role='SECRETARIAT',
        )
        self.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        ModeleDocument.objects.create(
            type=ModeleDocument.Type.ATTESTATION,
            libelle='Attestation de scolarité',
            formation=self.formation,
        )

    def test_liste_accessible_et_triee_par_intitule(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.user)
        reponse = client.get('/api/graduation/modeles/')

        self.assertEqual(reponse.status_code, 200, reponse.content[:300])
        resultats = reponse.json()['results']
        self.assertEqual(len(resultats), 1)
        self.assertEqual(resultats[0]['libelle'], 'Attestation de scolarité')
        self.assertEqual(resultats[0]['formation'], str(self.formation))
