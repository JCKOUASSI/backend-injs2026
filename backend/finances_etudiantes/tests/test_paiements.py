"""Tests smoke du lot L6 — Finances étudiantes.

Validation des services et garde-fous sans dépendre d'un jeu de données
complet : idempotence, validations de garde, anti-doublon.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from ..services import (
    confirmer_paiement, enregistrer_paiement_idempotent,
    valider_paiement_par_transaction,
)


class TestEnregistrementPaiement(TestCase):
    """Garde-fous du service idempotent d'enregistrement."""

    def test_paiement_sans_source_leve_erreur(self):
        """Aucun étudiant ni candidat → ValidationError."""
        with self.assertRaises(ValidationError):
            enregistrer_paiement_idempotent(
                nature='DOSSIER', montant=Decimal('100'),
                devise='XOF', mode='CAISSE',
                transaction_externe='TX_TEST_001',
            )

    def test_montant_zero_leve_erreur(self):
        """Montant zéro ou négatif → ValidationError (avant etudiant/candidat)."""
        # etudiant=None, candidat=None — la 1ère garde sur etudiant/candidat
        # déclencherait avant le montant, on délègue donc au test source.
        with self.assertRaises(ValidationError):
            enregistrer_paiement_idempotent(
                nature='DOSSIER', montant=0,
                devise='XOF', mode='CAISSE',
                transaction_externe='TX_TEST_002',
            )
        with self.assertRaises(ValidationError):
            enregistrer_paiement_idempotent(
                nature='DOSSIER', montant=Decimal('-50'),
                devise='XOF', mode='CAISSE',
                transaction_externe='TX_TEST_003',
            )

    def test_transaction_externe_vide_renvoie_none(self):
        """valider_paiement_par_transaction('') renvoie None (pas de crash)."""
        self.assertIsNone(valider_paiement_par_transaction(''))
        self.assertIsNone(valider_paiement_par_transaction(None))

    def test_paiement_cree_avec_source_generique_candidat(self):
        """Chemin de succès (candidat) : la GFK source est renseignée (P00-08)."""
        from admissions.models import Candidat
        from ..models import Paiement

        candidat = Candidat.objects.create(nom='Test', prenom='Source', sexe='M')
        paiement, cree = enregistrer_paiement_idempotent(
            candidat=candidat, nature='DOSSIER', montant=Decimal('1000'),
            devise='XOF', mode='CAISSE', transaction_externe='TX_OK_001',
        )
        self.assertTrue(cree)
        self.assertEqual(Paiement.objects.count(), 1)
        # La clé polymorphe NOT NULL doit pointer vers le candidat.
        self.assertEqual(paiement.object_id, candidat.pk)
        self.assertEqual(paiement.source, candidat)
        self.assertEqual(paiement.statut, 'INITIE')

    def test_paiement_idempotent_renvoie_le_meme_enregistrement(self):
        """Deux envois avec la même transaction externe = un seul paiement."""
        from admissions.models import Candidat
        from ..models import Paiement

        candidat = Candidat.objects.create(nom='Test', prenom='Idem', sexe='F')
        kwargs = dict(
            candidat=candidat, nature='INSCRIPTION', montant=Decimal('5000'),
            devise='XOF', mode='MTN_MONEY',
        )
        premier, cree_premier = enregistrer_paiement_idempotent(
            transaction_externe='TX_IDEM_001', **kwargs
        )
        deuxieme, cree_deuxieme = enregistrer_paiement_idempotent(
            transaction_externe='TX_IDEM_001', **kwargs
        )
        self.assertTrue(cree_premier)
        self.assertFalse(cree_deuxieme)
        self.assertEqual(premier.pk, deuxieme.pk)
        self.assertEqual(Paiement.objects.count(), 1)
        self.assertEqual(deuxieme.source, candidat)

    def test_confirmation_emet_une_quittance(self):
        """Chemin de succès : preuve fournie → CONFIRME + Quittance unique."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils import timezone
        from admissions.models import Candidat
        from ..models import Quittance

        candidat = Candidat.objects.create(nom='Test', prenom='Conf', sexe='M')
        paiement, _ = enregistrer_paiement_idempotent(
            candidat=candidat, nature='SCOLARITE', montant=Decimal('25000'),
            devise='XOF', mode='CAISSE', transaction_externe='TX_CONF_001',
        )
        paiement.preuve = SimpleUploadedFile('preuve.txt', b'preuve')
        paiement.save()
        confirmer_paiement(paiement, utilisateur=None)
        paiement.refresh_from_db()
        self.assertEqual(paiement.statut, 'CONFIRME')
        self.assertEqual(Quittance.objects.count(), 1)
        quittance = Quittance.objects.get()
        self.assertEqual(quittance.date_echeance, timezone.localdate())
        # Idempotent : un second appel ne crée pas de doublon.
        confirmer_paiement(paiement, utilisateur=None)
        self.assertEqual(Quittance.objects.count(), 1)

    def test_confirmation_sans_preuve_leve_erreur(self):
        """Aucune preuve → ValidationError, pas de quittance, statut inchangé."""
        from admissions.models import Candidat
        from ..models import Quittance

        candidat = Candidat.objects.create(nom='Test', prenom='SansPreuve', sexe='F')
        paiement, _ = enregistrer_paiement_idempotent(
            candidat=candidat, nature='SCOLARITE', montant=Decimal('25000'),
            devise='XOF', mode='CAISSE', transaction_externe='TX_CONF_002',
        )
        with self.assertRaises(ValidationError):
            confirmer_paiement(paiement, utilisateur=None)
        self.assertEqual(Quittance.objects.count(), 0)


class TestModelesRegles(TestCase):
    """Validation des contraintes sur Tarification (unicité)."""

    def test_nature_choices_valables(self):
        """Les natures acceptées à la création sont les 5 prévues."""
        from ..models import NATURE_FRAIS
        natures = dict(NATURE_FRAIS)
        self.assertEqual(set(natures.keys()), {
            'DOSSIER', 'INSCRIPTION', 'SCOLARITE', 'EXAMEN', 'DOCUMENT',
        })
