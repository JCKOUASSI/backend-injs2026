"""Nomenclatures « Administratif & scolarité » (PDF du 1er novembre 2026).

Modes de paiement, types de frais, types de document, types de
notification et années académiques, transcrits des tableaux du document :
les valeurs « socle » sont exactement les choix du module
finances_etudiantes (jusqu'au code historique ELEPHANT_MONEY), la
typologie pratique reste en fiabilité CADRAGE tant qu'elle n'est pas
arrêtée par la DAF, la Scolarité et la Direction des études. Aucun
montant : les barèmes relèvent de l'arrêté annuel de tarification.
"""
from django.core.management import call_command
from django.test import TestCase

from finances_etudiantes.models import MODE_PAIEMENT, NATURE_FRAIS
from referentiels.models import (
    RefModePaiement,
    RefTypeDocument,
    RefTypeFrais,
    RefTypeNotification,
)
from scolarite.models import AnneeAcademique


class NomenclaturesAdministratifTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('importer_referentiels_injs', '--sans-cycles')

    def test_volumes_des_tableaux_du_document(self):
        self.assertEqual(RefModePaiement.objects.count(), 14)
        self.assertEqual(RefTypeFrais.objects.count(), 28)
        self.assertEqual(RefTypeDocument.objects.count(), 56)
        self.assertEqual(RefTypeNotification.objects.count(), 47)
        self.assertEqual(AnneeAcademique.objects.count(), 8)

    def test_provenance_complete_sur_toutes_les_valeurs(self):
        for modele in (RefModePaiement, RefTypeFrais, RefTypeDocument,
                       RefTypeNotification):
            with self.subTest(modele=modele.__name__):
                self.assertFalse(
                    modele.objects.filter(fiabilite='A_RENSEIGNER').exists())
                self.assertFalse(
                    modele.objects.filter(source_document='').exists())
                self.assertFalse(
                    modele.objects.filter(description='').exists())

    def test_valeurs_socle_alignees_sur_le_module_finances(self):
        # Les 5 natures et 6 modes du socle, mot pour mot : ni plus, ni
        # moins, et ce sont les seules valeurs OFFICIEL des deux blocs.
        self.assertEqual(
            set(RefTypeFrais.objects.filter(fiabilite='OFFICIEL')
                .values_list('code', flat=True)),
            {code for code, _ in NATURE_FRAIS},
        )
        self.assertEqual(
            set(RefModePaiement.objects.filter(fiabilite='OFFICIEL')
                .values_list('code', flat=True)),
            {code for code, _ in MODE_PAIEMENT},
        )
        # Code historique du socle, conservé à l'identique.
        orange = RefModePaiement.objects.get(code='ELEPHANT_MONEY')
        self.assertEqual(orange.libelle, 'Orange Money')
        self.assertEqual(
            RefModePaiement.objects.filter(fiabilite='CADRAGE').count(), 8)
        self.assertEqual(
            RefTypeFrais.objects.filter(fiabilite='CADRAGE').count(), 23)

    def test_documents_sept_familles_et_fiche_complete(self):
        attendus = {
            'DOC_CAND_': 6, 'DOC_SCO_': 9, 'DOC_EVA_': 7, 'DOC_DIP_': 5,
            'DOC_STG_': 4, 'DOC_FIN_': 8, 'DOC_MED_': 3, 'DOC_PIE_': 9,
            'DOC_ETA_': 5,
        }
        for prefixe, nombre in attendus.items():
            with self.subTest(prefixe=prefixe):
                self.assertEqual(
                    RefTypeDocument.objects.filter(
                        code__startswith=prefixe).count(), nombre)
        certificat = RefTypeDocument.objects.get(code='DOC_SCO_01')
        for zone in ('Famille :', 'Nature :', 'Émetteur :', 'Signataire :',
                     'Validité :', 'Traçabilité :', 'VALIDEE'):
            self.assertIn(zone, certificat.description)
        diplome = RefTypeDocument.objects.get(code='DOC_DIP_01')
        self.assertIn('SHA-256', diplome.description)

    def test_notifications_cinq_familles(self):
        attendus = {'NOT_ALR_': 8, 'NOT_RAP_': 10, 'NOT_VAL_': 13,
                    'NOT_INF_': 10, 'NOT_SEC_': 6}
        for prefixe, nombre in attendus.items():
            with self.subTest(prefixe=prefixe):
                self.assertEqual(
                    RefTypeNotification.objects.filter(
                        code__startswith=prefixe).count(), nombre)
        alerte = RefTypeNotification.objects.get(code='NOT_ALR_03')
        self.assertIn('CRITIQUE', alerte.description)
        self.assertIn('Déclencheur :', alerte.description)
        validation = RefTypeNotification.objects.get(code='NOT_VAL_01')
        self.assertIn('48 heures', validation.description)
        self.assertIn('A_VALIDER', validation.description)

    def test_annees_calendrier_et_statuts(self):
        annees = {a.libelle: a for a in AnneeAcademique.objects.all()}
        for libelle, annee in annees.items():
            with self.subTest(libelle=libelle):
                self.assertEqual(
                    (annee.date_debut.month, annee.date_debut.day), (10, 1))
                self.assertEqual(
                    (annee.date_fin.month, annee.date_fin.day), (7, 31))
        # Une seule année courante : 2026-2027.
        self.assertEqual(
            AnneeAcademique.objects.filter(courante=True).count(), 1)
        self.assertEqual(
            AnneeAcademique.courante_ou_none().libelle, '2026-2027')
        # Archivées : inactives et clôturées.
        for libelle in ('2021-2022', '2022-2023', '2023-2024', '2024-2025'):
            annee = annees[libelle]
            self.assertFalse(annee.actif)
            self.assertTrue(annee.cloturee)
            self.assertEqual(annee.date_cloture, annee.date_fin)
        # 2025-2026 clôturée mais encore consultable.
        cloturee = annees['2025-2026']
        self.assertTrue(cloturee.actif)
        self.assertTrue(cloturee.cloturee)
        self.assertEqual(cloturee.date_cloture, cloturee.date_fin)
        # Planifiées : actives, ni courantes ni clôturées.
        for libelle in ('2027-2028', '2028-2029'):
            annee = annees[libelle]
            self.assertTrue(annee.actif)
            self.assertFalse(annee.courante)
            self.assertFalse(annee.cloturee)
            self.assertIsNone(annee.date_cloture)

    def test_import_idempotent(self):
        call_command('importer_referentiels_injs', '--sans-cycles')
        self.assertEqual(RefModePaiement.objects.count(), 14)
        self.assertEqual(RefTypeFrais.objects.count(), 28)
        self.assertEqual(RefTypeDocument.objects.count(), 56)
        self.assertEqual(RefTypeNotification.objects.count(), 47)
        self.assertEqual(AnneeAcademique.objects.count(), 8)
        self.assertEqual(
            AnneeAcademique.courante_ou_none().libelle, '2026-2027')
