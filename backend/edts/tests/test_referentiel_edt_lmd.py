"""Tests du Référentiel EDT LMD — règles d'idempotence et de résolution LMD.

Couvre les corrections apportées au chantier « Référentiel EDT LMD » :

1. **Idempotence du créneau** : les horaires sont un repère d'agenda, donc
   normalisés à la minute ; deux créations d'un même créneau (jour, début, fin)
   doivent converger vers le **même** objet, jamais produire de doublon.
2. **Unicité** : la base refuse deux créneaux strictement identiques.
3. **Résolution LMD de l'affectation** : une affectation générée est rattachée
   à son affectation pédagogique (donc résoluble en ECUE/UE/semestre) et à son
   enseignant par la FK métier.
4. **Collisions sur clés étrangères** : les conflits sont détectés via
   ``salle_id`` / ``formateur_id`` et non par comparaison de libellés.

Aucun test n'est désactivé pour obtenir un vert.
"""
from datetime import time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from edts.services import types_conflit
from formations.models import Formateur, RefFormation, RefSalle, RefSite
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, Groupe, Maquette,
    Niveau, Semestre, UE,
)


class CreneauTemplateIdempotenceTests(TestCase):
    """Un créneau est identifié par (jour, heure début, heure fin)."""

    def test_les_heures_sont_normalisees_a_la_minute(self):
        creneau = CreneauTemplate.objects.create(
            jour='LUNDI',
            heure_debut=time(8, 0, 42, 987654),   # secondes + microsecondes
            heure_fin=time(9, 59, 31, 123456),
        )
        creneau.refresh_from_db()
        self.assertEqual(creneau.heure_debut, time(8, 0))
        self.assertEqual(creneau.heure_fin, time(9, 59))

    def test_les_heures_texte_sont_converties_et_normalisees(self):
        creneau = CreneauTemplate.objects.create(
            jour='LUNDI',
            heure_debut='08:00:42.987654',
            heure_fin='10:00:31.123456',
        )
        self.assertEqual(creneau.heure_debut, time(8, 0))
        self.assertEqual(creneau.heure_fin, time(10, 0))

    def test_deux_creations_identiques_donnent_le_meme_creneau(self):
        """Idempotence : le micro-courb de l'horaire ne crée pas de doublon.

        Deux écritures du même créneau (jour, début, fin) — même après
        arrondi — désignent le même objet. La seconde doit être refusée par la
        contrainte d'unicité plutôt que d'ajouter une ligne au référentiel.
        """
        premier = CreneauTemplate.objects.create(
            jour='MARDI', heure_debut=time(8, 0, 1, 5), heure_fin=time(10, 0, 2, 7))
        with self.assertRaises(ValidationError):
            CreneauTemplate.objects.create(
                jour='MARDI', heure_debut=time(8, 0, 3, 9), heure_fin=time(10, 0, 4, 11))
        self.assertEqual(CreneauTemplate.objects.filter(jour='MARDI').count(), 1)
        self.assertEqual(premier.heure_debut, time(8, 0))

    def test_get_or_create_retrouve_le_creneau_existant(self):
        """Le chemin réellement utilisé par les générateurs est convergent.

        `get_or_create` sur les horaires arrondis retrouve le créneau existant
        au lieu d'en créer un second : c'est l'idempotence exigée.
        """
        existant, cree = CreneauTemplate.objects.get_or_create(
            jour='MERCREDI', heure_debut=time(8, 0), heure_fin=time(10, 0))
        self.assertTrue(cree)
        retrouve, cree = CreneauTemplate.objects.get_or_create(
            jour='MERCREDI',
            heure_debut=CreneauTemplate.normaliser(time(8, 0, 41, 7)),
            heure_fin=CreneauTemplate.normaliser(time(10, 0, 12, 3)))
        self.assertFalse(cree, 'le créneau existant doit être retrouvé')
        self.assertEqual(retrouve.pk, existant.pk)
        self.assertEqual(CreneauTemplate.objects.filter(jour='MERCREDI').count(), 1)

    def test_la_base_refuse_deux_creneaux_strictement_identiques(self):
        """Le modèle refuse le doublon avant même d'atteindre la base.

        `save()` appelle `full_clean()` : la contrainte d'unicité est donc
        vérifiée à l'écriture, ce qui donne un message métier lisible plutôt
        qu'une `IntegrityError` brute. Le filet base reste en place (contrainte
        réelle) pour les écritures en bulk.
        """
        CreneauTemplate.objects.create(
            jour='JEUDI', heure_debut=time(14, 0), heure_fin=time(16, 0))
        with self.assertRaises(ValidationError) as contexte:
            CreneauTemplate.objects.create(
                jour='JEUDI', heure_debut=time(14, 0), heure_fin=time(16, 0))
        self.assertIn('existe déjà', str(contexte.exception))

    def test_la_contrainte_est_bien_posee_en_base(self):
        """Filet base : sans passer par le modèle, la base refuse aussi."""
        noms = {cont.name for cont in CreneauTemplate._meta.constraints}
        self.assertIn('uniq_creneau_template_jour_horaires', noms)
        CreneauTemplate.objects.create(
            jour='JEUDI', heure_debut=time(14, 0), heure_fin=time(16, 0))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CreneauTemplate.objects.bulk_create([
                    CreneauTemplate(jour='JEUDI', heure_debut=time(14, 0),
                                    heure_fin=time(16, 0)),
                ])

    def test_durees_differentes_resterent_des_creneaux_distincts(self):
        a = CreneauTemplate.objects.create(
            jour='VENDREDI', heure_debut=time(8, 0), heure_fin=time(10, 0))
        b = CreneauTemplate.objects.create(
            jour='VENDREDI', heure_debut=time(8, 0), heure_fin=time(12, 0))
        self.assertNotEqual(a.pk, b.pk)
        self.assertEqual(CreneauTemplate.objects.filter(jour='VENDREDI').count(), 2)

    def test_une_heure_de_fin_anterieure_est_refusee(self):
        with self.assertRaises(ValidationError):
            CreneauTemplate.objects.create(
                jour='LUNDI', heure_debut=time(10, 0), heure_fin=time(9, 0))

    def test_duree_prevue_calculee_apres_normalisation(self):
        creneau = CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut=time(8, 0, 30), heure_fin=time(10, 0, 30))
        creneau.refresh_from_db()
        self.assertEqual(creneau.duree_prevue_minutes, 120)


