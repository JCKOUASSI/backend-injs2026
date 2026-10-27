"""Lot L1 (GET-INJS) — Tests de non-regression du moteur et de la publication.

Couvre les scenarios LOT 1 :

1. C4 durci : salle sans capacite + groupe avec effectif connu = blocage.
2. C4 durci : salle avec capacite suffisante = placement autorise.
3. FINALITE_COMPLETE -> GENERATION_OK quand tout est place.
4. FINALITE_PARTIAL -> GENERATION_PARTIELLE (impasse, budget non epuise).
5. FINALITE_IMPOSSIBLE -> GENERATION_IMPOSSIBLE (blocage demonstre, pas de placement).
6. FINALITE_BUDGET_EXHAUSTED -> GENERATION_PARTIELLE (budget de recherche epuise).
6bis. Refus precoce (canevas vide) -> finalite IMPOSSIBLE (metrics vides).
7. Metriques de diagnostic : budget_configured, budget_restant,
   nb_placements_effectues, finalite.
8. conflits_inter_edt : aucun conflit -> OK.
9. conflits_inter_edt : conflit C1 (enseignant partage) -> CONFLITS.
10. conflits_inter_edt : conflit C2 (groupe partage) -> CONFLITS.
11. conflits_inter_edt : conflit C3 (salle partagee) -> CONFLITS.
12. conflits_inter_edt : EDT sans affectation -> DONNEE_INCONNUE.
13. conflits_inter_edt : liste vide -> OK.
14. Publication refuse un plan incomplet (MOTIF_PLAN_INCOMPLET).
15. Publication force publie malgré un plan incomplet (force=True).

Ces tests construisent leurs propres donnees dans la base de test Django
(TestCase — transaction annulee en fin de test).
"""

from datetime import time

from django.test import TestCase

from formations.models import RefBatiment, RefFormation, RefSalle, RefSite
from formations.referentiel_injs_l6 import SOURCE_A45
from edts.models import (
    AffectationCreneau, CreneauTemplate, DisponibiliteHoraire, EmploiDuTemps,
)
from edts.moteur import contraintes as C
from edts.moteur import generation as G
from edts.moteur import publication as P
from edts.services import conflits_inter_edt
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, Groupe, Maquette, Niveau,
    Parcours, Semestre, UE,
)


class FabriqueL1:
    """Constructeur de donnees de test — chaque test est autonome."""

    def __init__(self, testcase):
        self.tc = testcase

    def creer_base(self, perimetre='INJS', filiere='F01', suffixe=''):
        self.annee, _ = AnneeAcademique.objects.get_or_create(
            libelle='2026-2027',
            defaults={'date_debut': '2026-10-01', 'date_fin': '2027-06-30'},
        )
        self.cycle = RefFormation.objects.create(
            intitule=f'FORMATION TEST {perimetre}{suffixe}', perimetre=perimetre,
            filiere_code=filiere, source=SOURCE_A45,
        )
        self.niveau, _ = Niveau.objects.get_or_create(
            code='L1', defaults={'libelle': 'Licence 1', 'cycle': 'LICENCE',
                                 'ordre': 1, 'credits_requis': 60},
        )
        self.semestre, _ = Semestre.objects.get_or_create(
            niveau=self.niveau, numero=1, defaults={'libelle': 'S1'},
        )
        self.parcours = Parcours.objects.create(
            code=f'P{suffixe or "1"}', intitule='Parcours test',
            ref_formation=self.cycle,
        )
        self.formateur, _ = __import__('formations.models', fromlist=['Formateur']).Formateur.objects.get_or_create(
            nom='Traoré', prenom='Awa',
        )
        self.site, _ = RefSite.objects.get_or_create(nom=f'SITE TEST{suffixe}')
        self.batiment, _ = RefBatiment.objects.get_or_create(
            site=self.site, nom=f'B{suffixe or "1"}',
        )
        return self

    def creer_maquette(self):
        maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.cycle,
            parcours=self.parcours, niveau=self.niveau,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=self.semestre, code='UE1',
            intitule='UE test', credits=10,
        )
        ecue = ECUE.objects.create(
            ue=ue, code='ECUE1', intitule='ECUE test', credits=4,
        )
        self.maquette, self.ue, self.ecue = maquette, ue, ecue
        return maquette, ue, ecue

    def creer_groupe(self, nom='L1-G1', capacite=30):
        return Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.cycle,
            parcours=self.parcours, niveau=self.niveau, nom=nom,
            capacite_max=capacite,
        )

    def creer_affectation(self, volume=4, type_ens='CM', groupe=None,
                          statut='VALIDEE'):
        return AffectationPedagogique.objects.create(
            annee_academique=self.annee,
            ref_formation=self.cycle,
            parcours=self.parcours,
            niveau=self.niveau,
            semestre=self.semestre,
            ue=self.ue, ecue=self.ecue, groupe=groupe,
            enseignant=self.formateur,
            type_enseignement=type_ens, volume_horaire=volume, statut=statut,
        )

    def creer_creneaux(self, jours=('LUNDI', 'MARDI'),
                       heures=((8, 10), (10, 12))):
        crees = []
        for jour in jours:
            for debut, fin in heures:
                crees.append(CreneauTemplate.objects.create(
                    jour=jour, heure_debut=time(debut, 0), heure_fin=time(fin, 0),
                ))
        return crees

    def creer_salle(self, nom='Salle A', type_lieu='SALLE', capacite=30):
        return RefSalle.objects.create(
            site=self.site, batiment=self.batiment, nom=nom,
            type_lieu=type_lieu, capacite=capacite,
        )


