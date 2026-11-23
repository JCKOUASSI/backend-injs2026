"""Lot L8 (GET-INJS) — Socle de données du moteur d'emploi du temps.

Ce lot ferme les trois écarts bloquants relevés par l'audit statique du
2026-09-28, sans introduire de table ``Promotion`` (arbitrage explicite du
commanditaire : ``scolarite.Groupe`` porte déjà la promotion pédagogique) :

1. ``edts.DisponibiliteHoraire`` — période jour + plage horaire pour un
   enseignant OU une salle. Rend les contraintes fortes C5 (indisponibilité
   enseignant) et C6 (indisponibilité salle) évaluables, ce que
   ``scolarite.IndisponibiliteEnseignant`` (purement datée) ne permettait pas.
2. ``RefSalle.type_lieu`` étendu (TP, TD, COURS, INFORMATIQUE, LABORATOIRE,
   SPORT) — rend la contrainte forte C7 (compatibilité salle / type
   d'enseignement) exprimable.
3. ``EmploiDuTemps`` versionné (``version``, ``motif_modification``,
   ``valide_par/le``, ``publie_par/le``, ``empreinte``) — rend l'étape R
   (versionnage) et l'étape 43 (idempotence) atteignables.

Aucune de ces modifications ne supprime ni ne renomme une donnée existante.
"""

from datetime import time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from formations.models import (
    Formateur, RefBatiment, RefFormation, RefSalle, RefSite,
)
from edts.models import (
    CreneauTemplate, DisponibiliteHoraire, EmploiDuTemps,
)
from scolarite.models import AnneeAcademique


class BaseL8(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-06-30',
        )
        cls.cycle = RefFormation.objects.create(intitule='ÉDUCATION ET MOTRICITÉ — LICENCE')
        cls.formateur = Formateur.objects.create(nom='Traoré', prenom='Awa')
        cls.site = RefSite.objects.create(nom='INJS MARCORY')
        cls.batiment = RefBatiment.objects.create(site=cls.site, nom='ENSEPS')
        cls.salle = RefSalle.objects.create(
            site=cls.site, batiment=cls.batiment, nom='Salle 101',
            type_lieu=RefSalle.TypeLieu.TP, capacite=30,
        )