class CollisionsSurClesEtrangeresTests(TestCase):
    """Les conflits se déterminent par FK, pas par comparaison de libellés."""

    def setUp(self):
        self.edt = EmploiDuTemps.objects.create(
            annee_academique=AnneeAcademique.objects.create(
                libelle='2026-2027', date_debut='2026-09-01',
                date_fin='2027-08-31', courante=True),
            population_type='FORMATION', population_id=1,
            statut='BROUILLON', semaine_debut=1, semaine_fin=10)
        self.creneau = CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0))
        site = RefSite.objects.create(nom='INJS Marcory')
        self.salle_a = RefSalle.objects.create(nom='SALLE ALPHA', site=site)
        self.salle_b = RefSalle.objects.create(nom='SALLE ALPHA', site=site)
        self.formateur = Formateur.objects.create(
            numerobadge='FB-EDT-1', nom='KONE', prenom='Awa')
        self.formation = RefFormation.objects.create(intitule='Licence STAPS')

    def _affectation(self, **kwargs):
        defauts = {
            'emploi_du_temps': self.edt, 'creneau_template': self.creneau,
            'semaine_debut': 1, 'semaine_fin': 10, 'actif': True,
        }
        defauts.update(kwargs)
        return AffectationCreneau.objects.create(**defauts)

    def test_meme_salle_par_fk_est_un_conflit(self):
        a = self._affectation(salle=self.salle_a, salle_nom='SALLE ALPHA')
        b = self._affectation(salle=self.salle_a, salle_nom='SALLE ALPHA')
        self.assertIn('HORAIRE_SALLE', types_conflit(a, b))

    def test_salles_distintes_meme_libelle_ne_sont_pas_un_conflit(self):
        """Deux `RefSalle` différents portent le même libellé : pas de conflit.

        C'est exactement le cas que la comparaison par `salle_nom` résolvait à
        tort, et que la clé étrangère règle correctement.
        """
        a = self._affectation(salle=self.salle_a, salle_nom='SALLE ALPHA')
        b = self._affectation(salle=self.salle_b, salle_nom='SALLE ALPHA')
        self.assertNotIn('HORAIRE_SALLE', types_conflit(a, b))

    def test_meme_enseignant_par_fk_formateur_est_un_conflit(self):
        a = self._affectation(formateur=self.formateur)
        b = self._affectation(formateur=self.formateur)
        self.assertIn('HORAIRE_ENSEIGNANT', types_conflit(a, b))

    def test_formateur_prioritaire_sur_le_compte_utilisateur(self):
        """Deux affectations du même formateur ne sont pas en conflit parce que
        leurs `enseignant_id` (comptes utilisateurs) diffèrent."""
        a = self._affectation(formateur=self.formateur, enseignant_id=11)
        b = self._affectation(formateur=self.formateur, enseignant_id=22)
        self.assertIn('HORAIRE_ENSEIGNANT', types_conflit(a, b))


