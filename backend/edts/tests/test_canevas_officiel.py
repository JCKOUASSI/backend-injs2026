"""Le canevas officiel est une donnée de référence, pas une convention implicite.

Ces tests fixent la grille (6 jours × 4 plages = 24 créneaux de 2 h), la
détection des trois écarts (manquants, non prévus, chevauchements) et le
comportement de la commande de vérification.

Le cas réel qui a motivé ce contrôle : la base de démonstration contenait
14 créneaux aux plages hétérogènes (08:00–12:00, 14:00–17:00, 18:00–20:00…),
dont certains se chevauchaient — situation où les contrôles de conflit ne
peuvent plus être garantis.
"""

import io
import json
import os
import tempfile
from datetime import time

from django.core.management import call_command
from django.test import TestCase

from edts.moteur import canevas_officiel as O
from edts.models import CreneauTemplate


class GrilleOfficielleTests(TestCase):

    def test_taille_de_la_grille(self):
        self.assertEqual(len(O.JOURS_OFFICIELS), 6)
        self.assertEqual(len(O.PLAGES_OFFICIELLES), 4)
        self.assertEqual(O.nombre_officiel(), 24)
        self.assertEqual(len(O.grille_officielle()), 24)

    def test_chaque_plage_fait_deux_heures(self):
        for debut, fin in O.PLAGES_OFFICIELLES:
            minutes = (fin.hour * 60 + fin.minute) - (debut.hour * 60 + debut.minute)
            self.assertEqual(minutes, 120, f'{debut}–{fin} ne fait pas 2 h')

    def test_plages_dans_l_ordre_et_sans_recouvrement(self):
        precedente = None
        for debut, fin in O.PLAGES_OFFICIELLES:
            self.assertLess(debut, fin)
            if precedente is not None:
                self.assertLessEqual(precedente, debut)
            precedente = fin

    def test_grille_officielle_ne_se_chevauche_pas(self):
        self.assertEqual(O.chevauchements(O.grille_officielle()), [])


class PauseDeduiteTests(TestCase):
    """La pause déjeuner se DÉDUIT de la grille officielle, elle ne s'invente pas.

    Sans cette déduction, une journée 07:30–11:45 + 13:30–17:45 serait signalée
    comme trouée sur 1 h 45 : la règle souple produirait une pénalité sur le
    fonctionnement normal de l'établissement.
    """

    def test_intervalles_du_canevas(self):
        intervalles = O.interruptions()
        self.assertEqual(len(intervalles), 3)
        minutes = [item[2] for item in intervalles]
        self.assertEqual(minutes, [15, 105, 15])

    def test_pause_deduite_est_le_plus_long_intervalle(self):
        debut, fin = O.pause_deduite()
        self.assertEqual((debut.strftime('%H:%M'), fin.strftime('%H:%M')),
                         ('11:45', '13:30'))

    def test_la_pause_deduite_annule_le_faux_trou(self):
        """Preuve par le moteur : sans pause, la journée type est pénalisée."""
        from edts.moteur import contraintes as C

        index = {('G', 1, 'LUNDI'): [
            (time(7, 30), time(9, 30)), (time(9, 45), time(11, 45)),
            (time(13, 30), time(15, 30)),
        ]}
        sans_pause = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(13, 30), heure_fin=time(15, 30),
            politique=C.politique_souples({'actives': True}))
        self.assertIn('TROU_HORAIRE', [p.code for p in sans_pause])

        debut, fin = O.pause_deduite()
        avec_pause = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(13, 30), heure_fin=time(15, 30),
            politique=C.politique_souples({
                'actives': True,
                'pause_dejeuner': (debut.strftime('%H:%M'), fin.strftime('%H:%M')),
            }))
        self.assertNotIn('TROU_HORAIRE', [p.code for p in avec_pause])


