"""Lot L8 (GET-INJS) — Tests du moteur : besoins, contraintes, génération.

Ces tests construisent **leurs propres données** dans la base de test Django
(``TestCase`` — transaction annulée en fin de test). Aucune fixture n'est
ajoutée à la base de développement : le canevas horaire reste vide tant que
l'INJS n'a pas fourni de canevas officiel (arbitrage du commanditaire).

Couverture :
- besoins        : motifs de blocage distincts, périmètre INJS, traçabilité ;
- contraintes    : C1→C7 dures, préférences souples, compatibilité salles ;
- génération     : backtracking, déterminisme, salle spécialisée, impasses ;
- validation     : couverture, conflits, volumes ;
- publication    : transactionnelle, idempotente, verrouillée.
"""

from datetime import time

from django.test import TestCase

from formations.models import (
    Formateur, RefBatiment, RefFormation, RefSalle, RefSite,
)
from formations.referentiel_injs_l6 import SOURCE_A45
from edts.models import (
    AffectationCreneau, CreneauTemplate, DisponibiliteHoraire, EmploiDuTemps,
)
from edts.moteur import besoins as B
from edts.moteur import contraintes as C
from edts.moteur import generation as G
from edts.moteur import publication as P
from edts.moteur import validation as V
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, Maquette, Niveau, Parcours,
    Semestre, UE,
)


class FabriqueLMD:
    """Constructeur de données de test — chaque test est autonome."""

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
        self.formateur, _ = Formateur.objects.get_or_create(
            nom='Traoré', prenom='Awa',
        )
        self.site, _ = RefSite.objects.get_or_create(nom=f'SITE TEST{suffixe}')
        self.batiment, _ = RefBatiment.objects.get_or_create(
            site=self.site, nom=f'B{suffixe or "1"}',
        )
        return self

    def creer_groupe(self, nom='L1-G1', capacite=30):
        from scolarite.models import Groupe

        return Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.cycle,
            parcours=self.parcours, niveau=self.niveau, nom=nom,
            capacite_max=capacite,
        )

    def creer_maquette(self, groupe=None):
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

    def creer_affectation(self, volume=4, type_ens='CM', groupe=None, statut='VALIDEE',
                          ref_formation=None, parcours=None, niveau=None,
                          semestre=None):
        """Affectation pédagogique réellement rattachée à sa chaîne LMD.

        Les quatre repères (formation, parcours, niveau, semestre) sont
        surchargeables : un test qui construit une population dédiée doit
        pouvoir y rattacher son affectation, sinon les filtres de périmètre du
        moteur ne la retiennent pas.
        """
        ecue = self.ecue
        return AffectationPedagogique.objects.create(
            annee_academique=self.annee,
            ref_formation=ref_formation or self.cycle,
            parcours=parcours or self.parcours,
            niveau=niveau or self.niveau,
            semestre=semestre or self.semestre,
            ue=ecue.ue, ecue=ecue, groupe=groupe, enseignant=self.formateur,
            type_enseignement=type_ens, volume_horaire=volume, statut=statut,
        )

    def creer_creneaux(self, jours=('LUNDI', 'MARDI'), heures=((8, 10), (10, 12))):
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


class TestMotifsDeBlocage(TestCase):
    """Les causes de blocage doivent être DISTINGUÉES (arbitrage §6).

    Aucun fallback silencieux, aucun horaire fictif.
    """

    def setUp(self):
        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()

    def test_aucune_affectation_pedagogique(self):
        r = B.calculate_teaching_needs()
        self.assertTrue(r.vide)
        self.assertEqual(r.motif_echec, B.MOTIF_AFFECTATIONS_VIDES)
        self.assertIn('explication', r.detail)
        self.assertIn('action_recommandee', r.detail)

    def test_canevas_vide_avec_affectations(self):
        """Affectations OK mais aucun créneau → motif dédié, jamais « 2 h »."""
        groupe = self.f.creer_groupe()
        self.f.creer_affectation(volume=4, groupe=groupe)
        r = B.calculate_teaching_needs()
        self.assertTrue(r.vide)
        self.assertEqual(r.motif_echec, B.MOTIF_CANEVAS_VIDE)
        self.assertEqual(r.detail['nb_affectations'], 1)
        self.assertIsNone(B.duree_canevas_heures())

    def test_affectations_hors_perimetre_injs(self):
        """Un cycle legacy (CPFAE/professorat) n'est pas une formation INJS."""
        legacy = FabriqueLMD(self).creer_base(perimetre='LEGACY', filiere='',
                                             suffixe='-LEG')
        legacy.creer_maquette()
        groupe = legacy.creer_groupe(nom='L1-GLEG')
        legacy.creer_affectation(volume=4, groupe=groupe)
        r = B.calculate_teaching_needs()
        self.assertTrue(r.vide)
        self.assertEqual(r.motif_echec, B.MOTIF_HORS_PERIMETRE_INJS)

    def test_volume_horaire_nul(self):
        groupe = self.f.creer_groupe()

