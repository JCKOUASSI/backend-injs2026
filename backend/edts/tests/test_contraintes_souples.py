"""Contraintes SOUPLES (étape K) — configurables, désactivées par défaut.

Ce que ces tests garantissent :

1. **Défaut inactif** : sans activation explicite, le solveur produit des
   pénalités identiques à avant l'introduction des règles souples. C'est ce qui
   protège les 456 tests existants et les mesures de charge déjà publiées.
2. **Activation réelle** : quand la politique est active, un trou, une série
   trop longue et une journée surchargée produisent bien les pénalités
   attendues, avec le poids configuré.
3. **Jamais bloquant** : une pénalité ne retire jamais un placement.
4. **Configuration stricte** : une clé inconnue ou un type invalide lève une
   erreur explicite — un réglage mal orthographié ne doit pas être ignoré.
"""

from datetime import time

from django.test import TestCase, override_settings

from edts.moteur import contraintes as C


def _index(*plages, prefixe='G', ressource=1, jour='LUNDI'):
    """Index d'occupations minimal, au format produit par le solveur."""
    index = {}
    for debut, fin in plages:
        index.setdefault((prefixe, ressource, jour), []).append((debut, fin))
    return index


class PolitiqueSouplesTests(TestCase):
    """Politique effective : défauts, priorités, validation."""

    def test_defaut_desactive(self):
        politique = C.politique_souples()
        self.assertFalse(politique['actives'])
        self.assertEqual(politique['max_heures_consecutives'], 4.0)
        self.assertEqual(politique['max_heures_par_jour'], 8.0)
        self.assertEqual(politique['tolerance_minutes'], 15)

    @override_settings(EDTS_CONTRAINTES_SOUPLES={'actives': True,
                                                'max_heures_consecutives': 3})
    def test_reglage_django_pris_en_compte(self):
        politique = C.politique_souples()
        self.assertTrue(politique['actives'])
        self.assertEqual(politique['max_heures_consecutives'], 3)
        # Les autres valeurs restent celles par défaut.
        self.assertEqual(politique['max_heures_par_jour'], 8.0)

    @override_settings(EDTS_CONTRAINTES_SOUPLES={'actives': True,
                                                'max_heures_consecutives': 3})
    def test_parametre_explicite_prioritaire_sur_le_reglage(self):
        politique = C.politique_souples({'max_heures_consecutives': 2})
        self.assertEqual(politique['max_heures_consecutives'], 2)
        self.assertTrue(politique['actives'])

    def test_cle_inconnue_refusee(self):
        with self.assertRaises(ValueError) as ctx:
            C.politique_souples({'active': True})  # « actives » mal orthographié
        self.assertIn('active', str(ctx.exception))
        self.assertIn('actives', str(ctx.exception))

    def test_type_invalide_refuse(self):
        with self.assertRaises(ValueError):
            C.politique_souples({'actives': 'oui'})
        with self.assertRaises(ValueError):
            C.politique_souples({'max_heures_consecutives': 'quatre'})
        with self.assertRaises(ValueError):
            C.politique_souples({'max_heures_consecutives': -1})

    def test_source_non_dict_refusee(self):
        with self.assertRaises(ValueError):
            C.politique_souples(['actives'])