class PersistanceChaineLmdTests(TestCase):
    """Le plan persisté conserve toute la chaîne LMD."""

    def setUp(self):
        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-09-01',
            date_fin='2027-08-31', courante=True)
        self.edt = EmploiDuTemps.objects.create(
            annee_academique=self.annee, population_type='FORMATION',
            population_id=1, statut='BROUILLON', semaine_debut=1, semaine_fin=10)
        self.formation = RefFormation.objects.create(intitule='Licence STAPS')
        self.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        self.groupe = Groupe.objects.create(
            annee_academique=self.annee, niveau=self.niveau,
            ref_formation=self.formation, nom='L1-G1')
        self.creneau = CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0))
        self.salle = RefSalle.objects.create(
            nom='SALLE LMD', site=RefSite.objects.create(nom='INJS Marcory'))
        self.formateur = Formateur.objects.create(
            numerobadge='FB-EDT-2', nom='TRAORE', prenom='Mariam')
        # -- Chaîne pédagogique LMD complète (UE/ECUE/AP) --------------------
        self.semestre = Semestre.objects.create(
            niveau=self.niveau, numero=1, libelle='Semestre 1')
        self.maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, version=1, libelle='Maquette L1',
            statut=Maquette.Statut.BROUILLON)
        self.ue = UE.objects.create(
            maquette=self.maquette, semestre=self.semestre, code='UE1',
            intitule='Physique')
        self.ecue = ECUE.objects.create(
            ue=self.ue, code='ECUE1', intitule='Physique appliquée')
        self.affectation_pedagogique = AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, semestre=self.semestre, ue=self.ue, ecue=self.ecue,
            groupe=self.groupe, enseignant=self.formateur,
            type_enseignement=AffectationPedagogique.TypeEnseignement.CM,
            volume_horaire=4,
            statut=AffectationPedagogique.Statut.VALIDEE)

    def _besoin(self, ecue_id=None):
        from edts.moteur.besoins import TeachingNeed
        return TeachingNeed(
            affectation_pedagogique_id=self.affectation_pedagogique.id,
            annee_academique_id=self.annee.id,
            ref_formation_id=self.formation.id, parcours_id=None,
            niveau_id=self.niveau.id, semestre_id=self.semestre.id,
            groupe_id=self.groupe.id, ue_id=self.ue.id, ecue_id=self.ecue.id,
            enseignant_id=self.formateur.id, type_enseignement='CM',
            nature='COURS', intitule=self.ecue.intitule, volume_horaire=4,
            credits=2, effectif=30, duree_seance_heures=2, nb_seances=1)

    def _place(self, besoin):
        place = type('Place', (), {})()
        place.besoin = besoin
        place.creneau = self.creneau
        place.salle = self.salle
        place.semaine_debut = 1
        place.semaine_fin = 10
        return place

    def test_la_seance_est_rattachee_a_son_affectation_pedagogique(self):
        from edts.moteur import publication as publication_module
        nombre = publication_module.persister_plan(self.edt, [self._place(self._besoin())])
        self.assertEqual(nombre, 1)
        seance = AffectationCreneau.objects.get(emploi_du_temps=self.edt)
        self.assertEqual(seance.affectation_pedagogique_id,
                         self.affectation_pedagogique.id,
                         'la séance doit rester traçable jusqu au cours')
        self.assertEqual(seance.formateur_id, self.formateur.id)
        self.assertEqual(seance.salle_id, self.salle.id)
        self.assertEqual(seance.groupe_id, self.groupe.id)

    def test_remplacer_ne_duplique_pas_les_seances(self):
        from edts.moteur import publication as publication_module
        publication_module.persister_plan(self.edt, [self._place(self._besoin())])
        publication_module.persister_plan(self.edt, [self._place(self._besoin())],
                                          remplacer=True)
        self.assertEqual(AffectationCreneau.objects.filter(
            emploi_du_temps=self.edt, actif=True).count(), 1)
