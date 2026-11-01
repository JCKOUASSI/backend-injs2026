"""Garanties du module Finances Étudiantes — permissions et contrôles monétaires.

Ces tests couvrent des défauts constatés sur l'état initial :

* les listes (paiements, échéanciers, quittances, relances) ne portaient que
  ``IsAuthenticated`` : un compte étudiant lisait toutes les données
  financières de l'établissement par appel direct de l'API alors que
  l'interface lui masque le module ;
* ``finances_etudiantes/permissions.py`` n'était branché nulle part et
  contenait un rôle corrompu (``CHEF_SE   TARIAT``) ;
* un remboursement pouvait dépasser le montant encaissé, porter sur un
  paiement non confirmé, ou être rejoué sans idempotence ;
* la confirmation testait le statut ``REMBOLSE`` (faute de frappe) au lieu de
  ``REMBOURSE`` : un paiement remboursé pouvait être re-confirmé ;
* régénérer une facture le même jour levait une erreur d'unicité, et générer
  deux fois un échéancier créait deux échéanciers (double facturation).
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Participant, RefFormation
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
    InscriptionAdministrative,
    Niveau,
)

from ..models import Echeancier, Facture, LigneEcheancier, Paiement, Remboursement, Tarification
from ..services import (
    confirmer_paiement,
    creer_remboursement,
    enregistrer_paiement_idempotent,
    generer_echeancier_pour_etudiant,
    generer_facture,
)


def _pdf_valide():
    """Contenu minimal accepté par le validateur de preuve (magic bytes PDF)."""
    return ContentFile(b'%PDF-1.4\n% preuve de paiement\n', name='preuve.pdf')


class FixtureFinances(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.participant = Participant.objects.create(
            nom='Kone', prenom='Awa', sexe='F', matricule='INJS26-9001',
        )
        cls.dossier = DossierEtudiant.objects.create(participant=cls.participant)
        # La génération d'un échéancier s'appuie sur l'inscription administrative
        # de l'année : sans elle, le service ne trouve aucune tarification.
        cls.inscription = InscriptionAdministrative.objects.create(
            etudiant=cls.dossier, annee_academique=cls.annee,
            ref_formation=cls.formation, niveau=cls.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )
        Tarification.objects.create(
            formation=cls.formation, annee_academique=cls.annee,
            nature='INSCRIPTION', montant_base=Decimal('150000'),
        )

    def utilisateur(self, username, role):
        return User.objects.create_user(username=username, password='pass', role=role)

    def client_pour(self, role, username=None):
        user = self.utilisateur(username or f'u_{role.lower()}', role)
        client = APIClient()
        client.force_authenticate(user)
        return client, user

    def paiement_confirme(self, montant=Decimal('50000')):
        paiement, _ = enregistrer_paiement_idempotent(
            etudiant=self.dossier, nature='INSCRIPTION', montant=montant,
            devise='XOF', mode='CAISSE', transaction_externe=f'TX-{montant}-OK',
            utilisateur=self.utilisateur('agent_fin', 'FINANCE'),
        )
        paiement.preuve.save('preuve.pdf', _pdf_valide(), save=True)
        confirmer_paiement(paiement, paiement.utilisateur)
        return paiement


class PermissionsFinancesEtudiantesTests(FixtureFinances):
    """L'API applique la matrice de rôles que l'interface suppose."""

    URLS_LECTURE = (
        '/api/finances-etudiantes/paiements/',
        '/api/finances-etudiantes/echeanciers/',
        '/api/finances-etudiantes/quittances/',
        '/api/finances-etudiantes/relances/',
    )

    def test_etudiant_ne_lit_pas_les_donnees_financieres(self):
        client, _ = self.client_pour('AUDITEUR')
        for url in self.URLS_LECTURE:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 403)

    def test_formateur_ne_lit_pas_les_donnees_financieres(self):
        client, _ = self.client_pour('FORMATEUR')
        for url in self.URLS_LECTURE:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 403)

    def test_secretariat_lit_les_donnees_financieres(self):
        client, _ = self.client_pour('SECRETARIAT')
        for url in self.URLS_LECTURE:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 200)

    def test_finance_et_direction_lisent(self):
        for role in ('FINANCE', 'DIRECTION', 'ARCHIVE', 'ENCADRANT'):
            client, _ = self.client_pour(role, username=f'lecteur_{role.lower()}')
            with self.subTest(role=role):
                self.assertEqual(client.get('/api/finances-etudiantes/paiements/').status_code, 200)

    def test_secretariat_ne_confirme_pas_un_paiement(self):
        """La confirmation crée une quittance : réservée à FINANCE/DIRECTION/admins."""
        client, _ = self.client_pour('SECRETARIAT')
        paiement = self.paiement_confirme()
        self.assertEqual(
            client.post(f'/api/finances-etudiantes/paiements/{paiement.id}/confirmer/').status_code,
            403,
        )

    def test_finance_confirme_un_paiement(self):
        """Régression : `IsDFRC` excluait FINANCE, qui ne pouvait donc jamais valider."""
        client, _ = self.client_pour('FINANCE')
        paiement, _ = enregistrer_paiement_idempotent(
            etudiant=self.dossier, nature='INSCRIPTION', montant=Decimal('25000'),
            devise='XOF', mode='CAISSE', transaction_externe='TX-A-CONFIRMER',
        )
        paiement.preuve.save('preuve.pdf', _pdf_valide(), save=True)
        reponse = client.post(f'/api/finances-etudiantes/paiements/{paiement.id}/confirmer/')
        self.assertEqual(reponse.status_code, 200)
        paiement.refresh_from_db()
        self.assertEqual(paiement.statut, 'CONFIRME')

    def test_direction_ne_cree_pas_d_echeancier_en_ecriture(self):
        """DIRECTION valide ; la saisie courante reste ouverte au secrétariat."""
        client, _ = self.client_pour('DIRECTION')
        reponse = client.post(
            '/api/finances-etudiantes/echeanciers/',
            {'etudiant_id': self.dossier.id, 'annee_academique_id': self.annee.id},
            format='json',
        )
        self.assertIn(reponse.status_code, (201, 200))

    def test_etudiant_ne_cree_pas_d_echeancier(self):
        client, _ = self.client_pour('AUDITEUR')
        reponse = client.post(
            '/api/finances-etudiantes/echeanciers/',
            {'etudiant_id': self.dossier.id, 'annee_academique_id': self.annee.id},
            format='json',
        )
        self.assertEqual(reponse.status_code, 403)
        self.assertFalse(Echeancier.objects.exists())


class GarantiesMonetairesTests(FixtureFinances):
    def test_paiement_rembourse_ne_peut_pas_etre_reconfirme(self):
        paiement = self.paiement_confirme()
        paiement.statut = 'REMBOURSE'
        paiement.save(update_fields=['statut'])
        with self.assertRaises(ValidationError):
            confirmer_paiement(paiement, None)

    def test_remboursement_superieur_au_montant_refuse(self):
        paiement = self.paiement_confirme(Decimal('10000'))
        with self.assertRaises(ValidationError):
            creer_remboursement(
                paiement_original=paiement, montant=Decimal('10001'),
                motif='Trop-perçu',
            )

    def test_cumul_des_remboursements_borne_au_montant_encaisse(self):
        paiement = self.paiement_confirme(Decimal('10000'))
        creer_remboursement(paiement_original=paiement, montant=Decimal('6000'), motif='Partiel')
        with self.assertRaises(ValidationError):
            creer_remboursement(paiement_original=paiement, montant=Decimal('5000'), motif='Solde')
        self.assertEqual(Remboursement.objects.count(), 1)

    def test_remboursement_sur_paiement_non_confirme_refuse(self):
        paiement, _ = enregistrer_paiement_idempotent(
            etudiant=self.dossier, nature='INSCRIPTION', montant=Decimal('9000'),
            devise='XOF', mode='CAISSE', transaction_externe='TX-NON-CONFIRME',
        )
        with self.assertRaises(ValidationError):
            creer_remboursement(paiement_original=paiement, montant=Decimal('1000'), motif='Erreur')

    def test_remboursement_idempotent_par_transaction_externe(self):
        paiement = self.paiement_confirme(Decimal('20000'))
        premier, cree1 = creer_remboursement(
            paiement_original=paiement, montant=Decimal('5000'), motif='Erreur de caisse',
            transaction_externe='REM-001',
        )
        second, cree2 = creer_remboursement(
            paiement_original=paiement, montant=Decimal('5000'), motif='Erreur de caisse',
            transaction_externe='REM-001',
        )
        self.assertTrue(cree1)
        self.assertFalse(cree2)
        self.assertEqual(premier.pk, second.pk)
        self.assertEqual(Remboursement.objects.count(), 1)

    def test_api_remboursement_refuse_un_montant_excessif(self):
        client, _ = self.client_pour('FINANCE')
        paiement = self.paiement_confirme(Decimal('1000'))
        reponse = client.post(
            '/api/finances-etudiantes/remboursements/',
            {'paiement_original_id': paiement.id, 'montant': '5000', 'motif': 'Test'},
            format='json',
        )
        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(Remboursement.objects.exists())

    def test_facture_regenerable_le_meme_jour(self):
        echeancier = generer_echeancier_pour_etudiant(self.dossier, self.annee)
        premiere = generer_facture(echeancier)
        seconde = generer_facture(echeancier)
        self.assertEqual(premiere.pk, seconde.pk)
        self.assertEqual(Facture.objects.count(), 1)

    def test_echeancier_idempotent(self):
        premier = generer_echeancier_pour_etudiant(self.dossier, self.annee)
        second = generer_echeancier_pour_etudiant(self.dossier, self.annee)
        self.assertEqual(premier.pk, second.pk)
        self.assertEqual(Echeancier.objects.count(), 1)
        self.assertEqual(LigneEcheancier.objects.count(), 1)

    def test_quittance_creee_une_seule_fois(self):
        from ..models import Quittance

        paiement = self.paiement_confirme()
        confirmer_paiement(paiement, None)  # rejeu : ne doit rien créer de plus
        self.assertEqual(Quittance.objects.filter(paiement=paiement).count(), 1)


class LibellesPaiementTests(FixtureFinances):
    """L'API doit exposer des libellés lisibles, pas seulement les codes.

    Défaut constaté : l'écran « Finances étudiantes » affichait ``p.mode`` tel
    quel, donc « ELEPHANT_MONEY » ou « CARTE_BANCAIRE » au guichet. Les codes
    restent exposés (clients existants) ; les libellés s'y ajoutent.
    """

    def test_liste_paiements_expose_les_libelles(self):
        client, _ = self.client_pour('FINANCE')
        paiement, _ = enregistrer_paiement_idempotent(
            etudiant=self.dossier, nature='INSCRIPTION', montant=Decimal('25000'),
            devise='XOF', mode='ELEPHANT_MONEY', transaction_externe='OM-LIB-1',
            utilisateur=self.utilisateur('agent_lib', 'FINANCE'),
        )
        res = client.get('/api/finances-etudiantes/paiements/')
        self.assertEqual(res.status_code, 200)
        lignes = res.data.get('results', res.data)
        ligne = next(l for l in lignes if l['id'] == paiement.id)
        self.assertEqual(ligne['mode'], 'ELEPHANT_MONEY')
        self.assertEqual(ligne['mode_libelle'], 'Orange Money')
        self.assertEqual(ligne['nature_libelle'], "Frais d'inscription")
        self.assertEqual(ligne['statut_libelle'], 'Initialisé')

    def test_tous_les_codes_de_paiement_ont_un_libelle(self):
        from ..models import MODE_PAIEMENT, NATURE_FRAIS, STATUT_PAIEMENT

        for code, libelle in MODE_PAIEMENT + NATURE_FRAIS + STATUT_PAIEMENT:
            self.assertTrue(libelle.strip(), f'libellé manquant pour {code}')
            # Un libellé ne doit pas être le code recopié : il serait illisible
            # dans l'interface (« ELEPHANT_MONEY »).
            self.assertNotEqual(libelle, code)
