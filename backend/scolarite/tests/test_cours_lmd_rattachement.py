"""Lot L5 — Rattachement EXPLICIT des séances EDT aux cours (API « Cours »).

Avant L5, `GET /api/scolarite/pedagogie/cours/` déduisait les séances d'un cours
par heuristique `(groupe, cycle)`. Cette déduction est supprimée : la clé
étrangère `AffectationCreneau.affectation_pedagogique` (lot L1) est la seule
source de vérité, sans repli.

Ces tests prouvent :
- une séance avec FK apparaît sur le SEUL bon cours ;
- une séance n'est jamais affichée sur un cours qui ne la référence pas ;
- une séance sans FK n'est rattachée à aucun cours et reste détectable ;
- aucun doublon de séance n'apparaît entre plusieurs cours d'un même groupe ;
- les indicateurs de couverture exposent la régularisation à faire.
"""

from datetime import date, timedelta
from pathlib import Path

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from formations.models import Formateur, RefFormation
from presences.models import Pointage
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, Groupe, Maquette, Niveau,
    Parcours, Semestre, TypeFormation, UE,
)

URL = '/api/scolarite/pedagogie/cours/'


def _horodatages(creneau):
    """Entrée/sortie plausibles calées sur la durée du créneau."""
    ct = creneau.creneau_template
    debut = timezone.localtime().replace(hour=ct.heure_debut.hour,
                                         minute=ct.heure_debut.minute,
                                         second=0, microsecond=0)
    fin = debut + timedelta(hours=ct.heure_fin.hour - ct.heure_debut.hour)
    return (debut, fin)