class TestC4Durci(TestCase):
    """Scenario 1-2 : C4 durci — capacite inconnue + effectif connu = bloquant."""

    def setUp(self):
        self.f = FabriqueL1(self).creer_base()
        self.f.creer_maquette()
        self.f.creer_creneaux(jours=('LUNDI',), heures=((8, 10),))
        self.groupe = self.f.creer_groupe()
        self.salle_sans_capacite = self.f.creer_salle('Sans Cap', 'SALLE', None)
        self.salle_avec_capacite = self.f.creer_salle('Avec Cap', 'SALLE', 30)

    def test_salle_sans_capacite_bloque_quand_effectif_connu(self):
        """C4 : salle.capacite None + groupe.capacite_max connu → refusée."""
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = G.generate_schedule(
            annee_academique_id=self.f.annee.pk,
            salles=[self.salle_sans_capacite],
        )
        self.assertEqual(r.status, G.GENERATION_IMPOSSIBLE)
        self.assertTrue(r.non_places)
        self.assertEqual(len(r.placements), 0)

    def test_salle_avec_capacite_suffisante_est_acceptee(self):
        """C4 : salle.capacite >= groupe.capacite_max → placement autorisé."""
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = G.generate_schedule(
            annee_academique_id=self.f.annee.pk,
            salles=[self.salle_avec_capacite],
        )
        self.assertEqual(r.status, G.GENERATION_OK)
        self.assertEqual(len(r.placements), 1)



class TestFinalite(TestCase):
    """Scenario 3-6 : classification de la fin de recherche (etape P)."""

    def setUp(self):
        self.f = FabriqueL1(self).creer_base()
        self.f.creer_maquette()
        self.creneaux = self.f.creer_creneaux(
            jours=('LUNDI', 'MARDI', 'MERCREDI'),
            heures=((8, 10), (10, 12)),
        )
        self.groupe = self.f.creer_groupe()
        self.groupe2 = self.f.creer_groupe(nom='L1-G2', capacite=30)
        self.salle = self.f.creer_salle('Salle A', 'SALLE', 30)
        self.salle2 = self.f.creer_salle('Salle B', 'SALLE', 30)

    def _generer(self, salles=None, budget=G.BUDGET_PLACEMENTS_DEFAUT):
        params = dict(
            annee_academique_id=self.f.annee.pk,
            salles=salles if salles is not None else [self.salle, self.salle2],
            budget=budget,
        )
        return G.generate_schedule(**params)

    def test_finalite_complete_quand_tout_place(self):
        """Scenario 3 : tous les besoins places -> COMPLETE / OK."""
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        self.f.creer_affectation(volume=2, groupe=self.groupe2)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_OK)
        self.assertEqual(r.finalite, G.FINALITE_COMPLETE)
        self.assertEqual(r.metrics['finalite'], G.FINALITE_COMPLETE)
        self.assertEqual(r.metrics['taux_couverture'], 100.0)

    def test_finalite_budget_exhauste_quand_budget_epuise(self):
        """Scenario 4 : budget de recherche epuise -> BUDGET_EXHAUSTED / PARTIELLE.

        Le solveur est « tout ou rien » : avec 2 besoins et un budget de 1,
        il explore le premier, epuise le budget, et renvoie None.
        """
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        self.f.creer_affectation(volume=2, groupe=self.groupe2)
        r = self._generer(budget=1)
        self.assertEqual(r.status, G.GENERATION_PARTIELLE)
        self.assertEqual(r.finalite, G.FINALITE_BUDGET_EXHAUSTED)
        self.assertEqual(r.metrics['finalite'], G.FINALITE_BUDGET_EXHAUSTED)
        self.assertEqual(r.metrics['budget_configured'], 1)
        self.assertEqual(len(r.placements), 0)
        self.assertTrue(r.non_places)

    def test_finalite_impossible_quand_blocage_démontré(self):
        """Scenario 5 : aucun placement possible, budget non epuise -> IMPOSSIBLE."""
        RefSalle.objects.all().delete()
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self._generer(salles=[])
        self.assertEqual(r.status, G.GENERATION_IMPOSSIBLE)
        self.assertEqual(r.finalite, G.FINALITE_IMPOSSIBLE)
        self.assertEqual(r.metrics['finalite'], G.FINALITE_IMPOSSIBLE)
        self.assertEqual(len(r.placements), 0)
        self.assertTrue(r.non_places)

    def test_metriques_diagnostic_presentes(self):
        """Scenario 6 : budget_configured, budget_restant, nb_placements_effectues, finalite."""
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self._generer(budget=500)
        self.assertIn('budget_configured', r.metrics)
        self.assertIn('budget_restant', r.metrics)
        self.assertIn('nb_placements_effectues', r.metrics)
        self.assertIn('finalite', r.metrics)
        self.assertEqual(r.metrics['budget_configured'], 500)
        self.assertEqual(r.metrics['nb_placements_effectues'], len(r.placements))
        self.assertEqual(r.metrics['finalite'], G.FINALITE_COMPLETE)

    def test_finalite_impossible_sur_refus_prealable(self):
        """Refus précoce (canevas vide) -> finalité IMPOSSIBLE côté dataclass.

        Sur les retours précoces, `metrics` reste vide (comportement LOT 2
        inchangé) : la classification est portée par `resultat.finalite`.
        """
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = G.generate_schedule(
            annee_academique_id=self.f.annee.pk,
            creneaux=[],
            salles=[self.salle],
        )
        self.assertEqual(r.status, G.GENERATION_IMPOSSIBLE)
        self.assertEqual(r.motif_echec, G.MOTIF_CANEVAS_VIDE)
        self.assertEqual(r.finalite, G.FINALITE_IMPOSSIBLE)



