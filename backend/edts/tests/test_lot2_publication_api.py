"""Lot 2 (GET-INJS) — Raccordement du contrôle de complétude à l'API de publication.

Le moteur refusait déjà un plan incomplet (``MOTIF_PLAN_INCOMPLET``, LOT 1) mais
``publish_api`` ne transmettait pas les besoins attendus : le contrôle était
inerte sur le parcours API normal. Le LOT 2 le rend effectif en dérivant le
périmètre attendu de la population déclarée de l'EDT (jamais de la requête).

Scénarios :

16. Plan incomplet (GROUPE)  -> 409 MOTIF_PLAN_INCOMPLET, controle APPLIQUE.
17. Plan complet (GROUPE)    -> 200 publie=True, controle APPLIQUE.
18. EDT sans seance mais perimetre avec besoins -> 409 PLAN_INCOMPLET
    (le controle s'applique avant AUCUNE_AFFECTATION_A_PUBLIER).
19. EDT vide sans besoin calculable -> refus historique
    AUCUNE_AFFECTATION_A_PUBLIER preserve, controle NON_APPLICABLE.
20. Population ENSEIGNANT    -> publication sans controle (aucun besoin
    invente), controle_completude NON_APPLICABLE + motif explicite.
21. EDT introuvable -> 404, aucun effet de bord.

Ces tests passent par la route reelle ``POST /api/edts/lmd/{id}/publish/`` et
construisent leurs propres donnees (TestCase — transaction annulee en fin de
test). La base de developpement n'est jamais touchee.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from edts.models import AffectationCreneau, EmploiDuTemps
from edts.tests.test_lot1_moteur import FabriqueL1


class BasePublicationAPI(TestCase):
    """Fabrique partagee — meme socle que le moteur LOT 1, mais via l'API."""

    def setUp(self):
        self.client_api = APIClient()
        self.f = FabriqueL1(self).creer_base()
        self.f.creer_maquette()
        self.creneau1, self.creneau2 = self.f.creer_creneaux(
            jours=('LUNDI',), heures=((8, 10), (10, 12)))
        self.groupe = self.f.creer_groupe()
        self.salle = self.f.creer_salle('Salle A', 'SALLE', 30)
        # 2h de volume sur un canevas de 2h -> 1 seance attendue par affectation.
        self.affectation1 = self.f.creer_affectation(volume=2, groupe=self.groupe)
        self.affectation2 = self.f.creer_affectation(volume=2, groupe=self.groupe)
        U = get_user_model()
        self.direction = U.objects.create_user(username='dir_lot2', password='x')
        self.direction.role = 'DIRECTION'
        self.direction.save()
        self.client_api.force_authenticate(user=self.direction)

    def _edt(self, population_type='GROUPE', population_id=None):
        return EmploiDuTemps.objects.create(
            annee_academique=self.f.annee,
            population_type=population_type,
            population_id=(population_id if population_id is not None
                           else self.groupe.pk),
            statut='BROUILLON', semaine_debut=1, semaine_fin=10,
        )

    def _seance(self, edt, creneau, affectation):
        return AffectationCreneau.objects.create(
            emploi_du_temps=edt, creneau_template=creneau,
            semaine_debut=1, semaine_fin=1,
            salle=self.salle, salle_nom=self.salle.nom,
            affectation_pedagogique=affectation,
            groupe=self.groupe, enseignant_id=self.f.formateur.pk,
        )

    def _publier(self, edt):
        return self.client_api.post(f'/api/edts/lmd/{edt.pk}/publish/')