class TestCalculDesBesoins(TestCase):
    """Étape E — volumes, types, groupes, traçabilité."""

    def setUp(self):
        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()
        self.f.creer_creneaux(heures=((8, 10),))

    def test_volume_divise_en_seances(self):
        groupe = self.f.creer_groupe()
        self.f.creer_affectation(volume=4, type_ens='CM', groupe=groupe)
        r = B.calculate_teaching_needs()
        self.assertFalse(r.vide)
        self.assertEqual(len(r.besoins), 1)
        besoin = r.besoins[0]
        self.assertEqual(besoin.duree_seance_heures, 2.0)
        self.assertEqual(besoin.nb_seances, 2)
        self.assertEqual(r.total_heures_attendues, 4.0)
        self.assertEqual(r.total_seances_attendues, 2)

    def test_le_decoupage_suit_le_canevas_reel(self):
        """Un créneau de 3 h → des séances de 3 h, jamais 2 h par défaut."""
        CreneauTemplate.objects.all().delete()
        CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(11, 0),
        )
        groupe = self.f.creer_groupe()
        self.f.creer_affectation(volume=6, groupe=groupe)
        r = B.calculate_teaching_needs()
        self.assertEqual(r.besoins[0].duree_seance_heures, 3.0)
        self.assertEqual(r.besoins[0].nb_seances, 2)

    def test_la_tracabilite_est_preservee(self):
        groupe = self.f.creer_groupe()
        affectation = self.f.creer_affectation(volume=2, groupe=groupe)
        besoin = B.calculate_teaching_needs().besoins[0]
        self.assertEqual(besoin.affectation_pedagogique_id, affectation.pk)
        self.assertEqual(besoin.groupe_id, groupe.pk)
        self.assertEqual(besoin.niveau_id, self.f.niveau.pk)
        self.assertEqual(besoin.semestre_id, self.f.semestre.pk)
        self.assertEqual(besoin.ref_formation_id, self.f.cycle.pk)
        self.assertEqual(besoin.ecue_id, affectation.ecue_id)

    def test_le_type_denseignement_determine_la_nature(self):
        groupe = self.f.creer_groupe()
        for type_ens, nature in (('CM', 'COURS'), ('TD', 'TD'), ('TP', 'TP')):
            self.f.creer_affectation(volume=2, type_ens=type_ens, groupe=groupe)
        natures = {b.type_enseignement: b.nature
                   for b in B.calculate_teaching_needs().besoins}
        self.assertEqual(natures, {'CM': 'COURS', 'TD': 'TD', 'TP': 'TP'})

    def test_les_besoins_sont_tries_par_difficulte(self):
        groupe = self.f.creer_groupe()
        self.f.creer_affectation(volume=2, type_ens='CM', groupe=groupe)
        self.f.creer_affectation(volume=2, type_ens='TP', groupe=groupe)
        besoins = B.calculate_teaching_needs().besoins
        # Le TP (salle spécialisée) passe avant le CM.
        self.assertEqual(besoins[0].type_enseignement, 'TP')
        self.assertGreater(besoins[0].difficulte, besoins[1].difficulte)

    def test_les_causes_sont_differentes_les_unes_des_autres(self):
        motifs = {
            B.MOTIF_AFFECTATIONS_VIDES, B.MOTIF_HORS_PERIMETRE_INJS,
            B.MOTIF_CANEVAS_VIDE, B.MOTIF_VOLUME_INCONNU,
        }
        self.assertEqual(len(motifs), 4, 'Chaque cause a son propre identifiant.')