class TestConflitsInterEdt(TestCase):
    """Scenario 8-12 : controle de cohérence inter-EDT (lecture seule)."""

    def setUp(self):
        self.f = FabriqueL1(self).creer_base()
        self.f.creer_maquette()
        self.creneau = CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
        )
        self.groupe = self.f.creer_groupe()
        self.groupe_b = self.f.creer_groupe(nom='L1-G2')
        self.salle = self.f.creer_salle('Salle A', 'SALLE', 30)
        self.formateur = self.f.formateur
        self.formateur_b, _ = __import__('formations.models', fromlist=['Formateur']).Formateur.objects.get_or_create(
            nom='Kouassi', prenom='Jean',
        )

    def _edt(self, groupe=None, statut='BROUILLON'):
        return EmploiDuTemps.objects.create(
            annee_academique=self.f.annee,
            population_type='GROUPE',
            population_id=(groupe or self.groupe).pk,
            statut=statut,
        )

    def _seance(self, edt, creneau, salle=None, enseignant_id=None,
                groupe_id=None, semaine=1):
        return AffectationCreneau.objects.create(
            emploi_du_temps=edt,
            creneau_template=creneau,
            semaine_debut=semaine,
            semaine_fin=semaine,
            salle=salle,
            salle_nom=salle.nom if salle else '',
            groupe_id=groupe_id or self.groupe.pk,
            enseignant_id=enseignant_id or self.formateur.pk,
        )

    def test_aucun_conflit_retourne_OK(self):
        """Scenario 8 : deux EDT avec seances sur créneaux disjoints -> OK."""
        edt_a = self._edt()
        edt_b = self._edt(groupe=self.groupe_b)
        creneau_b = CreneauTemplate.objects.create(
            jour='MARDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
        )
        self._seance(edt_a, self.creneau, salle=self.salle)
        self._seance(edt_b, creneau_b, salle=self.salle)
        r = conflits_inter_edt([edt_a.pk, edt_b.pk])
        self.assertEqual(r['statut'], 'OK')
        self.assertEqual(r['conflits'], [])

    def test_conflit_c1_enseignant(self):
        """Scenario 9 : meme enseignant sur meme creneau, deux EDT -> CONFLITS C1."""
        edt_a = self._edt()
        edt_b = self._edt(groupe=self.groupe_b)
        self._seance(edt_a, self.creneau, salle=self.salle,
                     enseignant_id=self.formateur.pk)
        self._seance(edt_b, self.creneau, salle=self.salle,
                     enseignant_id=self.formateur.pk)
        r = conflits_inter_edt([edt_a.pk, edt_b.pk])
        self.assertEqual(r['statut'], 'CONFLITS')
        self.assertEqual(len(r['conflits']), 1)
        self.assertEqual(r['conflits'][0]['type_conflit'], 'C1_CONFLIT_ENSEIGNANT')
        self.assertEqual(r['detail']['affectations_analyses'], 2)

    def test_conflit_c2_groupe(self):
        """Scenario 10 : meme groupe sur meme creneau, deux EDT -> CONFLITS C2."""
        edt_a = self._edt()
        edt_b = self._edt(groupe=self.groupe_b)
        self._seance(edt_a, self.creneau, salle=self.salle,
                     enseignant_id=self.formateur.pk,
                     groupe_id=self.groupe.pk)
        self._seance(edt_b, self.creneau, salle=self.salle,
                     enseignant_id=self.formateur_b.pk,
                     groupe_id=self.groupe.pk)
        r = conflits_inter_edt([edt_a.pk, edt_b.pk])
        self.assertEqual(r['statut'], 'CONFLITS')
        self.assertEqual(r['conflits'][0]['type_conflit'], 'C2_CONFLIT_GROUPE')

    def test_conflit_c3_salle(self):
        """Scenario 11 : meme salle sur meme creneau, deux EDT -> CONFLITS C3."""
        edt_a = self._edt()
        edt_b = self._edt(groupe=self.groupe_b)
        self._seance(edt_a, self.creneau, salle=self.salle,
                     enseignant_id=self.formateur.pk,
                     groupe_id=self.groupe.pk)
        self._seance(edt_b, self.creneau, salle=self.salle,
                     enseignant_id=self.formateur_b.pk,
                     groupe_id=self.groupe_b.pk)
        r = conflits_inter_edt([edt_a.pk, edt_b.pk])
        self.assertEqual(r['statut'], 'CONFLITS')
        self.assertEqual(r['conflits'][0]['type_conflit'], 'C3_CONFLIT_SALLE')

    def test_edt_sans_affectation_retourne_DONNEE_INCONNUE(self):
        """Scenario 12 : un EDT sans affectation -> DONNEE_INCONNUE (pas de conflit)."""
        edt_a = self._edt()
        edt_vide = self._edt(groupe=self.groupe_b)  # aucune affectation
        self._seance(edt_a, self.creneau, salle=self.salle)
        r = conflits_inter_edt([edt_a.pk, edt_vide.pk])
        self.assertEqual(r['statut'], 'DONNEE_INCONNUE')
        self.assertIn(edt_vide.pk, r['detail']['edt_sans_affectation'])

    def test_liste_vide_retourne_OK(self):
        """Scenario 13 : aucun EDT a croiser -> OK."""
        r = conflits_inter_edt([])
        self.assertEqual(r['statut'], 'OK')
        self.assertEqual(r['conflits'], [])