class PenalitesSouplesTests(TestCase):
    """Calcul des trois règles souples, sur des journées réalistes."""

    def setUp(self):
        self.actif = {'actives': True}

    def test_inactif_ne_produit_rien(self):
        index = _index((time(8, 0), time(10, 0)))
        penalites = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(16, 0), heure_fin=time(18, 0),
            politique=C.politique_souples())
        self.assertEqual(penalites, [])

    def test_trou_detecte_avec_le_poids_configure(self):
        # 08:00–10:00 déjà posé, candidat 16:00–18:00 : 6 h d'attente.
        index = _index((time(8, 0), time(10, 0)))
        penalites = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(16, 0), heure_fin=time(18, 0),
            politique=C.politique_souples(self.actif))
        codes = {p.code: p.poids for p in penalites}
        self.assertEqual(codes.get('TROU_HORAIRE'), 1)
        # 4 h au total : sous le seuil de 8 h, aucune surcharge.
        self.assertNotIn('SURCHARGE_JOURNALIERE', codes)
        # Deux séances séparées : aucune série de plus de 4 h.
        self.assertNotIn('PLUS_DE_X_HEURES_CONSECUTIVES', codes)

    def test_journee_normale_sans_penalite(self):
        # 08:00–10:00, 10:15–12:15 (récréation de 15 min), 13:30–15:30.
        # La pause déjeuner est déclarée : ce n'est pas un trou pédagogique.
        index = _index((time(8, 0), time(10, 0)), (time(10, 15), time(12, 15)))
        penalites = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(13, 30), heure_fin=time(15, 30),
            politique=C.politique_souples({
                'actives': True, 'pause_dejeuner': ('12:15', '13:30')}))
        self.assertEqual([p.code for p in penalites], [])

    def test_meme_journee_sans_pause_declaree_signale_le_trou(self):
        # Sans pause configurée, l'écart de 1 h 15 est compté comme un trou :
        # le moteur n'invente aucune exemption. C'est explicite et testé.
        index = _index((time(8, 0), time(10, 0)), (time(10, 15), time(12, 15)))
        penalites = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(13, 30), heure_fin=time(15, 30),
            politique=C.politique_souples(self.actif))
        self.assertIn('TROU_HORAIRE', [p.code for p in penalites])

    def test_pause_invalide_refusee(self):
        with self.assertRaises(ValueError):
            C.politique_souples({'pause_dejeuner': ('13:30', '12:15')})
        with self.assertRaises(ValueError):
            C.politique_souples({'pause_dejeuner': '12:15-13:30'})
        with self.assertRaises(ValueError):
            C.politique_souples({'pause_dejeuner': ('25:00', '26:00')})

    def test_serie_trop_longue(self):
        # 4 séances de 2 h enchaînées = 6 h consécutives (seuil 4 h).
        index = _index((time(8, 0), time(10, 0)), (time(10, 0), time(12, 0)),
                       (time(12, 0), time(14, 0)))
        penalites = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(14, 0), heure_fin=time(16, 0),
            politique=C.politique_souples(self.actif))
        codes = {p.code for p in penalites}
        self.assertIn('PLUS_DE_X_HEURES_CONSECUTIVES', codes)

    def test_surcharge_journaliere(self):
        index = _index((time(7, 30), time(9, 30)), (time(9, 30), time(11, 30)),
                       (time(12, 0), time(14, 0)), (time(14, 0), time(16, 0)))
        penalites = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(16, 0), heure_fin=time(18, 0),
            politique=C.politique_souples(self.actif))
        codes = {p.code for p in penalites}
        self.assertIn('SURCHARGE_JOURNALIERE', codes)  # 10 h dans la journée

    def test_seuils_personnalises(self):
        # 08:00–10:00 déjà posé + candidat 10:00–12:00 = 4 h consécutives.
        index = _index((time(8, 0), time(10, 0)))
        penalites = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(10, 0), heure_fin=time(12, 0),
            politique=C.politique_souples({
                'actives': True, 'max_heures_consecutives': 2,
                'max_heures_par_jour': 4,
            }))
        codes = {p.code for p in penalites}
        # 4 h consécutives > seuil de 2 h → pénalité.
        self.assertIn('PLUS_DE_X_HEURES_CONSECUTIVES', codes)
        # 4 h dans la journée n'est PAS supérieur au seuil de 4 h : pas de
        # surcharge. Le seuil est un dépassement strict, pas une égalité.
        self.assertNotIn('SURCHARGE_JOURNALIERE', codes)

    def test_trou_desactive_par_la_politique(self):
        index = _index((time(8, 0), time(10, 0)))
        penalites = C.penalites_souples(
            index, prefixe='G', ressource=1, jour='LUNDI',
            heure_debut=time(16, 0), heure_fin=time(18, 0),
            politique=C.politique_souples({
                'actives': True, 'penaliser_trous': False}))
        self.assertNotIn('TROU_HORAIRE', [p.code for p in penalites])