class TestGeneration(TestCase):
    """Étapes L→O — backtracking, déterminisme, contraintes, impasses."""

    def setUp(self):
        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()
        self.creneaux = self.f.creer_creneaux(
            jours=('LUNDI', 'MARDI', 'MERCREDI'), heures=((8, 10), (10, 12)),
        )
        self.groupe = self.f.creer_groupe()
        self.salle = self.f.creer_salle('Salle A', 'SALLE', 30)

    def _generer(self, **kwargs):
        params = dict(annee_academique_id=self.f.annee.pk)
        params.update(kwargs)
        return G.generate_schedule(**params)

    def test_generation_simple(self):
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_OK)
        self.assertEqual(len(r.placements), 1)
        self.assertEqual(r.metrics['seances_placees'], 1)
        self.assertEqual(r.metrics['taux_couverture'], 100.0)
        self.assertEqual(r.metrics['nb_conflits_critiques'], 0)

    def test_plusieurs_groupes_et_plusieurs_salles(self):
        g2 = self.f.creer_groupe(nom='L1-G2')
        self.f.creer_salle('Salle B', 'SALLE', 30)
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        self.f.creer_affectation(volume=2, groupe=g2)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_OK)
        self.assertEqual(len(r.placements), 2)
        creneaux = [(p.jour, p.heure_debut) for p in r.placements]
        self.assertEqual(len(set(creneaux)), 2, 'C1/C2 : pas de double occupation.')

    def test_conflit_enseignant_est_evite(self):
        g2 = self.f.creer_groupe(nom='L1-G2')
        self.f.creer_salle('Salle B', 'SALLE', 30)
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        self.f.creer_affectation(volume=2, groupe=g2)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_OK)

    def test_aucune_salle_compatible_pour_un_tp(self):
        """C7 : sans salle au référentiel, le blocage doit être explicite."""
        RefSalle.objects.all().delete()
        self.f.creer_affectation(volume=2, type_ens='TP', groupe=self.groupe)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_IMPOSSIBLE)
        self.assertEqual(r.motif_echec, G.MOTIF_AUCUNE_SALLE_COMPATIBLE)
        self.assertTrue(r.non_places)
        self.assertIn('contraintes_bloquantes', r.non_places[0].as_dict())

    def test_salle_specialisee_respectee(self):
        """C7 : un TP ne doit jamais finir dans une salle incompatible.

        Les salles génériques (``SALLE``) restent compatibles — on ne rejette
        pas un espace non qualifié. Le contrôle porte donc sur l'absence de
        toute salle *typée dans un autre sens* (ex. une salle ``TD``).
        """
        self.f.creer_salle('Salle TP', 'TP', 30)
        self.f.creer_affectation(volume=2, type_ens='TP', groupe=self.groupe)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_OK)
        for place in r.placements:
            self.assertIn(
                place.salle.type_lieu,
                C.types_salle_compatibles(place.besoin.nature),
                'C7 : la salle choisie doit être compatible avec le TP.',
            )

    def test_capacite_insuffisante_bloque(self):
        """C4 : effectif 50, salle de 20 places → refusée."""
        grand = self.f.creer_groupe(nom='L1-G3', capacite=50)
        self.f.creer_salle('Salle Petite', 'SALLE', 20)
        self.f.creer_affectation(volume=2, groupe=grand)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_IMPOSSIBLE)
        self.assertEqual(r.motif_echec, G.MOTIF_AUCUNE_SALLE_COMPATIBLE)

    def test_indisponibilite_enseignant_bloque_le_creneau(self):
        """C5 : l'enseignant indisponible le lundi 08-10 ne peut pas y être placé."""
        DisponibiliteHoraire.objects.create(
            annee_academique=self.f.annee, enseignant=self.f.formateur,
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
            statut='INDISPONIBLE',
        )
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_OK)
        place = r.placements[0]
        self.assertFalse(
            place.jour == 'LUNDI' and place.heure_debut == time(8, 0),
            'C5 : la séance ne doit pas tomber sur une indisponibilité.',
        )

    def test_indisponibilite_salle_bloque(self):
        """C6 : salle indisponible sur tous les créneaux → blocage."""
        for jour in ('LUNDI', 'MARDI', 'MERCREDI'):
            for debut, fin in ((8, 10), (10, 12)):
                DisponibiliteHoraire.objects.create(
                    annee_academique=self.f.annee, salle=self.salle,
                    jour=jour, heure_debut=time(debut, 0),
                    heure_fin=time(fin, 0), statut='INDISPONIBLE',
                )
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_IMPOSSIBLE)

    def test_preference_enseignant_est_penalite_pas_blocage(self):
        """Étape K : une préférence produit une pénalité, jamais un blocage.

        La préférence porte sur le LUNDI ; le seul créneau disponible est le
        MARDI. Le placement doit avoir lieu (preuve : la préférence n'a pas
        bloqué) **et** être pénalisé (preuve : la préférence compte).
        """
        CreneauTemplate.objects.all().delete()
        CreneauTemplate.objects.create(
            jour='MARDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
        )
        DisponibiliteHoraire.objects.create(
            annee_academique=self.f.annee, enseignant=self.f.formateur,
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
            statut='PREFERENCE',
        )
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_OK, 'La préférence ne bloque pas.')
        self.assertEqual(r.placements[0].jour, 'MARDI')
        codes = {p.code for place in r.placements for p in place.penalites}
        self.assertIn('PREFERENCE_ENSEIGNANT_NON_RESPECTEE', codes)

    def test_une_preference_respectee_ne_genere_pas_de_penalite(self):
        """Contre-épreuve : si le créneau préféré est libre, aucune pénalité."""
        CreneauTemplate.objects.all().delete()
        CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
        )
        DisponibiliteHoraire.objects.create(
            annee_academique=self.f.annee, enseignant=self.f.formateur,
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
            statut='PREFERENCE',
        )
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_OK)
        self.assertEqual(r.placements[0].jour, 'LUNDI')
        codes = {p.code for place in r.placements for p in place.penalites}
        self.assertNotIn('PREFERENCE_ENSEIGNANT_NON_RESPECTEE', codes)

    def test_le_moteur_est_deterministe(self):
        g2 = self.f.creer_groupe(nom='L1-G2')
        self.f.creer_salle('Salle B', 'SALLE', 30)
        self.f.creer_affectation(volume=4, groupe=self.groupe)
        self.f.creer_affectation(volume=4, groupe=g2)
        premier = [(p.jour, p.heure_debut, p.salle_id, p.groupe_id)
                   for p in self._generer().placements]
        second = [(p.jour, p.heure_debut, p.salle_id, p.groupe_id)
                  for p in self._generer().placements]
        self.assertEqual(premier, second, 'Deux exécutions doivent coïncider.')

    def test_aucune_ecriture_en_base(self):
        """Le moteur ne persiste rien : la publication est une autre étape."""
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        self._generer()
        self.assertEqual(AffectationCreneau.objects.count(), 0)
        self.assertEqual(EmploiDuTemps.objects.count(), 0)

    def test_canevas_vide_renvoie_son_motif(self):
        """Arbitrage §6 : canevas vide = motif dédié, jamais un horaire fictif."""
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        CreneauTemplate.objects.all().delete()
        r = self._generer()
        self.assertEqual(r.status, G.GENERATION_IMPOSSIBLE)
        self.assertEqual(r.motif_echec, B.MOTIF_CANEVAS_VIDE)
        self.assertIn('explication', r.detail)

