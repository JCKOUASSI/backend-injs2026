"""Identifiants d'entrée : une chaîne « 10 » n'est pas deux identifiants.

Défaut réel trouvé en exécutant la suite sur PostgreSQL. `affectations_planifiables`
faisait `list(groupe_ids)`. Or `generate_schedule(groupe_ids=str(pk))` — la forme
utilisée par les tests et par l'écran de génération — passait une chaîne :

    list('9')  == ['9']        → fonctionnait par accident ;
    list('10') == ['1', '0']   → aucun groupe trouvé.

Conséquence : dès qu'une clé de groupe dépassait 9, le moteur répondait
« AFFECTATIONS_PEDAGOGIQUES_VIDES » alors que les affectations existaient. Sur
SQLite la suite restait verte (les clés repartaient de 1 à chaque exécution) ;
sur PostgreSQL la séquence avance et le défaut est apparu. Le bug ne dépendait
donc pas de la base, seulement de la longueur de l'identifiant — c'est ce que
ces tests fixent, sans jamais dépendre de la valeur réelle des clés.
"""

from django.test import TestCase

from edts.moteur import besoins as B
from edts.moteur import generation as G
from edts.moteur.identifiants import normaliser_ids
from edts.tests.test_lot2_moteur import FabriqueLMD


class NormaliserIdsTests(TestCase):
    """Contrat de la normalisation, cas par cas."""

    def test_chaine_simple_un_seul_identifiant(self):
        self.assertEqual(normaliser_ids('10'), ['10'])

    def test_chaine_multiple(self):
        self.assertEqual(normaliser_ids('10,11'), ['10', '11'])
        self.assertEqual(normaliser_ids('10, 11 '), ['10', '11'])

    def test_entier(self):
        self.assertEqual(normaliser_ids(10), [10])

    def test_liste_mixte(self):
        self.assertEqual(normaliser_ids([10, '11']), [10, '11'])

    def test_liste_contenant_une_chaine_multiple(self):
        self.assertEqual(normaliser_ids(['10,11']), ['10', '11'])

    def test_valeurs_vides(self):
        self.assertIsNone(normaliser_ids(None))
        self.assertIsNone(normaliser_ids(''))
        self.assertIsNone(normaliser_ids([]))
        self.assertIsNone(normaliser_ids([None]))

    def test_type_invalide_refuse(self):
        with self.assertRaises(TypeError):
            normaliser_ids(object())


class GroupeIdsADeuxChiffresTests(TestCase):
    """Le cas qui a échoué : un identifiant à deux chiffres."""

    def setUp(self):
        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()
        self.f.creer_salle('Salle A', 'SALLE', 30)
        self.f.creer_creneaux(jours=('LUNDI',), heures=((8, 10), (10, 12)))
        self.groupe = self.f.creer_groupe()
        self.f.creer_affectation(volume=2, groupe=self.groupe)

    def _besoins(self, groupe_ids):
        return B.calculate_teaching_needs(
            annee_academique_id=self.f.annee.pk,
            ref_formation_id=self.f.cycle.pk,
            parcours_id=self.f.parcours.pk,
            niveau_id=self.f.niveau.pk,
            semestre_id=self.f.semestre.pk,
            groupe_ids=groupe_ids,
        )

    def test_chaîne_simple_trouve_les_affectations(self):
        resultat = self._besoins(str(self.groupe.pk))
        self.assertFalse(resultat.vide, f'motif : {resultat.motif_echec}')
        self.assertEqual(len(resultat.besoins), 1)

    def test_entier_trouve_les_affectations(self):
        self.assertFalse(self._besoins(self.groupe.pk).vide)

    def test_liste_trouve_les_affectations(self):
        self.assertFalse(self._besoins([self.groupe.pk]).vide)

    def test_identifiant_absent_ne_ramene_rien(self):
        """Contre-épreuve : la normalisation ne doit pas élargir le filtre."""
        self.assertTrue(self._besoins('999999').vide)

    def test_identifiant_a_deux_chiffres_explicitement(self):
        """On rejoue le cas exact : un groupe dont l'identifiant fait 2 chiffres.

        Le test ne suppose aucune valeur de séquence : il crée autant de groupes
        que nécessaire pour obtenir un identifiant ≥ 10, puis vérifie que ce
        groupe est bien planifié.
        """
        from scolarite.models import Groupe

        while self.groupe.pk < 10:
            self.groupe = self.f.creer_groupe(nom=f'L1-G{self.groupe.pk}-bis')
        self.assertGreaterEqual(self.groupe.pk, 10)
        self.f.creer_affectation(volume=2, groupe=self.groupe)

        resultat = self._besoins(str(self.groupe.pk))
        self.assertFalse(resultat.vide, f'motif : {resultat.motif_echec}')
        self.assertTrue(
            all(b.groupe_id == self.groupe.pk for b in resultat.besoins))
        self.assertEqual(Groupe.objects.filter(pk=self.groupe.pk).count(), 1)

    def test_generation_complete_avec_identifiant_a_deux_chiffres(self):
        while self.groupe.pk < 10:
            self.groupe = self.f.creer_groupe(nom=f'L1-G{self.groupe.pk}-bis')
        self.f.creer_affectation(volume=2, groupe=self.groupe)

        resultat = G.generate_schedule(
            annee_academique_id=self.f.annee.pk,
            ref_formation_id=self.f.cycle.pk,
            parcours_id=self.f.parcours.pk,
            niveau_id=self.f.niveau.pk,
            semestre_id=self.f.semestre.pk,
            groupe_ids=str(self.groupe.pk),
        )
        self.assertEqual(resultat.status, G.GENERATION_OK, resultat.motif_echec)
        self.assertGreaterEqual(resultat.metrics['seances_placees'], 1)


class MetricsToujoursCompletTests(TestCase):
    """Un échec précoce doit rester un résultat lisible, jamais un KeyError."""

    def setUp(self):
        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()

    def test_canevas_vide_expose_des_compteurs_a_zero(self):
        # Une affectation existe, mais AUCUN créneau : c'est bien le canevas
        # qui bloque (sinon le premier motif serait « affectations vides »).
        groupe = self.f.creer_groupe()
        self.f.creer_affectation(volume=2, groupe=groupe)
        resultat = G.generate_schedule(
            annee_academique_id=self.f.annee.pk,
            ref_formation_id=self.f.cycle.pk,
            groupe_ids=str(groupe.pk),
        )
        self.assertEqual(resultat.status, G.GENERATION_IMPOSSIBLE)
        self.assertEqual(resultat.motif_echec, G.MOTIF_CANEVAS_VIDE)
        # Les clés attendues par l'API et le bilan annuel existent.
        for cle in ('seances_attendues', 'seances_placees', 'seances_non_placees',
                    'heures_placees', 'taux_couverture', 'score_penalites',
                    'contraintes_souples'):
            self.assertIn(cle, resultat.metrics)
        self.assertFalse(resultat.metrics['contraintes_souples']['active'])

    def test_aucune_affectation_expose_aussi_ses_compteurs(self):
        resultat = G.generate_schedule(annee_academique_id=self.f.annee.pk)
        self.assertEqual(resultat.status, G.GENERATION_IMPOSSIBLE)
        self.assertEqual(resultat.metrics['seances_placees'], 0)
        self.assertEqual(resultat.metrics['taux_couverture'], 0.0)
        self.assertEqual(resultat.metrics['finalite'], resultat.finalite)