class TestPublicationSecurisee(TestCase):
    """Scenario 14-15 : refus de plan incomplet et force a la publication."""

    def setUp(self):
        self.f = FabriqueL1(self).creer_base()
        self.f.creer_maquette()
        self.f.creer_creneaux(jours=('LUNDI',), heures=((8, 10),))
        self.groupe = self.f.creer_groupe()
        self.salle = self.f.creer_salle('Salle A', 'SALLE', 30)
        self.formateur = self.f.formateur
        self.affectation1 = self.f.creer_affectation(volume=2, groupe=self.groupe)
        self.affectation2 = self.f.creer_affectation(volume=2, groupe=self.groupe)
        self.edt = EmploiDuTemps.objects.create(
            annee_academique=self.f.annee,
            population_type='GROUPE',
            population_id=self.groupe.pk,
            statut='BROUILLON',
        )
        # Une seule seence placee sur les deux attendues -> plan incomplet.
        AffectationCreneau.objects.create(
            emploi_du_temps=self.edt,
            creneau_template=CreneauTemplate.objects.first(),
            semaine_debut=1, semaine_fin=1,
            salle=self.salle, salle_nom=self.salle.nom,
            affectation_pedagogique=self.affectation1,
            groupe=self.groupe,
            enseignant_id=self.formateur.pk,
        )

    def test_publication_refuse_plan_incomplet(self):
        """Scenario 14 : besoins attendus > seances placees -> MOTIF_PLAN_INCOMPLET."""
        besoins = [self.affectation1, self.affectation2]
        r = P.publier_emploi_du_temps(
            self.edt.pk, besoins_attendus=besoins,
        )
        self.assertFalse(r['publie'])
        self.assertEqual(r['motif_echec'], P.MOTIF_PLAN_INCOMPLET)
        self.assertEqual(self.edt.statut, 'BROUILLON', 'Aucun effet de bord.')

    def test_publication_force_accepte_plan_incomplet(self):
        """Scenario 15 : force=True publie malgré un plan incomplet."""
        besoins = [self.affectation1, self.affectation2]
        r = P.publier_emploi_du_temps(
            self.edt.pk, besoins_attendus=besoins, force=True,
        )
        self.assertTrue(r['publie'], r)
        self.edt.refresh_from_db()
        self.assertEqual(self.edt.statut, 'PUBLIE')