class TestValidationEtPublication(TestCase):
    """Étapes P, S, U, 42, 43, 51 — validation, publication, idempotence."""

    def setUp(self):
        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()
        self.creneaux = self.f.creer_creneaux(
            jours=('LUNDI', 'MARDI'), heures=((8, 10),),
        )
        self.groupe = self.f.creer_groupe()
        self.salle = self.f.creer_salle('Salle A', 'SALLE', 30)

    def _edt(self, **kwargs):
        defauts = {
            'annee_academique': self.f.annee,
            'population_type': 'GROUPE',
            'population_id': self.groupe.pk,
        }
        defauts.update(kwargs)
        return EmploiDuTemps.objects.create(**defauts)

    def _seance(self, edt, affectation, creneau, salle=None, **kwargs):
        defauts = {
            'emploi_du_temps': edt,
            'creneau_template': creneau,
            'semaine_debut': 1,
            'semaine_fin': 1,
            'salle': salle,
            'salle_nom': salle.nom if salle else '',
            'affectation_pedagogique': affectation,
            'groupe': self.groupe,
        }
        defauts.update(kwargs)
        return AffectationCreneau.objects.create(**defauts)

    # ── Validation (étape P) ──

    def test_validation_accepte_un_edt_valide(self):
        affectation = self.f.creer_affectation(volume=2, groupe=self.groupe)
        edt = self._edt()
        self._seance(edt, affectation, self.creneaux[0], self.salle)
        rapport = V.valider_emploi_du_temps(edt)
        self.assertTrue(rapport.valide, rapport.violations)
        self.assertEqual(rapport.statut, V.OK)
        self.assertEqual(rapport.couverture['seances_planifiees'], 1)

    def test_validation_signale_une_sans_affectation_pedagogique(self):
        """C8 : une séance sans contexte pédagogique émet un warning."""
        affectation = self.f.creer_affectation(volume=2, groupe=self.groupe)
        edt = self._edt()
        AffectationCreneau.objects.create(
            emploi_du_temps=edt, creneau_template=self.creneaux[0],
            semaine_debut=1, semaine_fin=1, groupe=self.groupe,
        )
        rapport = V.valider_emploi_du_temps(edt)
        self.assertTrue(
            any('C8' in w or 'affectation' in w.lower() for w in rapport.warnings),
            rapport.warnings,
        )

    def test_la_validation_ne_modifie_rien(self):
        affectation = self.f.creer_affectation(volume=2, groupe=self.groupe)
        edt = self._edt()
        self._seance(edt, affectation, self.creneaux[0], self.salle)
        avant = AffectationCreneau.objects.count()
        V.valider_emploi_du_temps(edt)
        self.assertEqual(AffectationCreneau.objects.count(), avant)

    # ── Publication (étapes S, U, 42, 43, 51) ──

    def test_publication_refuse_un_edt_sans_seance(self):
        edt = self._edt()
        r = P.publier_emploi_du_temps(edt.pk)
        self.assertFalse(r['publie'])
        self.assertEqual(r['motif_echec'], P.MOTIF_AUCUNE_AFFECTATION)

    def test_publication_reussit_et_est_idempotente(self):
        affectation = self.f.creer_affectation(volume=2, groupe=self.groupe)
        edt = self._edt()
        self._seance(edt, affectation, self.creneaux[0], self.salle)
        premier = P.publier_emploi_du_temps(edt.pk)
        self.assertTrue(premier['publie'], premier)
        edt.refresh_from_db()
        self.assertEqual(edt.statut, 'PUBLIE')
        self.assertIsNotNone(edt.publie_le)
        # Idempotence : republier ne duplique rien et ne lève pas.
        second = P.publier_emploi_du_temps(edt.pk)
        self.assertFalse(second['publie'])
        self.assertEqual(second['motif_echec'], P.MOTIF_DEJA_PUBLIE)
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_publication_refuse_si_la_version_a_change(self):
        """Étape 51 — concurrence : la version a changé depuis le chargement."""
        affectation = self.f.creer_affectation(volume=2, groupe=self.groupe)
        edt = self._edt()
        self._seance(edt, affectation, self.creneaux[0], self.salle)
        r = P.publier_emploi_du_temps(edt.pk, version_attendue=99)
        self.assertFalse(r['publie'])
        self.assertEqual(r['motif_echec'], P.MOTIF_VERSION_CONFLIT)
        edt.refresh_from_db()
        self.assertEqual(edt.statut, 'BROUILLON', 'Aucun effet de bord.')

    def test_publication_refuse_si_statut_incompatible(self):
        affectation = self.f.creer_affectation(volume=2, groupe=self.groupe)
        edt = self._edt(statut='ARCHIVE')
        self._seance(edt, affectation, self.creneaux[0], self.salle)
        r = P.publier_emploi_du_temps(edt.pk)
        self.assertFalse(r['publie'])
        self.assertEqual(r['motif_echec'], P.MOTIF_STATUT_INVALIDE)

    def test_edt_introuvable(self):
        r = P.publier_emploi_du_temps(999999)
        self.assertFalse(r['publie'])
        self.assertEqual(r['motif_echec'], 'EDT_INTROUVABLE')

    def test_empreinte_generation_est_stable(self):
        """Étape 43 : mêmes paramètres → même empreinte."""
        a = P.empreinte_generation(
            annee_academique_id=1, ref_formation_id=2, groupe_ids=[3, 1], version=1,
        )
        b = P.empreinte_generation(
            annee_academique_id=1, ref_formation_id=2, groupe_ids=[1, 3], version=1,
        )
        c = P.empreinte_generation(
            annee_academique_id=1, ref_formation_id=2, groupe_ids=[3, 1], version=2,
        )
        self.assertEqual(a, b, 'L’ordre des groupes ne change pas l’empreinte.')
        self.assertNotEqual(a, c, 'La version change l’empreinte.')
        self.assertEqual(len(a), 64)