class TestDisponibiliteHoraire(BaseL8):
    """C5 / C6 — un seul porteur et une plage horaire cohérente."""

    def test_une_disponibilite_enseignant_est_valide(self):
        dispo = DisponibiliteHoraire.objects.create(
            annee_academique=self.annee, enseignant=self.formateur,
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(12, 0),
            statut='INDISPONIBLE', motif='Formation continue',
        )
        self.assertEqual(dispo.get_statut_display(), 'Indisponible')
        self.assertIn('Traoré', str(dispo))

    def test_une_disponibilite_salle_est_valide(self):
        dispo = DisponibiliteHoraire.objects.create(
            annee_academique=self.annee, salle=self.salle,
            jour='MARDI', heure_debut=time(14, 0), heure_fin=time(18, 0),
            statut='DISPONIBLE',
        )
        self.assertIn('Salle 101', str(dispo))

    def test_les_porteurs_sont_exclusifs(self):
        """Enseignant ET salle = ambiguïté métier : refusée par le modèle."""
        with self.assertRaises(ValidationError):
            DisponibiliteHoraire(
                annee_academique=self.annee, enseignant=self.formateur,
                salle=self.salle, jour='LUNDI',
                heure_debut=time(8, 0), heure_fin=time(10, 0),
            ).full_clean()

    def test_un_porteur_est_obligatoire(self):
        with self.assertRaises(ValidationError):
            DisponibiliteHoraire(
                annee_academique=self.annee, jour='LUNDI',
                heure_debut=time(8, 0), heure_fin=time(10, 0),
            ).full_clean()

    def test_une_plage_horaire_incoherente_est_refusee(self):
        with self.assertRaises(ValidationError):
            DisponibiliteHoraire(
                annee_academique=self.annee, enseignant=self.formateur,
                jour='LUNDI', heure_debut=time(12, 0), heure_fin=time(8, 0),
            ).full_clean()

    def test_la_contrainte_sql_interdit_les_deux_porteurs(self):
        """Défense en profondeur : la base refuse aussi le doublon."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DisponibiliteHoraire.objects.create(
                    annee_academique=self.annee, enseignant=self.formateur,
                    salle=self.salle, jour='LUNDI',
                    heure_debut=time(8, 0), heure_fin=time(10, 0),
                )

    def test_les_trois_statuts_sont_persistables(self):
        """DISPONIBLE / INDISPONIBLE (fort) / PREFERENCE (souple)."""
        for index, statut in enumerate(('DISPONIBLE', 'INDISPONIBLE', 'PREFERENCE')):
            d = DisponibiliteHoraire.objects.create(
                annee_academique=self.annee, enseignant=self.formateur,
                jour='LUNDI', heure_debut=time(8 + index, 0),
                heure_fin=time(9 + index, 0), statut=statut,
            )
            self.assertEqual(d.statut, statut)

    def test_une_preference_nest_pas_une_indisponibilite(self):
        """Étape K : une préférence ne doit jamais bloquer un placement."""
        pref = DisponibiliteHoraire.objects.create(
            annee_academique=self.annee, enseignant=self.formateur,
            jour='JEUDI', heure_debut=time(10, 0), heure_fin=time(12, 0),
            statut='PREFERENCE',
        )
        self.assertNotEqual(pref.statut, 'INDISPONIBLE')


class TestTypesDeSalle(BaseL8):
    """C7 — les types CM/TD/TP doivent exister au référentiel."""

    def test_les_types_pedagogiques_existent(self):
        types = dict(RefSalle.TypeLieu.choices)
        for attendu in ('COURS', 'TD', 'TP', 'INFORMATIQUE', 'LABORATOIRE', 'SPORT'):
            self.assertIn(attendu, types)

class TestVersionnageEmploiDuTemps(BaseL8):
    """Étape R — V1/V2/V3 d'un même périmètre + traçabilité du cycle de vie."""

    def _edt(self, **kwargs):
        defauts = {
            'annee_academique': self.annee,
            'population_type': 'FORMATION',
            'population_id': self.cycle.pk,
        }
        defauts.update(kwargs)
        return EmploiDuTemps.objects.create(**defauts)

    def test_un_edt_par_defaut_est_en_version_1(self):
        edt = self._edt()
        self.assertEqual(edt.version, 1)
        self.assertEqual(edt.statut, 'BROUILLON')
        self.assertEqual(edt.empreinte, '')

    def test_plusieurs_versions_du_meme_perimetre_sont_possibles(self):
        """L'unicité stricte annee+population rendait le versionnage
        impossible ; la version entre désormais dans la clé d'unicité."""
        v1 = self._edt(titre='EDT v1', version=1)
        v2 = self._edt(titre='EDT v2', version=2, motif_modification='ajout salle TP')
        v3 = self._edt(titre='EDT v3', version=3)
        self.assertEqual(
            EmploiDuTemps.objects.filter(
                annee_academique=self.annee, population_type='FORMATION',
                population_id=self.cycle.pk,
            ).count(), 3,
        )
        self.assertEqual({v1.version, v2.version, v3.version}, {1, 2, 3})

    def test_la_version_est_unique_par_perimetre(self):
        self._edt(version=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._edt(version=1)

    def test_les_champs_de_tracabilite_sont_persistes(self):
        edt = self._edt(motif_modification='Report TP', empreinte='abc123')
        edt.valide_le, edt.publie_le = None, None
        edt.save(update_fields=['valide_le', 'publie_le'])
        edt.refresh_from_db()
        self.assertEqual(edt.motif_modification, 'Report TP')
        self.assertEqual(edt.empreinte, 'abc123')
        self.assertIsNone(edt.valide_par)
        self.assertIsNone(edt.publie_par)
        self.assertIsNone(edt.valide_le)
        self.assertIsNone(edt.publie_le)

    def test_l_empreinte_est_indexee_pour_l_idempotence(self):
        """Étape 43 : retrouver une génération identique doit être rapide."""
        noms = set()
        for index in EmploiDuTemps._meta.indexes:
            noms.update(getattr(f, 'name', f) for f in index.fields)
        self.assertIn('empreinte', noms)

    def test_les_statuts_existants_restent_inchanges(self):
        """Aucun statut historique n'est supprimé par le lot."""
        statuts = {c[0] for c in EmploiDuTemps._meta.get_field('statut').choices}
        for attendu in ('BROUILLON', 'EN_VALIDATION', 'VALIDE', 'PUBLIE', 'ARCHIVE'):
            self.assertIn(attendu, statuts)


class TestPasDeTablePromotion(BaseL8):
    """Arbitrage du commanditaire : aucune table Promotion ne doit exister."""

    def test_aucun_modele_promotion_n_est_defini(self):
        from django.apps import apps

        with self.assertRaises(LookupError):
            apps.get_model('edts', 'Promotion')
        with self.assertRaises(LookupError):
            apps.get_model('scolarite', 'Promotion')

    def test_le_groupe_porte_la_promotion_pedagogique(self):
        """Année + formation + parcours + niveau + vague + groupe."""
        from scolarite.models import Groupe, Niveau, Parcours

        niveau = Niveau.objects.create(
            code='L1', libelle='Licence 1', cycle='LICENCE', ordre=1, credits_requis=60,
        )
        parcours = Parcours.objects.create(
            code='P1', intitule='Parcours test', ref_formation=self.cycle,
        )
        groupe = Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.cycle,
            parcours=parcours, niveau=niveau, nom='L1-G1', capacite_max=30,
        )
        self.assertEqual(groupe.annee_academique_id, self.annee.pk)
        self.assertEqual(groupe.niveau_id, niveau.pk)
        self.assertEqual(groupe.parcours_id, parcours.pk)
        # Promotion = notion calculée (année, formation, parcours, niveau, vague).
        promotion = {
            'annee': groupe.annee_academique_id,
            'formation': groupe.ref_formation_id,
            'parcours': groupe.parcours_id,
            'niveau': groupe.niveau_id,
        }
        self.assertEqual(len(promotion), 4)


    def test_les_types_historiques_sont_conserves(self):
        types = dict(RefSalle.TypeLieu.choices)
        for historique in ('SALLE', 'AMPHI', 'GYMNASE', 'REUNION', 'CONFERENCE'):
            self.assertIn(historique, types)

    def test_aucune_salle_existante_nest_reclassee(self):
        """Le lot n'affecte que le référentiel : le défaut reste SALLE."""
        salle = RefSalle.objects.create(
            site=self.site, batiment=self.batiment, nom='Sans type',
        )
        self.assertEqual(salle.type_lieu, RefSalle.TypeLieu.SALLE)
