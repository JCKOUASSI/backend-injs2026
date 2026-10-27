import csv
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from django.core.management import CommandError, call_command
from django.test import TestCase

from formations.models import RefFormation, RefModule
from scolarite import pedagogie_services
from scolarite.models import (
    ECUE,
    UE,
    AnneeAcademique,
    Maquette,
    Niveau,
    Semestre,
)

COLONNES = [
    'ANNEE', 'FORMATION', 'PARCOURS', 'NIVEAU', 'SEMESTRE',
    'UE_CODE', 'UE_INTITULE', 'UE_CREDITS', 'UE_CARACTERE',
    'ECUE_CODE', 'ECUE_INTITULE', 'ECUE_CREDITS', 'COEFFICIENT',
    'CM', 'TD', 'TP', 'MODULE',
]


def ligne(**overrides):
    base = {
        'ANNEE': '2026-2027',
        'FORMATION': 'LICENCE STAPS',
        'PARCOURS': '',
        'NIVEAU': 'L1',
        'SEMESTRE': 'S1',
        'UE_CODE': 'UE11',
        'UE_INTITULE': 'Sciences du mouvement',
        'UE_CREDITS': '9',
        'UE_CARACTERE': 'OBLIGATOIRE',
        'ECUE_CODE': 'ECUE111',
        'ECUE_INTITULE': 'Anatomie',
        'ECUE_CREDITS': '5',
        'COEFFICIENT': '2',
        'CM': '20',
        'TD': '10',
        'TP': '0',
        'MODULE': '',
    }
    base.update(overrides)
    return base


class ImportMaquetteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        cls.s2 = Semestre.objects.create(niveau=cls.niveau, numero=2, libelle='S2')
        cls.module = RefModule.objects.create(intitule='ANATOMIE FONCTIONNELLE')

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix='maquette-'))

    def ecrire(self, lignes, nom='maquette.csv'):
        chemin = self.dossier / nom
        with chemin.open('w', encoding='utf-8-sig', newline='') as fichier:
            redacteur = csv.DictWriter(fichier, fieldnames=COLONNES, delimiter=';')
            redacteur.writeheader()
            redacteur.writerows(lignes)
        return chemin

    def importer(self, lignes, **options):
        sortie = StringIO()
        call_command('import_maquette', str(self.ecrire(lignes)), stdout=sortie, **options)
        return sortie.getvalue()

    def test_import_regroupe_les_ecue_sous_une_seule_ue(self):
        self.importer([
            ligne(),
            ligne(ECUE_CODE='ECUE112', ECUE_INTITULE='Pratique sportive', TP='30'),
        ])

        self.assertEqual(Maquette.objects.count(), 1)
        self.assertEqual(UE.objects.count(), 1)
        self.assertEqual(ECUE.objects.count(), 2)
        self.assertEqual(UE.objects.get().semestre, self.s1)

    def test_semestres_multiples_dans_la_meme_maquette(self):
        self.importer([
            ligne(),
            ligne(SEMESTRE='S2', UE_CODE='UE21', UE_INTITULE='Physiologie', ECUE_CODE='ECUE211'),
        ])

        self.assertEqual(Maquette.objects.count(), 1)
        self.assertEqual(
            set(UE.objects.values_list('semestre__numero', flat=True)), {1, 2},
        )

    def test_rattachement_au_module_operationnel(self):
        self.importer([ligne(MODULE='anatomie fonctionnelle')])

        self.assertEqual(ECUE.objects.get().ref_module, self.module)

    def test_module_inconnu_signale_sans_bloquer(self):
        sortie = self.importer([ligne(MODULE='MODULE FANTOME')])

        self.assertIsNone(ECUE.objects.get().ref_module)
        self.assertIn('MODULE FANTOME', sortie)

    def test_module_inconnu_ne_cree_pas_de_ref_module(self):
        avant = RefModule.objects.count()
        self.importer([ligne(MODULE='MODULE FANTOME')])

        self.assertEqual(RefModule.objects.count(), avant)

    def test_dry_run_n_ecrit_rien(self):
        sortie = self.importer([ligne()], dry_run=True)

        self.assertEqual(Maquette.objects.count(), 0)
        self.assertEqual(ECUE.objects.count(), 0)
        self.assertIn('Simulation', sortie)

    def test_activer_passe_la_maquette_en_active(self):
        self.importer([ligne()], activer=True)

        self.assertEqual(Maquette.objects.get().statut, Maquette.Statut.ACTIVE)

    def test_statut_brouillon_par_defaut(self):
        self.importer([ligne()])

        self.assertEqual(Maquette.objects.get().statut, Maquette.Statut.BROUILLON)

    def test_second_import_cree_une_nouvelle_version(self):
        self.importer([ligne()])
        self.importer([ligne()])

        self.assertEqual(
            sorted(Maquette.objects.values_list('version', flat=True)), [1, 2],
        )

    def test_version_explicite_met_a_jour_la_maquette_existante(self):
        self.importer([ligne()])
        self.importer([ligne(ECUE_INTITULE='Anatomie générale')], version_maquette=1)

        self.assertEqual(Maquette.objects.count(), 1)
        self.assertEqual(ECUE.objects.get().intitule, 'Anatomie générale')

    def test_annee_inconnue_annule_tout_l_import(self):
        with self.assertRaises(CommandError) as contexte:
            self.importer([ligne(), ligne(ANNEE='2099-2100', ECUE_CODE='ECUE112')])

        self.assertIn('2099-2100', str(contexte.exception))
        self.assertEqual(Maquette.objects.count(), 0)

    def test_formation_absente_du_referentiel_est_rejetee(self):
        with self.assertRaises(CommandError) as contexte:
            self.importer([ligne(FORMATION='LICENCE INEXISTANTE')])

        self.assertIn('LICENCE INEXISTANTE', str(contexte.exception))

    def test_semestre_incoherent_avec_le_niveau_est_rejete(self):
        with self.assertRaises(CommandError) as contexte:
            self.importer([ligne(SEMESTRE='S5')])

        self.assertIn('S5', str(contexte.exception))

    def test_credits_non_numeriques_sont_rejetes(self):
        with self.assertRaises(CommandError) as contexte:
            self.importer([ligne(ECUE_CREDITS='cinq')])

        self.assertIn('ECUE_CREDITS', str(contexte.exception))

    def test_erreurs_multiples_sont_toutes_listees(self):
        with self.assertRaises(CommandError) as contexte:
            self.importer([
                ligne(ANNEE='2099-2100'),
                ligne(FORMATION='INCONNUE', ECUE_CODE='ECUE112'),
            ])

        message = str(contexte.exception)
        self.assertIn('Ligne 2', message)
        self.assertIn('Ligne 3', message)

    def test_colonne_obligatoire_manquante(self):
        chemin = self.dossier / 'partiel.csv'
        with chemin.open('w', encoding='utf-8-sig', newline='') as fichier:
            fichier.write('ANNEE;FORMATION\n2026-2027;LICENCE STAPS\n')

        with self.assertRaises(CommandError) as contexte:
            call_command('import_maquette', str(chemin), stdout=StringIO())

        self.assertIn('NIVEAU', str(contexte.exception))

    def test_modele_genere_est_reimportable(self):
        modele = self.dossier / 'modele.csv'
        call_command('import_maquette', modele=str(modele), stdout=StringIO())

        self.assertTrue(modele.exists())
        with modele.open(encoding='utf-8-sig', newline='') as fichier:
            lignes = list(csv.DictReader(fichier, delimiter=';'))
        self.assertEqual(list(lignes[0].keys()), COLONNES)

    def test_maquette_importee_alimente_les_inscriptions_pedagogiques(self):
        self.importer([
            ligne(),
            ligne(SEMESTRE='S2', UE_CODE='UE21', UE_INTITULE='Physiologie', ECUE_CODE='ECUE211'),
        ], activer=True)

        inscription = SimpleNamespace(
            annee_academique=self.annee,
            ref_formation=self.formation,
            niveau=self.niveau,
            parcours_id=None,
            parcours=None,
        )
        maquette = pedagogie_services.maquette_applicable(inscription)

        self.assertIsNotNone(maquette)
        self.assertEqual(maquette.unites_enseignement.count(), 2)
