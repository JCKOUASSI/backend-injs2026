"""Lot L2 — tests campagnes, concours/sélection et classement.

Couvre : workflow de campagne, refus de candidature hors campagne ouverte,
capacité de salle, double session de surveillant, verrouillage des notes,
historique des corrections, classement reproductible et publication.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from admissions import concours_services
from admissions.models import (
    CampagneAdmission,
    Candidat,
    Candidature,
    ClassementConcours,
    ConvocationEpreuve,
    Epreuve,
    NoteConcours,
    SurveillanceEpreuve,
)
from authentication.models import User
from formations.models import RefFormation, RefSalle, RefSite
from scolarite.models import AnneeAcademique, JournalScolarite, Niveau


def make_user(username, role='SECRETARIAT'):
    return User.objects.create_user(username=username, password='pass', role=role)


class ConcoursBase(TestCase):
    """Fixture : campagne OUVERTE + 2 épreuves + candidatures."""

    @classmethod
    def setUpTestData(cls):
        # Les dates sont exprimées RELATIVEMENT au jour d'exécution du test.
        # Avant, elles étaient codées en dur (2026-09-01 → 2026-09-30) : le
        # scénario « campagne ouverte » expirait le jour où cette date était
        # atteinte (le 30/09/2026), rendant le test non reproductible. Le
        # comportement métier n'est pas modifié : c'est uniquement le jeu de
        # données du test qui devient indépendant du calendrier.
        aujourd_hui = timezone.localdate()
        J = timedelta
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027',
            date_debut=aujourd_hui - J(days=60),
            date_fin=aujourd_hui + J(days=300), courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.site = RefSite.objects.create(nom='Campus INJS')
        cls.salle = RefSalle.objects.create(site=cls.site, nom='Amphi A', capacite=30)

        cls.campagne = CampagneAdmission.objects.create(
            libelle='Entrée L1 STAPS 2026', annee_academique=cls.annee,
            ref_formation=cls.formation,
            date_ouverture=aujourd_hui - J(days=30),
            date_fermeture=aujourd_hui + J(days=30),
            quota_admissibles=2, quota_admis=1,
        )
        cls.ecrit = Epreuve.objects.create(
            campagne=cls.campagne, type=Epreuve.Type.ECRIT, intitule='Écrit d’admissibilité',
            date=aujourd_hui - J(days=15), heure_debut='08:00', duree_minutes=120,
            centre=None, salle=cls.salle, coefficient=2,
        )
        cls.oral = Epreuve.objects.create(
            campagne=cls.campagne, type=Epreuve.Type.ORAL, intitule='Oral d’admission',
            date=aujourd_hui - J(days=10), heure_debut='09:00', duree_minutes=30, coefficient=1,
        )
        cls.candidatures = []
        for i, (nom, prenom) in enumerate([
            ('Kouadio', 'Aristide'), ('Bamba', 'Fatou'), ('Traoré', 'Moussa'),
        ]):
            candidat = Candidat.objects.create(nom=nom, prenom=prenom)
            cls.candidatures.append(Candidature.objects.create(
                candidat=candidat, annee_academique=cls.annee,
                ref_formation=cls.formation, niveau=cls.niveau,
                campagne=cls.campagne, statut=Candidature.Statut.EN_ETUDE,
            ))

    @classmethod
    def _noter_tout(cls):
        notes = [
            (0, Decimal('14'), Decimal('10')),   # total = 14*2 + 10 = 38
            (1, Decimal('12'), Decimal('12')),   # total = 12*2 + 12 = 36
            (2, Decimal('8'),  Decimal('9')),    # total = 8*2 + 9 = 25
        ]
        for index, note_ecrit, note_oral in notes:
            concours_services.enregistrer_note(cls.ecrit, cls.candidatures[index], note=note_ecrit)
            concours_services.enregistrer_note(cls.oral, cls.candidatures[index], note=note_oral)


class CampagneWorkflowTests(ConcoursBase):
    def test_workflow_campagne_complet(self):
        campagne = CampagneAdmission.objects.create(
            libelle='Campagne test', annee_academique=self.annee,
            ref_formation=self.formation,
        )
        concours_services.appliquer_transition_campagne(campagne, S('PLANIFIEE'))
        concours_services.appliquer_transition_campagne(campagne, S('OUVERTE'))
        self.assertEqual(campagne.statut, CampagneAdmission.Statut.OUVERTE)
        concours_services.appliquer_transition_campagne(campagne, S('CLOTUREE'))
        self.assertEqual(campagne.statut, CampagneAdmission.Statut.CLOTUREE)
        # ARCHIVEE : transition finale autorisée, ensuite plus rien.
        concours_services.appliquer_transition_campagne(campagne, S('ARCHIVEE'))
        with self.assertRaises(ValidationError):
            concours_services.appliquer_transition_campagne(campagne, S('OUVERTE'))

    def test_transition_interdite_journalisee(self):
        avec_avant = JournalScolarite.objects.filter(action='CAMPAGNE_TRANSITION').count()
        with self.assertRaises(ValidationError):
            concours_services.appliquer_transition_campagne(self.campagne, S('OUVERTE'))
        avec_apres = JournalScolarite.objects.filter(action='CAMPAGNE_TRANSITION').count()
        self.assertEqual(avec_avant, avec_apres)  # transition refusée → pas de journal

    def test_candidature_sur_campagne_cloturee_refusee(self):
        for statut in (S('PLANIFIEE'), S('OUVERTE'), S('CLOTUREE')):
            concours_services.appliquer_transition_campagne(self.campagne, statut)
        candidat = Candidat.objects.create(nom='Nouveau', prenom='Candidat')
        candidature = Candidature(
            candidat=candidat, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau,
            campagne=self.campagne,
        )
        with self.assertRaises(ValidationError):
            candidature.full_clean(exclude=['numero'])

    def test_candidature_sur_campagne_ouverte_acceptee(self):
        for statut in (S('PLANIFIEE'), S('OUVERTE')):
            concours_services.appliquer_transition_campagne(self.campagne, statut)
        self.campagne.verifier_ouverture_candidature()  # OUVERTE + dates en cours : OK




class ConcoursReglesTests(ConcoursBase):
    """Règles : capacité de salle, double session, verrouillage des notes."""

    def test_capacite_salle_respectee_a_la_generation(self):
        petite_salle = RefSalle.objects.create(site=self.site, nom='Salle B', capacite=2)
        epreuve = Epreuve.objects.create(
            campagne=self.campagne, type=Epreuve.Type.ECRIT, intitule='Écrit petite salle',
            date=(timezone.localdate() - timedelta(days=14)), heure_debut='08:00', salle=petite_salle,
        )
        crees = concours_services.generer_convocations(epreuve)
        self.assertEqual(crees, 2)  # capacité 2 → seules 2 convocations
        self.assertEqual(ConvocationEpreuve.objects.filter(epreuve=epreuve).count(), 2)

    def test_convocation_manuelle_sur_capacite_atteinte_refusee(self):
        epreuve = Epreuve.objects.create(
            campagne=self.campagne, type=Epreuve.Type.ECRIT, intitule='Écrit capacité 1',
            date=(timezone.localdate() - timedelta(days=13)), heure_debut='08:00',
            salle=RefSalle.objects.create(site=self.site, nom='Salle C', capacite=1),
        )
        ConvocationEpreuve.objects.create(epreuve=epreuve, candidature=self.candidatures[0])
        excessif = ConvocationEpreuve(epreuve=epreuve, candidature=self.candidatures[1])
        with self.assertRaises(ValidationError):
            excessif.full_clean()

    def test_surveillant_double_session_refusee(self):
        surveillant = make_user('surveillant1', role='ENCADRANT')
        epreuve_concurrente = Epreuve.objects.create(
            campagne=self.campagne, type=Epreuve.Type.ORAL, intitule='Oral simultané',
            date=self.ecrit.date, heure_debut='09:00', duree_minutes=120,  # chevauche 08:00+120
        )
        SurveillanceEpreuve.objects.create(epreuve=self.ecrit, surveillant=surveillant)
        conflit = SurveillanceEpreuve(epreuve=epreuve_concurrente, surveillant=surveillant)
        with self.assertRaises(ValidationError):
            conflit.full_clean()

    def test_surveillant_sessions_distinctes_acceptees(self):
        surveillant = make_user('surveillant2', role='ENCADRANT')
        SurveillanceEpreuve.objects.create(epreuve=self.ecrit, surveillant=surveillant)
        # L'oral est un autre jour : aucune conflictualité.
        SurveillanceEpreuve.objects.create(epreuve=self.oral, surveillant=surveillant)
        self.assertEqual(SurveillanceEpreuve.objects.filter(surveillant=surveillant).count(), 2)

    def test_notes_verrouillees_non_modifiables(self):
        concours_services.enregistrer_note(self.ecrit, self.candidatures[0], note=Decimal('14'))
        concours_services.verrouiller_epreuve(self.ecrit)
        with self.assertRaises(ValidationError):
            concours_services.enregistrer_note(self.ecrit, self.candidatures[0], note=Decimal('18'))

    def test_correction_note_conserve_ancienne_et_nouvelle_valeur(self):
        concours_services.enregistrer_note(self.ecrit, self.candidatures[0], note=Decimal('14'))
        note_obj = NoteConcours.objects.get(epreuve=self.ecrit, candidature=self.candidatures[0])
        concours_services.enregistrer_note(self.ecrit, self.candidatures[0], note=Decimal('16'))
        historique = note_obj.historique.first()
        self.assertIsNotNone(historique)
        self.assertEqual(historique.ancienne_valeur, Decimal('14.00'))
        self.assertEqual(historique.nouvelle_valeur, Decimal('16.00'))
        # Décision audité (journal).
        self.assertTrue(JournalScolarite.objects.filter(
            action='CONCOURS_NOTE_CORRIGEE', objet_id=note_obj.pk,
        ).exists())


class ClassementTests(ConcoursBase):
    def test_classement_reproductible_avec_quotas(self):
        self._noter_tout()
        lignes = concours_services.calculer_classement(self.campagne)
        # Scores : 38 > 36 > 25
        self.assertEqual([l.rang for l in lignes], [1, 2, 3])
        self.assertEqual(
            [l.score_total for l in lignes],
            [Decimal('38.00'), Decimal('36.00'), Decimal('25.00')],
        )
        self.assertEqual(lignes[0].liste, ClassementConcours.Liste.ADMISSIBLE)
        self.assertEqual(lignes[1].liste, ClassementConcours.Liste.ADMISSIBLE)
        self.assertEqual(lignes[2].liste, ClassementConcours.Liste.LISTE_ATTENTE)
        # Reproductibilité : recalcul → mêmes rangs et listes.
        lignes2 = concours_services.calculer_classement(self.campagne)
        self.assertEqual(
            [(l.rang, str(l.score_total), l.liste) for l in lignes2],
            [(l.rang, str(l.score_total), l.liste) for l in lignes],
        )

    def test_classement_candidature_sans_note_exclue(self):
        self._noter_tout()
        extra = Candidature.objects.create(
            candidat=Candidat.objects.create(nom='Absent', prenom='Noté nulle part'),
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, campagne=self.campagne,
            statut=Candidature.Statut.EN_ETUDE,
        )
        lignes = concours_services.calculer_classement(self.campagne)
        self.assertFalse(any(l.candidature_id == extra.pk for l in lignes))

    def test_publication_bloque_recalcul(self):
        self._noter_tout()
        concours_services.calculer_classement(self.campagne)
        concours_services.publier_classement(self.campagne)
        self.assertTrue(ClassementConcours.objects.filter(campagne=self.campagne, publie=True).exists())
        with self.assertRaises(ValidationError):
            concours_services.calculer_classement(self.campagne)


class ConcoursAPITests(ConcoursBase):
    def setUp(self):
        self.client = APIClient()

    def test_anonyme_refuse(self):
        res = self.client.get('/api/admissions/campagnes/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cycle_campagne_via_api(self):
        self.client.force_authenticate(make_user('sec_api_l2', role='SECRETARIAT'))
        res = self.client.post('/api/admissions/campagnes/', {
            'libelle': 'Campagne API', 'annee_academique_id': self.annee.pk,
            'ref_formation_id': self.formation.pk,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        campagne_id = res.data['id']
        res = self.client.post(f'/api/admissions/campagnes/{campagne_id}/transition/',
                               {'statut': 'PLANIFIEE'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['statut'], 'PLANIFIEE')
        # Transition interdite → 400
        res = self.client.post(f'/api/admissions/campagnes/{campagne_id}/transition/',
                               {'statut': 'ARCHIVEE'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_notes_via_api_et_verrouillage(self):
        self.client.force_authenticate(make_user('sec_api_l2b', role='SECRETARIAT'))
        res = self.client.post(f'/api/admissions/epreuves/{self.ecrit.pk}/notes/', {
            'candidature_id': self.candidatures[0].pk, 'note': '13',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        res = self.client.post(f'/api/admissions/epreuves/{self.ecrit.pk}/verrouiller/', {})
        self.assertEqual(res.status_code, 200)
        res = self.client.post(f'/api/admissions/epreuves/{self.ecrit.pk}/notes/', {
            'candidature_id': self.candidatures[0].pk, 'note': '19',
        }, format='json')
        self.assertEqual(res.status_code, 400)
S = CampagneAdmission.Statut
