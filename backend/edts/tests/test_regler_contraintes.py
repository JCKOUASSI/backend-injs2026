"""La décision de politique doit être reproductible et traçable.

L'écran d'administration règle l'environnement où il est ouvert. Une décision
pédagogique doit pouvoir être **transportée** (préproduction, production) et
**rejouée à l'identique** : c'est le rôle de la commande
`regler_contraintes_souples`. Ce qui est vérifié ici :

1. `--verifier` n'écrit rien, même avec des valeurs complètes ;
2. aucune écriture sans motif — un réglage anonyme n'est pas une décision ;
3. une valeur invalide est refusée AVANT écriture (pause inversée, borne nulle) ;
4. l'enregistrement porte les bornes, le motif et l'auteur ;
5. rejouer la même politique ne réécrit ni la date ni l'auteur ;
6. `--desactiver` coupe les règles sans perdre les bornes déjà décidées ;
7. la politique enregistrée pilote réellement le moteur.
"""

import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from edts.models import PolitiqueContraintesSouples
from edts.moteur import contraintes as C


def _appeler(*options):
    sortie = io.StringIO()
    call_command('regler_contraintes_souples', *options,
                 stdout=sortie, stderr=io.StringIO())
    return sortie.getvalue()


class ReglerContraintesSouplesTests(TestCase):

    def setUp(self):
        self.direction = get_user_model().objects.create_user(
            username='direction', password='x', role='DIRECTION')

    def _regler(self, *options, motif='Bornes du référentiel appliquées.'):
        return _appeler(*options, '--motif', motif)

    # ── 1. Lecture seule ────────────────────────────────────────────────────
    def test_verifier_n_ecrit_rien(self):
        sortie = _appeler('--verifier', '--activer', '--max-jour', '6')
        self.assertEqual(PolitiqueContraintesSouples.objects.count(), 0)
        self.assertIn('Aucune écriture', sortie)
        self.assertIn('max_heures_par_jour = 6.0', sortie)

    def test_verifier_affiche_la_politique_effective(self):
        sortie = _appeler('--verifier')
        self.assertIn('origine defaut', sortie)
        self.assertIn('4 h consécutives', sortie)
        self.assertIn('pause aucune', sortie)

    # ── 2. Pas d'écriture sans motif ────────────────────────────────────────
    def test_motif_obligatoire(self):
        with self.assertRaises(CommandError) as ctx:
            _appeler('--activer')
        self.assertIn('motif', str(ctx.exception).lower())
        self.assertEqual(PolitiqueContraintesSouples.objects.count(), 0)

    def test_aucune_valeur_demandee_refusee(self):
        with self.assertRaises(CommandError):
            _appeler('--motif', 'Rien à faire.')

    def test_activer_et_desactiver_ensemble_refuses(self):
        with self.assertRaises(CommandError):
            _appeler('--activer', '--desactiver', '--motif', 'Ambigu.')

    # ── 3. Validation avant écriture ────────────────────────────────────────
    def test_pause_inversee_refusee_sans_rien_ecrire(self):
        with self.assertRaises(CommandError) as ctx:
            self._regler('--activer', '--pause', '13:30-11:45')
        self.assertIn('pause', str(ctx.exception).lower())
        self.assertEqual(PolitiqueContraintesSouples.objects.count(), 0)

    def test_format_de_pause_invalide_refuse(self):
        with self.assertRaises(CommandError):
            self._regler('--activer', '--pause', '11h45')

    def test_borne_nulle_refusee(self):
        with self.assertRaises(CommandError):
            self._regler('--activer', '--max-jour', '0')
        self.assertEqual(PolitiqueContraintesSouples.objects.count(), 0)

    # ── 4. Enregistrement complet ───────────────────────────────────────────
    def test_enregistrement_des_bornes_du_motif_et_de_l_auteur(self):
        self._regler('--activer', '--max-consecutives', '4', '--max-jour', '8',
                     '--tolerance', '15', '--pause', '11:45-13:30',
                     '--auteur', 'direction')
        ligne = PolitiqueContraintesSouples.charger()
        self.assertTrue(ligne.actives)
        self.assertEqual(ligne.max_heures_consecutives, 4.0)
        self.assertEqual(ligne.max_heures_par_jour, 8.0)
        self.assertEqual(ligne.tolerance_minutes, 15)
        self.assertEqual(ligne.pause_debut.strftime('%H:%M'), '11:45')
        self.assertEqual(ligne.pause_fin.strftime('%H:%M'), '13:30')
        self.assertEqual(ligne.motif, 'Bornes du référentiel appliquées.')
        self.assertEqual(ligne.modifie_par, self.direction)

    def test_auteur_inconnu_refuse(self):
        with self.assertRaises(CommandError):
            self._regler('--activer', '--auteur', 'fantome')
        self.assertEqual(PolitiqueContraintesSouples.objects.count(), 0)

    # ── 5. Idempotence ──────────────────────────────────────────────────────
    def test_rejouer_la_meme_politique_ne_reecrit_pas_la_decision(self):
        self._regler('--activer', '--max-jour', '8', '--auteur', 'direction')
        premiere = PolitiqueContraintesSouples.charger()
        date_initiale, auteur_initial = premiere.modifie_le, premiere.modifie_par_id

        sortie = self._regler('--activer', '--max-jour', '8',
                              '--auteur', 'direction')
        seconde = PolitiqueContraintesSouples.charger()
        self.assertEqual(seconde.modifie_le, date_initiale)
        self.assertEqual(seconde.modifie_par_id, auteur_initial)
        self.assertIn('déjà enregistrée', sortie)

    def test_pause_affichee_en_heures_et_minutes(self):
        """« pause 735 – 810 » n'est pas une information lisible."""
        sortie = self._regler('--activer', '--pause', '11:45-13:30')
        self.assertIn('11:45 – 13:30', sortie)
        self.assertNotIn('735', sortie)

    def test_sans_pause_efface_la_pause_enregistree(self):
        self._regler('--activer', '--pause', '11:45-13:30')
        self.assertIsNotNone(PolitiqueContraintesSouples.charger().pause_debut)
        self._regler('--activer', '--sans-pause', motif='Aucune pause officielle.')
        ligne = PolitiqueContraintesSouples.charger()
        self.assertIsNone(ligne.pause_debut)
        self.assertIsNone(ligne.pause_fin)
        self.assertIsNone(ligne.en_politique()['pause_dejeuner'])

    def test_pause_et_sans_pause_ensemble_refuses(self):
        with self.assertRaises(CommandError):
            self._regler('--activer', '--pause', '11:45-13:30', '--sans-pause')

    # ── 6. Désactivation sans perte ─────────────────────────────────────────
    def test_desactiver_conserve_les_bornes_decidees(self):
        self._regler('--activer', '--max-consecutives', '3', '--max-jour', '7')
        self._regler('--desactiver', motif='Suspension temporaire.')
        ligne = PolitiqueContraintesSouples.charger()
        self.assertFalse(ligne.actives)
        self.assertEqual(ligne.max_heures_consecutives, 3.0)
        self.assertEqual(ligne.max_heures_par_jour, 7.0)
        self.assertEqual(ligne.motif, 'Suspension temporaire.')

    # ── 7. Effet réel ───────────────────────────────────────────────────────
    def test_la_politique_ecrite_pilote_le_moteur(self):
        self._regler('--activer', '--max-jour', '6')
        effectif = C.politique_effective()
        self.assertEqual(effectif['origine'], 'base')
        self.assertTrue(effectif['politique']['actives'])
        self.assertEqual(effectif['politique']['max_heures_par_jour'], 6)
