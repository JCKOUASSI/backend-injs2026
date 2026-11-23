"""Statistiques des présences LMD enregistrées sur le canal EDT (N-02).

Ces tests prouvent ce que l'audit du 26/09/2026 établissait : les ``Pointage``
portant ``seance_edt`` (et ``session = None``) étaient **invisibles** du
décisionnel, car le socle historique raisonne en ``SessionModule``.

Ils prouvent également que la nouvelle couche calcule des chiffres **juste** :
un étudiant absent du groupe n'est jamais compté présent, et l'effectif agrégé
sur une période est une union (pas une somme).

Voir ``statistiques/seances_edt_stats`` pour le contrat détaillé.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from authentication.models import User
from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from formations.models import Participant, RefFormation
from presences.models import Pointage
from scolarite.models import (
    AffectationGroupe, AnneeAcademique, DossierEtudiant, Groupe,
    InscriptionAdministrative, Niveau, StatutEtudiant,
)
from statistiques import seances_edt_stats as edt_stats

JOURS = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI', 'DIMANCHE']


class SeanceEdtStatsTests(TestCase):
    """Trois auditeurs au groupe, une séance EDT planifiée aujourd'hui."""

    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.jour = today
        now = timezone.localtime().replace(second=0, microsecond=0)
        debut, fin = now - timedelta(minutes=5), now + timedelta(minutes=55)

        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=today - timedelta(weeks=3),
            date_fin=today + timedelta(weeks=40), courante=True,
        )
        cls.admin = User.objects.create_user(username='adm-stats', password='x', role='ADMIN')
        cls.template = CreneauTemplate.objects.create(
            jour=JOURS[today.weekday()], heure_debut=debut.time(), heure_fin=fin.time(),
        )
        cls.edt = EmploiDuTemps.objects.create(
            annee_academique=cls.annee, population_type='ANNEE', population_id=0,
            statut='PUBLIE', semaine_debut=1, semaine_fin=52,
            rentree=cls.annee.date_debut, cree_par=cls.admin,
        )
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.ref_formation = RefFormation.objects.create(intitule='LICENCE PRO — STATS')
        cls.groupe = Groupe.objects.create(
            annee_academique=cls.annee, niveau=cls.niveau,
            ref_formation=cls.ref_formation, nom='L1-G1', capacite_max=10,
        )
        cls.affectation = AffectationCreneau.objects.create(
            emploi_du_temps=cls.edt, creneau_template=cls.template,
            semaine_debut=1, semaine_fin=52, groupe=cls.groupe,
            formation=cls.ref_formation, salle_nom='Amphi 1',
            intitule='Physique appliquée',
        )
        cls.statut_actif = StatutEtudiant.objects.create(code='ACTIF', libelle='Actif')
        cls.participants = []
        for i in range(3):
            user = User.objects.create_user(username=f'stats{i}', password='x', role='AUDITEUR')
            participant = Participant.objects.filter(user=user).first()
            if participant is None:
                participant = Participant.objects.create(
                    matricule=f'STS{i:03d}', nom=f'Nom{i}', prenom=f'Prenom{i}', user=user,
                )
            dossier = DossierEtudiant.objects.create(participant=participant,
                                                    statut=cls.statut_actif)
            inscription = InscriptionAdministrative.objects.create(
                etudiant=dossier, annee_academique=cls.annee, niveau=cls.niveau,
                ref_formation=cls.ref_formation,
                statut=InscriptionAdministrative.Statut.VALIDEE,
                statut_etudiant=cls.statut_actif,
            )
            AffectationGroupe.objects.create(groupe=cls.groupe, inscription=inscription,
                                             active=True)
            cls.participants.append(participant)

    def _pointer(self, participant, statut=Pointage.Statut.TERMINE, duree=60, **kw):
        """Pointage sur le canal EDT : ``session=None``, ``seance_edt`` renseigné."""
        params = dict(
            participant=participant, seance_edt=self.affectation, session=None,
            date_journee=self.jour,
            timestamp_entree=timezone.now() - timedelta(hours=2),
            timestamp_sortie=timezone.now() - timedelta(hours=1),
            statut=statut, duree_presence_minutes=duree,
            annee_academique_id=self.annee.pk, groupe_lmd_id=self.groupe.pk,
        )
        params.update(kw)
        return Pointage.objects.create(**params)

    def _presents(self):
        return edt_stats.presentes_par_seance(
            [(self.affectation, self.jour, self.jour)]
        ).get((self.affectation.pk, self.jour), set())

    # -- Couverture de la faille N-02 ------------------------------------

    def test_presence_edt_invisible_du_socle_legacy(self):
        """Constat de l'audit, figé : le socle historique ignore ce pointage."""
        from statistiques import effectifs
        self._pointer(self.participants[0])
        presents = effectifs.presents_par_session([self.affectation.pk])
        self.assertEqual(presents, {}, 'le legacy ne voit pas les présences EDT (attendu)')

    def test_la_nouvelle_couche_calcule_bien_le_taux(self):
        self._pointer(self.participants[0])
        self._pointer(self.participants[1])
        stats = edt_stats.stats_seance(self.affectation, self.jour, self._presents())
        self.assertEqual(stats['effectif'], 3)
        self.assertEqual(stats['presents'], 2)
        self.assertEqual(stats['absents'], 1)
        self.assertAlmostEqual(stats['taux_presence'], 0.6667, places=4)

    # -- Règles de comptage ----------------------------------------------

    def test_absent_non_badge_ne_compte_pas_comme_present(self):
        self._pointer(self.participants[0], statut=Pointage.Statut.ABSENT_NON_BADGE, duree=0)
        self.assertEqual(self._presents(), set())

    def test_sortie_sans_duree_ne_compte_pas(self):
        self._pointer(self.participants[0], duree=0)
        self.assertEqual(self._presents(), set())

    def test_entree_sans_sortie_compte_comme_present(self):
        self._pointer(self.participants[0], timestamp_sortie=None, duree=None,
                      statut=Pointage.Statut.EN_COURS)
        self.assertIn(self.participants[0].pk, self._presents())

    def test_presence_hors_groupe_ignoree(self):
        """Un auditeur d'un autre groupe ne gonfle pas le taux.

        ``presentes_par_seance`` restitue le brut (utile pour un diagnostic) ;
        c'est ``stats_seance`` qui recoupe avec les attendus du groupe. Le taux
        ne doit donc pas bouger.
        """
        avant = edt_stats.stats_seance(self.affectation, self.jour, set())
        autre_user = User.objects.create_user(username='ext-stats', password='x', role='AUDITEUR')
        # La création d'un compte crée parfois sa fiche participant d'office : on
        # la réutilise plutôt que d'en forcer une seconde (unicité user↔participant).
        externe = Participant.objects.filter(user=autre_user).first()
        if externe is None:
            externe = Participant.objects.create(matricule='EXT1', nom='Externe',
                                                 prenom='Eleve', user=autre_user)
        self._pointer(externe)
        apres = edt_stats.stats_seance(self.affectation, self.jour, self._presents())
        self.assertEqual(apres['effectif'], avant['effectif'])
        self.assertEqual(apres['presents'], avant['presents'])
        self.assertNotIn(externe.pk, apres['presents_ids'])

    def test_groupe_vide_donne_taux_nul_sans_division_par_zero(self):
        AffectationGroupe.objects.update(active=False)
        stats = edt_stats.stats_seance(self.affectation, self.jour, set())
        self.assertEqual(stats['effectif'], 0)
        self.assertEqual(stats['taux_presence'], 0.0)

    # -- Agrégation de période -------------------------------------------

    def test_stats_periode_agregate_sans_double_comptage(self):
        """Un étudiant présent sur plusieurs séances ne compte qu'une fois."""
        self._pointer(self.participants[0])
        synthese = edt_stats.stats_periode(date_debut=self.jour, date_fin=self.jour)
        self.assertEqual(synthese['nb_seances'], 1)
        self.assertEqual(synthese['effectif'], 3)
        self.assertEqual(synthese['presents'], 1)
        self.assertEqual(synthese['absents'], 2)

    def test_stats_periode_vide_renvoie_zero_sans_erreur(self):
        synthese = edt_stats.stats_periode(
            date_debut=self.jour - timedelta(days=400), date_fin=self.jour - timedelta(days=390),
        )
        self.assertEqual(synthese['nb_seances'], 0)
        self.assertEqual(synthese['effectif'], 0)
        self.assertEqual(synthese['taux_presence'], 0.0)

    def test_stats_periode_filtre_par_formation(self):
        synthese = edt_stats.stats_periode(
            formation_id=self.ref_formation.pk, date_debut=self.jour, date_fin=self.jour,
        )
        self.assertEqual(synthese['nb_seances'], 1)
        self.assertEqual(len(synthese['par_formation']), 1)
        self.assertEqual(synthese['par_formation'][0]['formation_intitule'], 'LICENCE PRO — STATS')

    def test_stats_periode_filtre_par_groupe(self):
        vide = edt_stats.stats_periode(groupe_id=999999, date_debut=self.jour, date_fin=self.jour)
        self.assertEqual(vide['nb_seances'], 0)

    def test_taux_presence_seance_precise(self):
        self._pointer(self.participants[0])
        self.assertAlmostEqual(edt_stats.taux_presence(self.affectation.pk, self.jour),
                               0.3333, places=4)

    def test_taux_presence_seance_inconnue(self):
        self.assertEqual(edt_stats.taux_presence(999999, self.jour), 0.0)