class TestPublicationAPIPlanIncomplet(BasePublicationAPI):
    """Scénarios 16 et 18 : le parcours API refuse un plan incomplet."""

    def test_api_refuse_un_plan_incomplet(self):
        """Scenario 16 : 1 seance placee sur 2 attendues -> 409 PLAN_INCOMPLET."""
        edt = self._edt()
        self._seance(edt, self.creneau1, self.affectation1)
        r = self._publier(edt)
        self.assertEqual(r.status_code, 409, r.content)
        corps = r.json()
        self.assertFalse(corps['publie'])
        self.assertEqual(corps['motif_echec'], 'PLAN_INCOMPLET')
        self.assertEqual(corps['controle_completude']['statut'], 'APPLIQUE')
        couverture = corps['detail']['couverture']
        self.assertEqual(couverture['seances_attendues'], 2)
        self.assertEqual(couverture['seances_planifiees'], 1)
        self.assertEqual(couverture['seances_non_placees'], 1)

    def test_plan_incomplet_ne_publie_aucune_seance(self):
        """Scenario 16bis : aucun effet de bord — le refus ne publie rien."""
        edt = self._edt()
        self._seance(edt, self.creneau1, self.affectation1)
        r = self._publier(edt)
        self.assertEqual(r.status_code, 409, r.content)
        edt.refresh_from_db()
        self.assertEqual(edt.statut, 'BROUILLON', 'Aucune publication partielle.')
        self.assertIsNone(edt.publie_le)
        self.assertIsNone(edt.publie_par)
        self.assertIsNone(edt.valide_le)

    def test_api_edt_sans_seance_avec_perimetre_est_incomplet(self):
        """Scenario 18 : 0 seance placee sur 2 attendues -> PLAN_INCOMPLET.

        Le contrôle de complétude s'applique avant ``AUCUNE_AFFECTATION_A_PUBLIER``
        : un EDT vide au sein d'un périmètre qui attend des séances est un plan
        incomplet, pas une simple absence de contenu.
        """
        edt = self._edt()  # aucune seance placee
        r = self._publier(edt)
        self.assertEqual(r.status_code, 409, r.content)
        corps = r.json()
        self.assertEqual(corps['motif_echec'], 'PLAN_INCOMPLET')
        self.assertEqual(corps['detail']['couverture']['seances_non_placees'], 2)
        edt.refresh_from_db()
        self.assertEqual(edt.statut, 'BROUILLON')


class TestPublicationAPIPlanComplet(BasePublicationAPI):
    """Scénario 17 : le parcours API publie un plan complet."""

    def test_api_publie_un_plan_complet(self):
        """Scenario 17 : 2 seances placees sur 2 attendues -> 200 publie."""
        edt = self._edt()
        self._seance(edt, self.creneau1, self.affectation1)
        self._seance(edt, self.creneau2, self.affectation2)
        r = self._publier(edt)
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertTrue(corps['publie'], corps)
        self.assertEqual(corps['controle_completude']['statut'], 'APPLIQUE')
        self.assertEqual(corps['detail']['couverture']['seances_non_placees'], 0)
        edt.refresh_from_db()
        self.assertEqual(edt.statut, 'PUBLIE')
        self.assertIsNotNone(edt.publie_le)
        self.assertEqual(edt.publie_par_id, self.direction.pk)


class TestPublicationAPIDonneesManquantes(BasePublicationAPI):
    """Scénarios 19 et 20 : jamais de besoin inventé, contrôle non applicable."""

    def test_api_edt_vide_sans_besoins_garde_le_refus_historique(self):
        """Scenario 19 : perimetre sans affectation -> AUCUNE_AFFECTATION.

        Le contrôle de complétude ne peut pas s'appliquer (aucun besoin
        calculable) : le refus historique est preserve et l'etat est explicite.
        """
        from formations.models import RefFormation
        from formations.referentiel_injs_l6 import SOURCE_A45

        cycle_sans_besoin = RefFormation.objects.create(
            intitule='CYCLE INJS TEST SANS AFFECTATION', perimetre='INJS',
            filiere_code='F01', source=SOURCE_A45)
        edt = EmploiDuTemps.objects.create(
            annee_academique=self.f.annee, population_type='FORMATION',
            population_id=cycle_sans_besoin.pk, statut='BROUILLON',
            semaine_debut=1, semaine_fin=10,
        )
        r = self._publier(edt)
        self.assertEqual(r.status_code, 409, r.content)
        corps = r.json()
        self.assertEqual(corps['motif_echec'], 'AUCUNE_AFFECTATION_A_PUBLIER')
        self.assertEqual(corps['controle_completude']['statut'], 'NON_APPLICABLE')
        self.assertEqual(
            corps['controle_completude']['motif_non_applicabilite'],
            'AFFECTATIONS_PEDAGOGIQUES_VIDES')

    def test_api_population_enseignant_controle_non_applicable(self):
        """Scenario 20 : EDT ENSEIGNANT -> publication sans controle.

        Un EDT ciblant un enseignant est une vue croisée : le referentiel LMD
        ne definit pas son perimetre de besoins, aucun besoin n'est donc
        invente et l'etat NON_APPLICABLE est retourne au client.
        """
        edt = self._edt('ENSEIGNANT', self.f.formateur.pk)
        self._seance(edt, self.creneau1, self.affectation1)
        r = self._publier(edt)
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertTrue(corps['publie'], corps)
        self.assertEqual(corps['controle_completude']['statut'], 'NON_APPLICABLE')
        self.assertEqual(
            corps['controle_completude']['motif_non_applicabilite'],
            'POPULATION_SANS_PERIMETRE')

    def test_api_edt_introuvable_renvoie_404(self):
        """Scenario 21 : publication d'un EDT inexistant -> 404."""
        r = self.client_api.post('/api/edts/lmd/999999/publish/')
        self.assertEqual(r.status_code, 404)