class RattachementExpliciteTests(TestCase):
    """Groupe unique, 3 cours (CM/TD/TP), séances rattachées explicitement."""

    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=today - timedelta(weeks=3),
            date_fin=today + timedelta(weeks=40), courante=True,
        )
        type_formation = TypeFormation.objects.create(
            code='LIC', libelle='Licence professionnelle', actif=True,
        )
        niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        semestre = Semestre.objects.create(
            niveau=niveau, numero=1, libelle='Semestre 1', actif=True,
        )
        cycle = RefFormation.objects.create(intitule='LICENCE PRO — L1')
        parcours = Parcours.objects.create(
            ref_formation=cycle, type_formation=type_formation,
            code='P-PRO', intitule='Parcours professionnel', actif=True,
        )
        groupe = Groupe.objects.create(
            annee_academique=cls.annee, niveau=niveau, ref_formation=cycle,
            nom='L1-G1', capacite_max=30,
        )
        maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cycle,
            parcours=parcours, niveau=niveau,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=semestre, code='UE1',
            intitule='Unité 1', credits=6,
        )
        formateur = Formateur.objects.create(
            numerobadge='FB-L5-0001', nom='Traoré', prenom='Awa',
        )
        admin = User.objects.create_user(
            username='l5-admin', password='x', role=User.Role.INJS_ADMIN,
        )

        # --- 3 cours distincts sur le MÊME groupe (cas CM / TD / TP) ---
        cls.cours = {}
        for suffixe, code, type_enseignement in (
            ('CM', 'ECUE1', 'CM'), ('TD', 'ECUE2', 'TD'), ('TP', 'ECUE3', 'TP'),
        ):
            ecue = ECUE.objects.create(
                ue=ue, code=code, intitule=f'Enseignement {suffixe}',
                credits=4, volume_cm=20, volume_td=10, volume_tp=10,
            )
            cls.cours[suffixe] = AffectationPedagogique.objects.create(
                annee_academique=cls.annee, ref_formation=cycle, parcours=parcours,
                niveau=niveau, semestre=semestre, ue=ue, ecue=ecue, groupe=groupe,
                enseignant=formateur, type_enseignement=type_enseignement,
                volume_horaire=20, statut=AffectationPedagogique.Statut.VALIDEE,
            )

        cls.edt = EmploiDuTemps.objects.create(
            annee_academique=cls.annee, population_type='ANNEE', population_id=0,
            statut='PUBLIE', semaine_debut=1, semaine_fin=10,
            rentree=cls.annee.date_debut, cree_par=admin,
        )
        cls.template = CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut='08:00', heure_fin='10:00',
        )
        cls.groupe = groupe
        cls.cycle = cycle
        cls.admin = admin

    def _seance(self, affectation_pedagogique, intitule='Séance'):
        """Crée une séance rattachée au cours donné (FK explicite)."""
        return AffectationCreneau.objects.create(
            emploi_du_temps=self.edt, creneau_template=self.template,
            semaine_debut=1, semaine_fin=10, groupe=self.groupe,
            formation=self.cycle, salle_nom='Amphi 1', intitule=intitule,
            affectation_pedagogique=affectation_pedagogique,
        )

    def _seance_orpheline(self, intitule='Séance non rattachée'):
        return AffectationCreneau.objects.create(
            emploi_du_temps=self.edt, creneau_template=self.template,
            semaine_debut=1, semaine_fin=10, groupe=self.groupe,
            formation=self.cycle, salle_nom='Amphi 1', intitule=intitule,
        )

    def _lignes(self):
        reponse = self.client.get(URL, {'annee': self.annee.pk})
        self.assertEqual(reponse.status_code, 200, reponse.data)
        return {ligne['ecue']: ligne for ligne in reponse.data['resultats']}

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    # -- 1. Une séance avec FK apparaît sur le bon cours ------------------

    def test_une_seance_rattachee_apparait_sur_son_seul_cours(self):
        seance = self._seance(self.cours['TD'], 'TD de la semaine')
        lignes = self._lignes()
        self.assertEqual(len(lignes), 3)
        self.assertEqual([s['id'] for s in lignes['ECUE2']['planning']], [seance.pk])
        for ecue, ligne in lignes.items():
            if ecue == 'ECUE2':
                continue
            self.assertNotIn(
                seance.pk, [s['id'] for s in ligne['planning']],
                f'séance apparue à tort sur {ecue}',
            )

    # -- 2. Aucun doublon entre cours d'un même groupe (exigence 9) -------

    def test_chaque_cours_ne_recoit_que_ses_propres_seances(self):
        for suffixe in ('CM', 'TD', 'TP'):
            self._seance(self.cours[suffixe], f'Séance {suffixe}')
        lignes = self._lignes()
        self.assertEqual(len(lignes), 3)
        for suffixe, code in (('CM', 'ECUE1'), ('TD', 'ECUE2'), ('TP', 'ECUE3')):
            planning = lignes[code]['planning']
            self.assertEqual(len(planning), 1, suffixe)
            seance = AffectationCreneau.objects.get(pk=planning[0]['id'])
            self.assertEqual(seance.affectation_pedagogique_id, self.cours[suffixe].pk)
        # Chaque séance n'apparaît qu'une seule fois dans toute la réponse.
        ids = [s['id'] for ligne in lignes.values() for s in ligne['planning']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_une_seance_n_apparait_jamais_sur_un_autre_cours(self):
        seance_cm = self._seance(self.cours['CM'], 'CM')
        self._seance(self.cours['TD'], 'TD')
        self._seance(self.cours['TP'], 'TP')
        lignes = self._lignes()
        apparitions = [
            ecue for ecue, ligne in lignes.items()
            if seance_cm.pk in [s['id'] for s in ligne['planning']]
        ]
        self.assertEqual(apparitions, ['ECUE1'])

    # -- 3. Une séance sans FK n'est rattachée à aucun cours --------------

    def test_une_seance_sans_fk_n_est_rattachee_a_aucun_cours(self):
        orpheline = self._seance_orpheline()
        for ligne in self._lignes().values():
            self.assertNotIn(orpheline.pk, [s['id'] for s in ligne['planning']])
            self.assertEqual(ligne['nb_seances_rattachees'], 0)
            self.assertEqual(ligne['planning'], [])
        # La séance existe toujours : elle n'est ni supprimée ni modifiée.
        orpheline.refresh_from_db()
        self.assertIsNone(orpheline.affectation_pedagogique_id)
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_les_seances_non_rattachees_sont_detectables(self):
        self._seance_orpheline()
        ligne = self._lignes()['ECUE1']
        self.assertEqual(ligne['nb_seances_non_rattachees'], 1)
        self.assertTrue(ligne['regularisation_requise'])
        # Un cours qui possède ses séances n'est plus signalé.
        self._seance(self.cours['CM'])
        lignes = self._lignes()
        self.assertFalse(lignes['ECUE1']['regularisation_requise'])
        self.assertEqual(lignes['ECUE1']['nb_seances_non_rattachees'], 1)

    def test_les_seances_realisees_suivent_le_rattachement(self):
        seance = self._seance(self.cours['CM'])
        debut, fin = _horodatages(seance)
        for jour in (date.today(), date.today() + timedelta(days=1)):
            Pointage.objects.create(
                seance_edt=seance, date_journee=jour,
                timestamp_entree=debut, timestamp_sortie=fin,
                statut=Pointage.Statut.TERMINE,
            )
        lignes = self._lignes()
        self.assertEqual(lignes['ECUE1']['nb_seances_realisees'], 2)
        # Les autres cours n'héritent pas des pointages de cette séance.
        self.assertEqual(lignes['ECUE2']['nb_seances_realisees'], 0)
        self.assertEqual(lignes['ECUE3']['nb_seances_realisees'], 0)

    def test_une_seance_inactive_est_ignoree(self):
        seance = self._seance(self.cours['CM'])
        seance.actif = False
        seance.save(update_fields=['actif'])
        ligne = self._lignes()['ECUE1']
        self.assertEqual(ligne['nb_seances_rattachees'], 0)
        self.assertEqual(ligne['planning'], [])

    # -- 4. Non-régression et propreté ------------------------------------

    def test_aucune_donnee_metier_n_est_creee_par_l_api(self):
        """L'API est en lecture seule : elle ne crée ni ne supprime rien."""
        avant_seances = AffectationCreneau.objects.count()
        avant_cours = AffectationPedagogique.objects.count()
        self.assertEqual(len(self._lignes()), 3)
        self.assertEqual(AffectationCreneau.objects.count(), avant_seances)
        self.assertEqual(AffectationPedagogique.objects.count(), avant_cours)

    def test_les_valeurs_existantes_du_contrat_sont_conservees(self):
        """Aucun champ historique n'est retiré (règle 6 : ajout additif)."""
        ligne = self._lignes()['ECUE1']
        for champ in ('id', 'annee', 'cycle', 'parcours', 'niveau', 'semestre', 'ue',
                      'ecue', 'ecue_intitule', 'credits', 'type_enseignement',
                      'volume_horaire', 'groupe', 'groupe_nom', 'effectif',
                      'capacite_max', 'enseignant', 'dates', 'statut',
                      'nb_seances_planifiees', 'nb_seances_realisees', 'planning'):
            self.assertIn(champ, ligne, champ)

    def test_absence_de_reference_cpfae_dans_l_api(self):
        source = (Path(__file__).resolve().parent.parent / 'cours_lmd_api.py').read_text(
            encoding='utf-8')
        for terme in ('CPFAE_ADMIN', 'CHEF_CPFAE_ADMIN', 'ROLE_CPFAE_ADMIN'):
            self.assertNotIn(terme, source, terme)