class ResumeSouplesTests(TestCase):
    """Bilan d'un plan complet (lecture seule)."""

    def test_resume_inactif_vide(self):
        resume = C.resume_souples([])
        self.assertFalse(resume['active'])
        self.assertEqual(resume['trous'], 0)

    def test_resume_compte_les_ecarts(self):
        plan = [
            {'groupe_id': 1, 'jour': 'LUNDI', 'heure_debut': time(8, 0), 'heure_fin': time(10, 0)},
            {'groupe_id': 1, 'jour': 'LUNDI', 'heure_debut': time(16, 0), 'heure_fin': time(18, 0)},
        ]
        resume = C.resume_souples(plan, C.politique_souples({'actives': True}))
        self.assertTrue(resume['active'])
        self.assertEqual(resume['trous'], 1)
        self.assertEqual(resume['detail'][0]['ressource'], 'groupe 1')
        self.assertEqual(resume['detail'][0]['heures_jour'], 4.0)


class IntegrationGenerationTests(TestCase):
    """Le solveur réel : inactif par défaut, actif sur demande, jamais bloquant."""

    CODES = ('TROU_HORAIRE', 'PLUS_DE_X_HEURES_CONSECUTIVES',
             'SURCHARGE_JOURNALIERE')

    def setUp(self):
        from edts.tests.test_lot2_moteur import FabriqueLMD

        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()
        self.groupe = self.f.creer_groupe()
        self.salle = self.f.creer_salle('Salle A', 'SALLE', 30)
        self.f.creer_creneaux(jours=('LUNDI',), heures=((8, 10), (10, 12),
                                                       (14, 16), (16, 18)))
        # Deux ECUE distinctes sur le MÊME groupe : deux besoins qui devront
        # cohabiter sur la seule journée ouverte (LUNDI).
        from scolarite.models import ECUE, AffectationPedagogique

        self.ecue2 = ECUE.objects.create(
            ue=self.f.ue, code='ECUE2', intitule='ECUE test 2', credits=4)
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        AffectationPedagogique.objects.create(
            annee_academique=self.f.annee, ref_formation=self.f.cycle,
            parcours=self.f.parcours, niveau=self.f.niveau,
            semestre=self.f.semestre, ue=self.f.ue, ecue=self.ecue2,
            groupe=self.groupe, enseignant=self.f.formateur,
            type_enseignement='TD', volume_horaire=2, statut='VALIDEE',
        )

    def _generer(self, **extras):
        from edts.moteur import generation as G

        params = {
            'annee_academique_id': self.f.annee.pk,
            'ref_formation_id': self.f.cycle.pk,
            'parcours_id': self.f.parcours.pk,
            'niveau_id': self.f.niveau.pk,
            'semestre_id': self.f.semestre.pk,
            'groupe_ids': str(self.groupe.pk),
        }
        params.update(extras)
        return G.generate_schedule(**params)

    def _codes(self, resultat):
        return {p.code for place in resultat.placements for p in place.penalites}

    def test_defaut_inactif_aucune_penalite_souple(self):
        resultat = self._generer()
        bilan = resultat.metrics['contraintes_souples']
        self.assertFalse(bilan['active'])
        self.assertFalse(bilan['detail'])
        self.assertFalse(self._codes(resultat) & set(self.CODES))

    def test_activation_signale_la_journee_tendue_sans_rien_refuser(self):
        """Activer les règles ajoute des pénalités — jamais un refus."""
        temoin = self._generer()
        actif = self._generer(contraintes_souples={
            'actives': True, 'max_heures_consecutives': 2,
            'max_heures_par_jour': 3,
        })
        # Jamais bloquant : mêmes séances placées, aucun besoin écarté.
        self.assertEqual(actif.status, temoin.status)
        self.assertEqual(actif.metrics['seances_placees'],
                         temoin.metrics['seances_placees'])
        self.assertEqual(actif.non_places, [])
        # …mais la journée de 4 h est effectivement signalée.
        bilan = actif.metrics['contraintes_souples']
        self.assertTrue(bilan['active'])
        signale = (bilan['trous'] + bilan['series_trop_longues']
                   + bilan['journees_surchargees'])
        self.assertGreaterEqual(signale, 1)
        self.assertTrue(self._codes(actif) & set(self.CODES))
        # Le témoin, lui, reste vierge de toute pénalité souple.
        self.assertFalse(self._codes(temoin) & set(self.CODES))

    def test_reglage_django_active_la_politique(self):
        with override_settings(EDTS_CONTRAINTES_SOUPLES={'actives': True}):
            resultat = self._generer()
        self.assertTrue(resultat.metrics['contraintes_souples']['active'])
