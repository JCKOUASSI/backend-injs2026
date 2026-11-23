"""Tests de la commande de parcours de fumée ``smoke_test_injs`` (P00-08).

La commande reprend les recettes bout-en-bout du projet (candidature,
inscription, pédagogie, jurys, diplôme, finances) et doit :

* passer les 23 étapes sur une base neuve et rendre un code 0 ;
* annuler la totalité de ses écritures par défaut (mode CI, idempotent) ;
* conserver les données avec ``--persist`` ;
* s'arrêter avec un code d'erreur et un rapport dès qu'une étape casse.
"""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

CODES_ETAPES = [
    'SMOKE-01-CAMPAGNE', 'SMOKE-02-CANDIDAT', 'SMOKE-03-PIECES',
    'SMOKE-04-ADMISSIBILITE', 'SMOKE-05-ADMISSION', 'SMOKE-06-IA',
    'SMOKE-07-MATRICULE', 'SMOKE-08-IP', 'SMOKE-09-GROUPE',
    'SMOKE-10-MAQUETTE', 'SMOKE-11-PASSERELLE', 'SMOKE-12-SEANCE',
    'SMOKE-13-QR', 'SMOKE-14-POINTAGE', 'SMOKE-15-NOTE',
    'SMOKE-16-MOYENNE', 'SMOKE-17-JURY', 'SMOKE-18-DIPLOME',
    'SMOKE-19-TARIFS', 'SMOKE-20-ECHEANCIER', 'SMOKE-21-FACTURE',
    'SMOKE-22-PAIEMENT', 'SMOKE-23-QUITTANCE',
]


class SmokeCommandeTests(TestCase):
    def _executer(self, *args):
        sortie = StringIO()
        call_command('smoke_test_injs', *args, stdout=sortie, stderr=StringIO())
        return sortie.getvalue()

    def test_parcours_complet_23_etapes_sur_base_neuve(self):
        sortie = self._executer()
        for code in CODES_ETAPES:
            self.assertIn(code, sortie)
        self.assertIn('SUCCÈS', sortie)
        self.assertIn('INJS26-0001', sortie)
        self.assertIn('session VERROUILLE', sortie)
        self.assertIn('PDF + SHA-256', sortie)
        self.assertIn('quittance', sortie)

    def test_mode_ci_annule_toutes_les_ecritures(self):
        """Par défaut : aucune donnée ne subsiste (idempotent en CI)."""
        from admissions.models import Candidat
        from finances_etudiantes.models import Paiement
        from graduation.models import Diplome
        from jurys.models import SessionJury
        from scolarite.models import AnneeAcademique

        self._executer()
        self.assertFalse(AnneeAcademique.objects.exists())
        self.assertFalse(Candidat.objects.exists())
        self.assertFalse(SessionJury.objects.exists())
        self.assertFalse(Diplome.objects.exists())
        self.assertFalse(Paiement.objects.exists())

    def test_double_execution_mode_ci_reste_idempotente(self):
        """Deux exécutions successives passent et ne laissent rien."""
        from scolarite.models import AnneeAcademique

        self._executer()
        self._executer()
        self.assertFalse(AnneeAcademique.objects.exists())

    def test_persist_conserve_les_donnees(self):
        """Avec --persist, les écritures sont visibles après la commande."""
        from finances_etudiantes.models import Quittance
        from graduation.models import Diplome
        from scolarite.models import AnneeAcademique, InscriptionAdministrative

        sortie = self._executer('--persist')
        self.assertIn('PERSISTANCE', sortie)
        self.assertEqual(AnneeAcademique.objects.count(), 1)
        self.assertEqual(InscriptionAdministrative.objects.filter(statut='VALIDEE').count(), 1)
        self.assertEqual(Diplome.objects.filter(statut='VALIDATED').count(), 1)
        self.assertEqual(Quittance.objects.count(), 1)

    def test_echec_d_une_etape_arrete_et_rollback(self):
        """Une exception sur une étape → CommandError identifiée + rollback."""
        from scolarite.models import AnneeAcademique

        sortie = StringIO()
        with mock.patch(
            'scolarite.management.commands.smoke_test_injs.candidature_services.creer_candidature',
            side_effect=RuntimeError('panne provoquée'),
        ):
            with self.assertRaises(CommandError) as contexte:
                call_command('smoke_test_injs', stdout=sortie, stderr=StringIO())
        texte = sortie.getvalue()
        self.assertIn('SMOKE-02-CANDIDAT', str(contexte.exception))
        self.assertIn('ÉCHEC', texte)
        # Les étapes postérieures ne sont pas jouées.
        self.assertNotIn('SMOKE-03-PIECES', texte)
        # La transaction est annulée.
        self.assertFalse(AnneeAcademique.objects.exists())