class ComparaisonCanevasTests(TestCase):

    def test_grille_complete_est_conforme(self):
        rapport = O.comparer_canevas(O.grille_officielle())
        self.assertTrue(rapport['conforme'])
        self.assertEqual(rapport['manquants'], [])
        self.assertEqual(rapport['non_prevus'], [])
        self.assertEqual(rapport['chevauchements'], [])

    def test_creneau_manquant_signale(self):
        creneaux = O.grille_officielle()[1:]  # il manque le premier
        rapport = O.comparer_canevas(creneaux)
        self.assertFalse(rapport['conforme'])
        self.assertEqual(rapport['manquants'], ['LUNDI 07:30–09:30'])
        self.assertEqual(rapport['non_prevus'], [])

    def test_creneau_non_prevu_signale(self):
        creneaux = O.grille_officielle() + [('DIMANCHE', time(18, 0), time(20, 0))]
        rapport = O.comparer_canevas(creneaux)
        self.assertFalse(rapport['conforme'])
        self.assertEqual(rapport['non_prevus'], ['DIMANCHE 18:00–20:00'])

    def test_chevauchement_detecte(self):
        """Le cas réel : 08:00–12:00 contient 08:00–10:00."""
        creneaux = [('LUNDI', time(8, 0), time(12, 0)),
                    ('LUNDI', time(8, 0), time(10, 0))]
        paires = O.chevauchements(creneaux)
        self.assertEqual(len(paires), 1)
        # L'ordre dans la paire suit le tri par début puis par fin ; ce qui
        # compte est que les DEUX créneaux fautifs soient nommés.
        self.assertEqual(set(paires[0]),
                         {'LUNDI 08:00–10:00', 'LUNDI 08:00–12:00'})

    def test_creneaux_jointifs_ne_se_chevauchent_pas(self):
        creneaux = [('LUNDI', time(8, 0), time(10, 0)),
                    ('LUNDI', time(10, 0), time(12, 0))]
        self.assertEqual(O.chevauchements(creneaux), [])

    def test_chevauchement_entre_jours_differents_ignore(self):
        creneaux = [('LUNDI', time(8, 0), time(12, 0)),
                    ('MARDI', time(8, 0), time(10, 0))]
        self.assertEqual(O.chevauchements(creneaux), [])


class CommandeVerifierCanevasTests(TestCase):

    def _appeler(self, *options):
        sortie = io.StringIO()
        call_command('verifier_canevas', *options, stdout=sortie,
                     stderr=io.StringIO())
        return sortie.getvalue()

    def test_canevas_conforme_en_base(self):
        for jour, debut, fin in O.grille_officielle():
            CreneauTemplate.objects.create(jour=jour, heure_debut=debut,
                                           heure_fin=fin)
        sortie = self._appeler()
        self.assertIn('Canevas CONFORME', sortie)

    def test_canevas_vide_signale_les_24_manquants(self):
        sortie = self._appeler()
        self.assertIn('Manquants (24)', sortie)
        self.assertIn('Canevas NON conforme', sortie)

    def test_canevas_de_la_base_de_demonstration_signale_les_ecarts(self):
        """Reproduction du cas réel : plages hétérogènes et recouvrement."""
        for jour in ('LUNDI', 'MARDI'):
            CreneauTemplate.objects.create(jour=jour, heure_debut=time(8, 0),
                                           heure_fin=time(12, 0))
            CreneauTemplate.objects.create(jour=jour, heure_debut=time(8, 0),
                                           heure_fin=time(10, 0))
        sortie = self._appeler()
        self.assertIn('Chevauchements (2)', sortie)
        self.assertIn('Non prévus au référentiel', sortie)

    def test_creer_manquants_rend_le_canevas_conforme(self):
        sortie = self._appeler('--creer-manquants')
        self.assertIn('24 créneau(x) officiel(s) créé(s)', sortie)
        self.assertEqual(CreneauTemplate.objects.count(), 24)
        self.assertIn('Canevas CONFORME', sortie)

    def test_creer_manquants_ne_supprime_rien(self):
        ancien = CreneauTemplate.objects.create(
            jour='DIMANCHE', heure_debut=time(18, 0), heure_fin=time(20, 0))
        self._appeler('--creer-manquants')
        self.assertTrue(CreneauTemplate.objects.filter(pk=ancien.pk).exists())
        self.assertEqual(CreneauTemplate.objects.count(), 25)

    def test_rapport_json_ecrit(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, 'canevas.json')
            self._appeler('--json', chemin)
            with open(chemin, encoding='utf-8') as flux:
                rapport = json.load(flux)
        self.assertFalse(rapport['conforme'])
        self.assertEqual(rapport['attendus'], 24)
        self.assertEqual(len(rapport['manquants']), 24)
