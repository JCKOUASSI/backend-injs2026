"""Lot L2 — Consolidation de `AffectationCreneau` comme Séance / EDT LMD.

L2 ne reconstruit rien : il **raccorde** les relations déjà présentes dans le dépôt.

    AffectationCreneau
       ├── formateur → formations.Formateur        (FK EXISTANTE, réutilisée)
       ├── affectation_pedagogique → AffectationPedagogique   (lot L1)
       │        └── UE → ECUE
       └── salle → formations.RefSalle             (FK ajoutée par ce lot)

`salle_nom` est **conservé** : il alimente la détection de conflits
(`edts/services.py`) et plusieurs API. La FK `salle` le complète, elle ne le
remplace pas. Aucun rattachement automatique n'est introduit.
"""
from datetime import timedelta

from django.db.models import PROTECT, ProtectedError
from django.test import TestCase
from django.utils import timezone

from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from formations.models import Formateur, RefBatiment, RefFormation, RefSalle, RefSite
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, Groupe, Maquette, Niveau,
    Parcours, Semestre, TypeFormation, UE,
)

JOURS = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI', 'DIMANCHE']


class RaccordementPedagogiqueTests(TestCase):
    """La séance EDT retrouve son contexte pédagogique complet."""

    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        # Arrondir avant les décalages : le modèle normalise à la minute.
        now = timezone.localtime().replace(second=0, microsecond=0)
        debut, fin = now - timedelta(minutes=5), now + timedelta(minutes=55)

        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=today - timedelta(weeks=3),
            date_fin=today + timedelta(weeks=40), courante=True,
        )
        cls.type_formation = TypeFormation.objects.create(
            code='LIC', libelle='Licence professionnelle', actif=True,
        )
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.semestre = Semestre.objects.create(
            niveau=cls.niveau, numero=1, libelle='Semestre 1', actif=True,
        )
        cls.ref_formation = RefFormation.objects.create(intitule='LICENCE PRO — L1')
        cls.parcours = Parcours.objects.create(
            ref_formation=cls.ref_formation, type_formation=cls.type_formation,
            code='P-PRO', intitule='Parcours professionnel', actif=True,
        )
        cls.groupe = Groupe.objects.create(
            annee_academique=cls.annee, niveau=cls.niveau,
            ref_formation=cls.ref_formation, nom='L1-G1', capacite_max=30,
        )
        # Maquette laissée en BROUILLON : une maquette ACTIVE est immuable
        # (garde-fou Peyre-Lorraine), ce qui n'est pas l'objet de ce test.
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.ref_formation,
            parcours=cls.parcours, niveau=cls.niveau,
        )
        cls.ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.semestre, code='UE1',
            intitule='Unité 1', credits=6,
        )
        cls.ecue = ECUE.objects.create(
            ue=cls.ue, code='ECUE1', intitule='Physique appliquée',
            credits=4, volume_cm=20, volume_td=10, volume_tp=10,
        )
        cls.formateur = Formateur.objects.create(
            numerobadge='FB-L1-0001', nom='Traoré', prenom='Awa',
        )
        cls.affectation_pedagogique = AffectationPedagogique.objects.create(
            annee_academique=cls.annee, ref_formation=cls.ref_formation,
            parcours=cls.parcours, niveau=cls.niveau, semestre=cls.semestre,
            ue=cls.ue, ecue=cls.ecue, groupe=cls.groupe,
            enseignant=cls.formateur, type_enseignement='CM',
            volume_horaire=40, statut=AffectationPedagogique.Statut.VALIDEE,
        )
        cls.edt = EmploiDuTemps.objects.create(
            annee_academique=cls.annee, population_type='ANNEE', population_id=0,
            statut='PUBLIE', semaine_debut=1, semaine_fin=52,
            rentree=cls.annee.date_debut,
        )
        cls.template = CreneauTemplate.objects.create(
            jour=JOURS[today.weekday()], heure_debut=debut.time(), heure_fin=fin.time(),
        )

        # --- Lot L2 : référentiel salle ---
        cls.site = RefSite.objects.create(nom='INJS MARCORY', actif=True)
        cls.batiment = RefBatiment.objects.create(
            site=cls.site, nom='Bâtiment A', actif=True,
        )
        cls.salle = RefSalle.objects.create(
            site=cls.site, batiment=cls.batiment, nom='Amphi 1',
            type_lieu=RefSalle.TypeLieu.AMPHI, capacite=200, actif=True,
        )
        cls.salle_td = RefSalle.objects.create(
            site=cls.site, batiment=cls.batiment, nom='Salle TD1',
            type_lieu=RefSalle.TypeLieu.SALLE, capacite=40, actif=True,
        )
        # Second formateur : sert à vérifier qu'aucune contrainte
        # d'unicité formateur↔affectation n'est introduite (§ 7).
        cls.formateur_remplacant = Formateur.objects.create(
            numerobadge='FB-L1-0002', nom='Kouamé', prenom='Ibrahim',
        )

    def _seance(self, **kw):
        """Séance EDT. Sans `affectation_pedagogique`, la FK reste à None."""
        params = dict(
            emploi_du_temps=self.edt, creneau_template=self.template,
            semaine_debut=1, semaine_fin=52, groupe=self.groupe,
            salle_nom='Amphi 1', intitule='Séance de test',
        )
        params.update(kw)
        return AffectationCreneau.objects.create(**params)

    # -- Rattachement (exigence § 9) --------------------------------------

    def test_la_seance_retrouve_son_ecue(self):
        seance = self._seance(affectation_pedagogique=self.affectation_pedagogique)
        seance.refresh_from_db()
        self.assertIsNotNone(seance.affectation_pedagogique)
        self.assertEqual(seance.affectation_pedagogique.ecue, self.ecue)
        self.assertEqual(seance.affectation_pedagogique.ecue.intitule, 'Physique appliquée')

    def test_la_chaine_complete_est_atteignable(self):
        """Séance → ECUE → UE → Maquette → Formation / Parcours / Niveau / Semestre."""
        seance = self._seance(affectation_pedagogique=self.affectation_pedagogique)
        ap = seance.affectation_pedagogique
        self.assertEqual(ap.ecue, self.ecue)
        self.assertEqual(ap.ue, self.ue)
        # La maquette n'est pas portée par l'affectation : elle s'atteint via l'UE.
        self.assertEqual(ap.ue.maquette, self.maquette)
        self.assertEqual(ap.ue.maquette.ref_formation, self.ref_formation)
        self.assertEqual(ap.ue.maquette.parcours, self.parcours)
        self.assertEqual(ap.ref_formation, self.ref_formation)
        self.assertEqual(ap.parcours, self.parcours)
        self.assertEqual(ap.niveau, self.niveau)
        self.assertEqual(ap.semestre, self.semestre)
        self.assertEqual(ap.annee_academique, self.annee)
        self.assertEqual(ap.groupe, self.groupe)
        self.assertEqual(ap.enseignant, self.formateur)

    def test_la_seance_expose_encore_son_groupe_et_son_horaire(self):
        """Le lien pédagogique ne se substitue pas à l'identité opérationnelle."""
        seance = self._seance(affectation_pedagogique=self.affectation_pedagogique)
        self.assertEqual(seance.groupe_id, self.groupe.pk)
        self.assertEqual(seance.salle_nom, 'Amphi 1')
        self.assertEqual(seance.creneau_template, self.template)

    # -- Rattachement MANUEL (exigence § 3) -------------------------------

    def test_une_seance_sans_rattachement_reste_valide(self):
        """Aucune déduction automatique : la FK est à None et la séance est créée."""
        seance = self._seance()
        self.assertIsNone(seance.affectation_pedagogique)
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_le_rattachement_est_explicite_et_modifiable(self):
        """On peut rattacher après coup, comme le détacher — les deux manuels."""
        seance = self._seance()
        seance.affectation_pedagogique = self.affectation_pedagogique
        seance.save(update_fields=['affectation_pedagogique'])
        seance.refresh_from_db()
        self.assertEqual(seance.affectation_pedagogique_id, self.affectation_pedagogique.pk)
        seance.affectation_pedagogique = None
        seance.save(update_fields=['affectation_pedagogique'])
        seance.refresh_from_db()
        self.assertIsNone(seance.affectation_pedagogique_id)

    def test_une_seance_partage_l_affectation_pedagogique(self):
        """Plusieurs séances d'un même ECUE (CM, TD, TP) pointent la même affectation."""
        cm = self._seance(affectation_pedagogique=self.affectation_pedagogique)
        td = self._seance(affectation_pedagogique=self.affectation_pedagogique)
        lies = self.affectation_pedagogique.seances_edt.all()
        self.assertEqual(lies.count(), 2)
        self.assertEqual(set(lies), {cm, td})

    # -- Comportement PROTECT (exigence § 4 et § 9) -----------------------

    def test_supprimer_l_affectation_utilisee_est_protge(self):
        """Une affectation utilisée par une séance ne peut pas être supprimée."""
        self._seance(affectation_pedagogique=self.affectation_pedagogique)
        with self.assertRaises(ProtectedError):
            self.affectation_pedagogique.delete()

    def test_supprimer_une_affectation_inutilisee_est_autorise(self):
        """Converse du PROTECT : sans séance rattachée, la suppression passe."""
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.ref_formation,
            parcours=self.parcours, niveau=self.niveau, semestre=self.semestre,
            ue=self.ue, groupe=self.groupe, enseignant=self.formateur,
            type_enseignement='TD',
        )
        inutilisee = AffectationPedagogique.objects.filter(
            type_enseignement='TD').first()
        inutilisee.delete()
        self.assertFalse(AffectationPedagogique.objects.filter(
            type_enseignement='TD').exists())

    def test_le_protect_est_bien_le_on_delete_du_modele(self):
        """Garde-fou : la convention PROTECT ne doit pas être altérée."""
        champ = AffectationCreneau._meta.get_field('affectation_pedagogique')
        self.assertIs(champ.remote_field.on_delete, PROTECT)
        self.assertTrue(champ.null)
        self.assertTrue(champ.blank)


