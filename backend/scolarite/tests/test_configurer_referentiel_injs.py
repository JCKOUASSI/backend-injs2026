"""Tests de la configuration de l'offre de formation INJS (maquettes UE/ECUE).

Garanties vérifiées :

* idempotence stricte (deux exécutions → aucun doublon) ;
* fidélité au référentiel officiel (30 ECTS par semestre, totals connus) ;
* aucune invention : semestre absent de la source ⇒ aucune UE, aucun parcours,
  aucun code prétendu officiel, aucun volume horaire ;
* respect de l'immuabilité : une maquette validée n'est jamais modifiée ;
* le bug de double suffixe de ``qualifier_referentiel_injs_l6`` ne revient pas.
"""

import json
from datetime import time
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TestCase

from formations.models import RefFormation
from edts.models import CreneauTemplate
from scolarite.models import (
    ECUE, FamilleModule, Maquette, Niveau, Parcours, Semestre, StatutEtudiant, UE,
)

DONNEES = Path(__file__).resolve().parents[1] / 'data' / 'referentiel_offre_formation.json'


class ConfigurerReferentielInjsTests(TestCase):
    """Configuration des maquettes depuis le référentiel officiel."""

    @classmethod
    def setUpTestData(cls):
        call_command('init_referentiels_lmd', '--annee', '2026-2027',
                     stdout=StringIO())
        call_command('import_referentiel_injs_lmd', stdout=StringIO())
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())

    def _configurer(self, *args):
        return call_command('configurer_referentiel_injs', *args, stdout=StringIO())

    # ── Le jeu de données est présent et cohérent ───────────────────────────
    def test_jeu_de_donnees_present(self):
        self.assertTrue(DONNEES.is_file(), f'Jeu de données absent : {DONNEES}')
        donnees = json.loads(DONNEES.read_text(encoding='utf-8'))
        self.assertEqual(len(donnees['filieres']), 8)
        self.assertEqual(set(donnees['filiere_du_sigle'].values()),
                         {'F01', 'F02', 'F03', 'F04'})

    def test_tous_les_semestres_a_30_credits_dans_la_source(self):
        donnees = json.loads(DONNEES.read_text(encoding='utf-8'))
        for sigle, par_semestre in donnees['maquettes'].items():
            for numero, lignes in par_semestre.items():
                total = sum(ligne['credits'] or 0 for ligne in lignes)
                self.assertEqual(
                    total, 30,
                    f'{sigle} S{numero} : {total} crédits au lieu de 30.',
                )

    # ── Exécution réelle ────────────────────────────────────────────────────
    def test_cree_maquettes_ue_ecue(self):
        self._configurer()
        self.assertEqual(Maquette.objects.count(), 20)
        self.assertEqual(UE.objects.count(), 323)
        self.assertEqual(ECUE.objects.filter(archive=False).count(), 397)

    def test_chaque_semestre_totalise_30_ects(self):
        self._configurer()
        for maquette in Maquette.objects.select_related('niveau'):
            for semestre in Semestre.objects.filter(niveau=maquette.niveau):
                total = UE.objects.filter(
                    maquette=maquette, semestre=semestre,
                ).aggregate(total=Sum('credits'))['total'] or 0
                if total == 0:
                    continue
                self.assertEqual(
                    total, 30,
                    f'{maquette.ref_formation.filiere_code} {maquette.niveau.code} '
                    f'S{semestre.numero} : {total} crédits.',
                )

    def test_maquettes_en_brouillon_non_activees(self):
        self._configurer()
        self.assertEqual(
            set(Maquette.objects.values_list('statut', flat=True)), {'BROUILLON'},
        )

    def test_rattachement_au_bon_cycle(self):
        """L1–L3 → formation Licence, M1–M2 → formation Master."""
        self._configurer()
        for maquette in Maquette.objects.select_related('niveau', 'ref_formation'):
            attendu = 'LICENCE' if maquette.niveau.code.startswith('L') else 'MASTER'
            self.assertEqual(maquette.ref_formation.type_diplome, attendu)
            self.assertEqual(maquette.niveau.cycle, attendu)

    def test_aucun_parcours_invente(self):
        self._configurer()
        self.assertEqual(Parcours.objects.count(), 0)
        self.assertEqual(Maquette.objects.filter(parcours__isnull=False).count(), 0)

    def test_aucun_volume_horaire_invente(self):
        self._configurer()
        self.assertEqual(
            ECUE.objects.exclude(volume_cm=0, volume_td=0, volume_tp=0).count(), 0,
        )

    def test_semestre_ms_s8_absent_non_cree(self):
        """MS S8 est absent du référentiel : aucune UE ne doit y être rattachée."""
        self._configurer()
        maquette_m1 = Maquette.objects.get(
            ref_formation__filiere_code='F04', niveau__code='M1',
        )
        s8 = Semestre.objects.get(niveau__code='M1', numero=8)
        self.assertEqual(
            UE.objects.filter(maquette=maquette_m1, semestre=s8).count(), 0,
        )
        # Les autres semestres de M1 sont bien pourvus.
        s7 = Semestre.objects.get(niveau__code='M1', numero=7)
        self.assertGreater(
            UE.objects.filter(maquette=maquette_m1, semestre=s7).count(), 0,
        )

    def test_filieres_ensep_sans_maquette(self):
        """F05–F08 n'ont aucune maquette publiée : on n'en crée pas."""
        self._configurer()
        self.assertEqual(
            Maquette.objects.filter(
                ref_formation__filiere_code__in=['F05', 'F06', 'F07', 'F08'],
            ).count(),
            0,
        )

    def test_codes_techniques_explicites(self):
        self._configurer()
        codes = set(UE.objects.values_list('code', flat=True))
        self.assertIn('EM-S1-UE01', codes)
        for code in codes:
            self.assertRegex(code, r'^(EM|MS|ES|APA)-S\d{1,2}-UE\d{2}$')

    # ── Idempotence ─────────────────────────────────────────────────────────
    def test_idempotence_stricte(self):
        self._configurer()
        etat1 = (Maquette.objects.count(), UE.objects.count(),
                 ECUE.objects.filter(archive=False).count())
        self._configurer()
        etat2 = (Maquette.objects.count(), UE.objects.count(),
                 ECUE.objects.filter(archive=False).count())
        self.assertEqual(etat1, etat2)
        self.assertEqual(etat1, (20, 323, 397))

    def test_dry_run_n_ecrit_rien(self):
        self._configurer('--dry-run')
        self.assertEqual(
            (Maquette.objects.count(), UE.objects.count(), ECUE.objects.count()),
            (0, 0, 0),
        )

    def test_mise_a_jour_si_intitule_change(self):
        """Une correction de la source est propagée sans créer de doublon."""
        self._configurer()
        ue = UE.objects.get(code='EM-S1-UE01')
        ue.intitule = 'Intitulé erroné'
        ue.save(update_fields=['intitule'])
        self._configurer()
        ue.refresh_from_db()
        self.assertNotEqual(ue.intitule, 'Intitulé erroné')
        self.assertEqual(UE.objects.count(), 323)

    # ── Immuabilité des maquettes validées ──────────────────────────────────
    def test_maquette_validee_non_modifiee(self):
        self._configurer()
        maquette = Maquette.objects.get(
            ref_formation__filiere_code='F01', niveau__code='L1',
        )
        maquette.statut = Maquette.Statut.VALIDEE
        maquette.save(update_fields=['statut'])
        avant = list(
            UE.objects.filter(maquette=maquette).values_list('code', 'credits')
        )
        self._configurer()
        apres = list(
            UE.objects.filter(maquette=maquette).values_list('code', 'credits')
        )
        self.assertEqual(avant, apres)

    # ── Garde-fous d'exécution ──────────────────────────────────────────────
    def test_refuse_si_structure_lmd_absente(self):
        niveaux = list(Niveau.objects.values_list('id', flat=True))
        Semestre.objects.all().delete()
        Niveau.objects.filter(id__in=niveaux).update()
        Maquette.objects.all().delete()
        # Suppression réelle des niveaux (aucune maquette ne les référence plus).
        Niveau.objects.all().delete()
        with self.assertRaises(CommandError):
            self._configurer()

    def test_annee_inconnue_refusee(self):
        with self.assertRaises(CommandError):
            self._configurer('--annee', '1999-2000')


