"""Lot B — vue « Cours / Enseignements » (GET /api/scolarite/pedagogie/cours/).

Vérifie la jointure chaîne LMD : affectation pédagogique (ECUE × groupe ×
enseignant × type) + planning EDT + effectif du groupe + séances réalisées
(pointages de séance LMD du lot C) + filtres.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from formations.models import Formateur, RefFormation
from presences.models import Pointage
from scolarite.models import (
    AffectationGroupe, AffectationPedagogique, AnneeAcademique, ECUE, Groupe,
    InscriptionAdministrative, Maquette, Niveau, Semestre, StatutEtudiant, UE,
    DossierEtudiant,
)


class CoursLmdTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.admin = User.objects.create_user(username='cours-admin', password='x', role='ADMIN')
        cls.client = APIClient()
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=today - timedelta(weeks=3),
            date_fin=today + timedelta(weeks=40), courante=True,
        )
        cls.cycle = RefFormation.objects.create(
            intitule='LICENCE ADMINISTRATION', code='LIC-ADM',
            type_diplome='LICENCE', duree_annees=3, nb_semestres=6, nb_credites=180,
        )
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.semestre = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        # Maquette en brouillon : composer UE/ECUE sous maquette ACTIVE est
        # interdit par l'immunité de maquette (règle scolarite, conservée).
        cls.maquette = Maquette.objects.create(annee_academique=cls.annee,
                                               ref_formation=cls.cycle, niveau=cls.niveau,
                                               statut='BROUILLON')
        cls.ue = UE.objects.create(maquette=cls.maquette, semestre=cls.semestre,
                                   code='UE1.1', intitule='Fondamentaux')
        cls.ecue = ECUE.objects.create(ue=cls.ue, code='ECUE1.1.1', intitule='Droit public',
                                       credits=6)
        cls.groupe = Groupe.objects.create(annee_academique=cls.annee, niveau=cls.niveau,
                                           ref_formation=cls.cycle, nom='L1-G1', capacite_max=25)
        cls.formateur = Formateur.objects.create(numerobadge='FB-1', nom='Traoré', prenom='Awa')
        cls.ap = AffectationPedagogique.objects.create(
            annee_academique=cls.annee, ref_formation=cls.cycle, niveau=cls.niveau,
            semestre=cls.semestre, ue=cls.ue, ecue=cls.ecue, groupe=cls.groupe,
            enseignant=cls.formateur, type_enseignement='CM', volume_horaire=20,
            statut='PLANIFIEE',
        )
        # Planning EDT : un créneau hebdo sur le même groupe/cycle.
        cls.template = CreneauTemplate.objects.create(jour='MARDI', heure_debut='08:00',
                                                       heure_fin='10:00')
        cls.edt = EmploiDuTemps.objects.create(
            annee_academique=cls.annee, population_type='ANNEE', population_id=0,
            statut='PUBLIE', semaine_debut=1, semaine_fin=10, rentree=cls.annee.date_debut,
            cree_par=cls.admin,
        )
        cls.creneau = AffectationCreneau.objects.create(
            emploi_du_temps=cls.edt, creneau_template=cls.template,
            semaine_debut=1, semaine_fin=10, groupe=cls.groupe,
            formation=cls.cycle, salle_nom='Amphi 2', intitule='Droit public CM',
            # Lot L5 : le rattachement séance → cours est EXPLICITE. L'ancienne
            # jointure par (groupe, cycle) est supprimée : sans cette clé, la
            # séance n'apparaît sur aucun cours.
            affectation_pedagogique=cls.ap,
        )
        # Deux auditeurs inscrits dans le groupe.
        statut_actif = StatutEtudiant.objects.create(code='ACTIF', libelle='Actif')
        for i in range(2):
            participant = _creer_participant(f'cours-i{i}', f'MAT-C{i}')
            inscription = InscriptionAdministrative.objects.create(
                etudiant=DossierEtudiant.objects.create(participant=participant,
                                                         statut=statut_actif),
                annee_academique=cls.annee, ref_formation=cls.cycle, niveau=cls.niveau,
                statut='VALIDEE', statut_etudiant=statut_actif,
            )
            AffectationGroupe.objects.create(groupe=cls.groupe, inscription=inscription,
                                             active=True)

    def _get(self, **params):
        url = '/api/scolarite/pedagogie/cours/'
        if params:
            url += '?' + '&'.join(f'{k}={v}' for k, v in params.items())
        return self.client.get(url)

    def test_ligne_de_cours_complete(self):
        self.client.force_authenticate(self.admin)
        reponse = self._get(annee=self.annee.pk)
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(reponse.data['total'], 1)
        ligne = reponse.data['resultats'][0]
        self.assertEqual(ligne['ecue'], 'ECUE1.1.1')
        self.assertEqual(ligne['ecue_intitule'], 'Droit public')
        self.assertEqual(ligne['credits'], 6)
        self.assertEqual(ligne['type_enseignement'], 'CM')
        self.assertEqual(ligne['groupe_nom'], 'L1-G1')
        self.assertEqual(ligne['effectif'], 2)
        self.assertEqual(ligne['capacite_max'], 25)
        self.assertEqual(ligne['enseignant'], 'Traoré Awa')
        self.assertEqual(ligne['nb_seances_planifiees'], 10)   # 1 créneau × 10 semaines
        self.assertEqual(ligne['nb_seances_realisees'], 0)
        self.assertEqual(ligne['planning'][0]['jour'], 'Mardi')
        self.assertEqual(ligne['planning'][0]['salle'], 'Amphi 2')
        self.assertEqual(ligne['cycle'], 'LICENCE ADMINISTRATION')

    def test_seances_realisees_suivent_les_pointages(self):
        self.client.force_authenticate(self.admin)
        debut, fin = _horodatages(self.creneau)
        Pointage.objects.create(
            seance_edt=self.creneau, date_journee=date.today(),
            timestamp_entree=debut, timestamp_sortie=fin,
            statut=Pointage.Statut.TERMINE, statut_assiduite=Pointage.StatutAssiduite.PRESENT,
        )
        Pointage.objects.create(
            seance_edt=self.creneau, date_journee=date.today() + timedelta(days=1),
            timestamp_entree=debut, timestamp_sortie=fin,
            statut=Pointage.Statut.TERMINE,
        )
        ligne = self._get(annee=self.annee.pk).data['resultats'][0]
        self.assertEqual(ligne['nb_seances_realisees'], 2)

    def test_filtres_groupe_et_type(self):
        self.client.force_authenticate(self.admin)
        autre_groupe = Groupe.objects.create(annee_academique=self.annee, niveau=self.niveau,
                                             ref_formation=self.cycle, nom='L1-G2')
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.cycle, niveau=self.niveau,
            semestre=self.semestre, ue=self.ue, ecue=self.ecue, groupe=autre_groupe,
            enseignant=self.formateur, type_enseignement='TD',
        )
        self.assertEqual(self._get(annee=self.annee.pk).data['total'], 2)
        self.assertEqual(self._get(annee=self.annee.pk, groupe=autre_groupe.pk).data['total'], 1)
        self.assertEqual(self._get(annee=self.annee.pk, type_enseignement='TD').data['total'], 1)

    def test_annee_par_defaut_courante(self):
        autre_annee = AnneeAcademique.objects.create(
            libelle='2027-2028', date_debut=date(2027, 10, 1), date_fin=date(2028, 9, 30))
        AffectationPedagogique.objects.create(
            annee_academique=autre_annee, ref_formation=self.cycle, niveau=self.niveau,
            semestre=self.semestre, ue=self.ue, ecue=self.ecue, groupe=self.groupe,
            enseignant=self.formateur,
        )
        self.client.force_authenticate(self.admin)
        reponse = self._get()
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['total'], 1)  # seulement l'année courante

    def test_exige_authentification(self):
        reponse = self.client.get('/api/scolarite/pedagogie/cours/')
        self.assertIn(reponse.status_code, (401, 403))


def _creer_participant(username, matricule):
    from formations.models import Participant
    user = User.objects.create_user(username=username, password='x', role='AUDITEUR')
    participant = Participant.objects.filter(user=user).first()
    if participant is None:
        participant = Participant.objects.create(matricule=matricule, nom='Nom', prenom='Prénom',
                                                 user=user)
    return participant


def _horodatages(creneau):
    from django.utils import timezone as tz
    from datetime import datetime
    today = tz.localdate()
    debut = tz.make_aware(datetime.combine(today, creneau.creneau_template.heure_debut))
    fin = tz.make_aware(datetime.combine(today, creneau.creneau_template.heure_fin))
    return debut, fin