class ConsolidationSeanceLMDTests(RaccordementPedagogiqueTests):
    """Lot L2 — la séance s'appuie sur Formateur (existant) et RefSalle (nouveau).

    Cette classe hérite du jeu de données du lot L1 et ajoute :
    - Test 2 : le formateur utilise la FK existante, sans second FK ;
    - Test 3 : la FK `salle` vers `RefSalle` fonctionne ;
    - Test 4 : les relations réelles de cohérence, sans règle inventée.
    """

    # -- Test 2 — Formateur : relation unique, FK existante --------------

    def test_le_formateur_utilise_la_fk_existante(self):
        seance = self._seance(formateur=self.formateur)
        seance.refresh_from_db()
        self.assertEqual(seance.formateur, self.formateur)
        self.assertEqual(seance.formateur.numerobadge, 'FB-L1-0001')

    def test_il_n_existe_qu_un_seul_champ_vers_le_formateur(self):
        """Anti-doublon : aucun 2e champ `enseignant`/`formateur` FK n'est ajouté."""
        cibles = {
            f.name: f for f in AffectationCreneau._meta.get_fields()
            if getattr(f, 'many_to_one', False) or getattr(f, 'one_to_one', False)
        }
        vers_formateur = {
            nom: f for nom, f in cibles.items() if f.related_model is Formateur
        }
        # Uniquement le champ préexistant `formateur` : le lot L2 n'en ajoute pas.
        self.assertEqual(list(vers_formateur), ['formateur'])
        # `enseignant_id` reste un simple entier, jamais une FK.
        champ_legacy = AffectationCreneau._meta.get_field('enseignant_id')
        self.assertFalse(getattr(champ_legacy, 'related_model', None))

    def test_le_formateur_est_independant_de_l_affectation(self):
        """§ 7 : aucun « rappel automatique » du formateur depuis l'affectation.

        La règle métier (remplaçant autorisé ?) n'étant pas tranchée, aucune
        contrainte n'est introduite : les deux relations restent indépendantes.
        """
        seance = self._seance(
            formateur=self.formateur_remplacant,
            affectation_pedagogique=self.affectation_pedagogique,
        )
        seance.refresh_from_db()
        self.assertEqual(seance.formateur, self.formateur_remplacant)
        self.assertEqual(seance.affectation_pedagogique.enseignant, self.formateur)
        # La divergence est tolérée : le modèle ne l'interdit pas.
        self.assertNotEqual(seance.formateur, seance.affectation_pedagogique.enseignant)

    # -- Test 3 — Salle ---------------------------------------------------

    def test_la_seance_reference_la_salle_du_referentiel(self):
        seance = self._seance(salle=self.salle, salle_nom=self.salle.nom)
        seance.refresh_from_db()
        self.assertEqual(seance.salle, self.salle)
        self.assertEqual(seance.salle.site, self.site)
        self.assertEqual(seance.salle.batiment, self.batiment)
        self.assertEqual(seance.salle.type_lieu, RefSalle.TypeLieu.AMPHI)

    def test_salle_nom_est_conserve_avec_la_fk(self):
        """Transition : `salle_nom` reste alimenté et n'est jamais écrasé."""
        seance = self._seance(salle=self.salle_td, salle_nom='Salle TD1')
        seance.refresh_from_db()
        self.assertEqual(seance.salle, self.salle_td)
        self.assertEqual(seance.salle_nom, 'Salle TD1')

    def test_la_salle_est_optionnelle(self):
        seance = self._seance()
        self.assertIsNone(seance.salle)
        self.assertEqual(seance.salle_nom, 'Amphi 1')  # non régressé

    def test_supprimer_une_salle_utilisee_est_protge(self):
        self._seance(salle=self.salle, salle_nom=self.salle.nom)
        with self.assertRaises(ProtectedError):
            self.salle.delete()

    def test_une_salle_de_referentiel_n_expose_les_seances(self):
        self._seance(salle=self.salle, salle_nom=self.salle.nom)
        self.assertEqual(self.salle.seances_edt.count(), 1)

    def test_la_detection_de_conflit_de_salle_sert_toujours(self):
        """Non-régression : `edts/services.py` compare toujours `salle_nom`.

        `detecter_conflits` persiste des lignes `ConflitCreneau` et renvoie un
        dictionnaire de statistiques : le test observe la base, pas un retour
        texte. Ce test prouve que `salle_nom` reste le support de la détection
        de collision de salle après l'ajout de la FK `salle`.
        """
        from edts.models import ConflitCreneau
        from edts.services import detecter_conflits

        self.edt.semaine_debut, self.edt.semaine_fin = 1, 10
        self.edt.save()
        # Deux séances, même créneau, même salle : collision attendue.
        self._seance(salle=self.salle, salle_nom='A101', groupe=None)
        self._seance(salle=self.salle, salle_nom='A101', groupe=None)

        detecter_conflits(self.edt)

        types_conflits = set(
            ConflitCreneau.objects.filter(emploi_du_temps=self.edt)
            .values_list('type_conflit', flat=True)
        )
        self.assertIn(
            'HORAIRE_SALLE', types_conflits,
            msg="Le conflit de salle fondé sur salle_nom doit rester détecté.",
        )

    # -- Test 4 — Cohérence des relations réelles -------------------------

    def test_la_seance_expose_les_cotes_coherentes_de_la_chaine_lmd(self):
        """Année, formation, groupe et ECUE sont joignables depuis la séance."""
        seance = self._seance(
            formation=self.ref_formation, groupe=self.groupe,
            formateur=self.formateur, salle=self.salle,
            affectation_pedagogique=self.affectation_pedagogique,
        )
        self.assertEqual(seance.emploi_du_temps.annee_academique, self.annee)
        self.assertEqual(seance.affectation_pedagogique.annee_academique, self.annee)
        self.assertEqual(seance.formation, self.ref_formation)
        self.assertEqual(seance.affectation_pedagogique.ref_formation, self.ref_formation)
        self.assertEqual(seance.groupe, self.groupe)
        self.assertEqual(seance.affectation_pedagogique.groupe, self.groupe)
        self.assertEqual(seance.affectation_pedagogique.ue, self.ue)
        self.assertEqual(seance.affectation_pedagogique.ecue, self.ecue)

    def test_les_relations_independantes_restent_admissibles(self):
        """§ 8 : aucune contrainte d'égalité imposée entre champs redondants.

        `seance.formation` et `seance.groupe` sont des FK historiques, antérieures
        à `affectation_pedagogique`. Les rendre obligatoires ou identiques serait
        inventer une règle métier non tranchée : on vérifie donc qu'une séance peut
        être rattachée à l'affectation sans renseigner ces FK redondantes.
        """
        seance = self._seance(
            formation=None, groupe=None,
            affectation_pedagogique=self.affectation_pedagogique,
        )
        self.assertIsNone(seance.formation_id)
        self.assertIsNone(seance.groupe_id)
        self.assertEqual(seance.affectation_pedagogique.ecue, self.ecue)
        # Le groupe reste néanmoins joignable via l'affectation.
        self.assertEqual(seance.affectation_pedagogique.groupe, self.groupe)

    def test_la_chaine_lmd_complete_est_atteignable(self):
        """Architecture cible § 5 : Séance → ECUE / Formateur / Groupe / Salle."""
        seance = self._seance(
            affectation_pedagogique=self.affectation_pedagogique,
            formateur=self.formateur, salle=self.salle,
            salle_nom=self.salle.nom,
        )
        # ECUE
        self.assertEqual(seance.affectation_pedagogique.ecue, self.ecue)
        self.assertEqual(seance.affectation_pedagogique.ecue.ue, self.ue)
        # Formateur (FK unique, préexistante)
        self.assertEqual(seance.formateur, self.formateur)
        # Salle (FK nouvelle) + salle_nom (transition)
        self.assertEqual(seance.salle, self.salle)
        self.assertEqual(seance.salle_nom, self.salle.nom)
        # Horaire opérationnel
        self.assertEqual(seance.creneau_template, self.template)