class QualifierReferentielTests(TestCase):
    """Non-régression du double suffixe de cycle (bug corrigé)."""

    def test_pas_de_double_suffixe(self):
        call_command('init_referentiels_lmd', '--annee', '2026-2027',
                     stdout=StringIO())
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())
        intitules = list(
            RefFormation.objects.filter(
                perimetre=RefFormation.Perimetre.INJS,
            ).values_list('intitule', flat=True)
        )
        for intitule in intitules:
            self.assertNotRegex(
                intitule, r'— (LICENCE|MASTER) — (LICENCE|MASTER)$',
                f'Intitulé doublement suffixé : {intitule}',
            )

    def test_12_cycles_injs(self):
        """4 filières ENSEPS × 2 cycles + 4 filières ENSEP × 1 cycle = 12."""
        call_command('init_referentiels_lmd', '--annee', '2026-2027',
                     stdout=StringIO())
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())
        self.assertEqual(
            RefFormation.objects.filter(
                perimetre=RefFormation.Perimetre.INJS,
            ).count(),
            12,
        )

    def test_cycles_licence_et_master_typés(self):
        call_command('init_referentiels_lmd', '--annee', '2026-2027',
                     stdout=StringIO())
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())
        for filiere in ('F01', 'F02', 'F03', 'F04'):
            cycles = set(
                RefFormation.objects.filter(filiere_code=filiere)
                .values_list('type_diplome', flat=True)
            )
            self.assertEqual(cycles, {'LICENCE', 'MASTER'}, filiere)


class ReferentielsClasseurTests(TestCase):
    """Référentiels annexes du classeur : familles, statuts, plages horaires."""

    @classmethod
    def setUpTestData(cls):
        call_command('init_referentiels_lmd', '--annee', '2026-2027',
                     stdout=StringIO())
        call_command('import_referentiel_injs_lmd', stdout=StringIO())
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())

    def _configurer(self, *args):
        return call_command('configurer_referentiel_injs', *args, stdout=StringIO())

    def test_12_familles_de_modules(self):
        self._configurer()
        self.assertEqual(FamilleModule.objects.count(), 12)

    def test_toutes_les_ue_ont_une_famille(self):
        self._configurer()
        self.assertEqual(UE.objects.filter(famille__isnull=True).count(), 0)

    def test_total_credits_par_famille_coherent(self):
        """La somme des crédits par famille égale le total du référentiel."""
        from django.db.models import Sum

        self._configurer()
        total_ue = UE.objects.aggregate(total=Sum('credits'))['total']
        total_familles = 0
        for famille in FamilleModule.objects.all():
            total_familles += (
                famille.unites_enseignement.aggregate(total=Sum('credits'))['total'] or 0
            )
        self.assertEqual(total_familles, total_ue)
        self.assertEqual(total_ue, 1170)

    def test_statuts_etudiants_du_classeur(self):
        """Les 9 statuts du classeur sont disponibles, sans doublon sémantique."""
        from scolarite.management.commands.configurer_referentiel_injs import (
            _normaliser_libelle,
        )

        self._configurer()
        presents = {
            _normaliser_libelle(libelle)
            for libelle in StatutEtudiant.objects.values_list('libelle', flat=True)
        }
        attendus = {
            _normaliser_libelle(libelle)
            for libelle in ('Pré-inscrit', 'Inscrit', 'En cours', 'Admis(e)',
                            'Redouble', 'Ajourné(e)', 'Exclu(e)', 'Diplômé(e)',
                            'Abandon')
        }
        self.assertTrue(attendus <= presents, attendus - presents)

    def test_statuts_crees_ne_bloquent_pas_et_existants_preserves(self):
        """Le classeur ne dit pas quels statuts bloquent : rien n'est déduit.

        De plus, un statut déjà présent n'est jamais réécrit : son drapeau
        ``bloque_inscription`` relève du règlement de scolarité.
        """
        avant = dict(
            StatutEtudiant.objects.values_list('libelle', 'bloque_inscription')
        )
        self._configurer()
        apres = dict(
            StatutEtudiant.objects.values_list('libelle', 'bloque_inscription')
        )
        for libelle, bloque in avant.items():
            self.assertEqual(apres[libelle], bloque, libelle)
        for libelle in ('Pré-inscrit', 'Inscrit', 'En cours'):
            self.assertFalse(apres[libelle], libelle)

    def test_plages_horaires_du_modele_edt(self):
        self._configurer()
        self.assertEqual(CreneauTemplate.objects.count(), 24)
        plages = set(
            CreneauTemplate.objects.values_list('heure_debut', 'heure_fin')
        )
        self.assertIn((time(7, 30), time(9, 30)), plages)
        self.assertIn((time(15, 45), time(17, 45)), plages)

    def test_referentiels_annexes_idempotents(self):
        self._configurer()
        etat1 = (FamilleModule.objects.count(), StatutEtudiant.objects.count(),
                 CreneauTemplate.objects.count())
        self._configurer()
        etat2 = (FamilleModule.objects.count(), StatutEtudiant.objects.count(),
                 CreneauTemplate.objects.count())
        self.assertEqual(etat1, etat2)
        self.assertEqual(etat1[0], 12)
        self.assertEqual(etat1[2], 24)
        self.assertGreaterEqual(etat1[1], 9)

    def test_ecue_surnumeraires_archivees_non_supprimees(self):
        """Une ECUE en trop est archivée : la donnée n'est jamais détruite."""
        self._configurer()
        ue = UE.objects.get(code='EM-S3-UE04')
        ECUE.objects.create(ue=ue, code='EM-S3-UE04-EC99',
                            intitule='Surnuméraire', ordre=99)
        avant = ECUE.objects.filter(ue=ue).count()
        self._configurer()
        self.assertEqual(ECUE.objects.filter(ue=ue).count(), avant)
        self.assertTrue(
            ECUE.objects.get(code='EM-S3-UE04-EC99').archive,
        )
        self.assertEqual(ECUE.objects.filter(ue=ue, archive=False).count(),
                         ECUE.objects.filter(ue=ue).count() - 1)
