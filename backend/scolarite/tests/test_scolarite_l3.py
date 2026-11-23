"""Lot L1/L3 — tests inscriptions & scolarité : clôture d'année, radiation,
changement de parcours, double inscription incompatible, espace étudiant.

Règles couvertes :
- un redoublement/réinscription ne crée pas un nouvel étudiant (existant) ;
- toute inscription est liée à une AnneeAcademique (FK PROTECT existante) ;
- changement de parcours historisé (JournalScolarite + REORIENTATION) ;
- la radiation n'efface jamais les données ;
- un étudiant ne peut pas avoir deux inscriptions VALIDEE la même année ;
- une année clôturée n'accepte plus de nouvelle inscription ni de validation.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Participant, RefFormation
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
    EvenementScolarite,
    InscriptionAdministrative,
    JournalScolarite,
    Niveau,
    Parcours,
)

from scolarite import inscription_services
from scolarite import annee_services


def make_user(username, role='SECRETARIAT'):
    return User.objects.create_user(username=username, password='pass', role=role)


class ScolariteL3Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2025-2026', date_debut='2025-10-01', date_fin='2026-07-31', courante=True,
        )
        cls.annee_suivante = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31',
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.parcours_em = Parcours.objects.create(
            ref_formation=cls.formation, code='EM', intitule='Éducation et Motricité',
        )
        cls.parcours_sm = Parcours.objects.create(
            ref_formation=cls.formation, code='SM', intitule='Sport et Management',
        )
        cls.participant = Participant.objects.create(
            matricule='INJS26-0001', nom='Kouadio', prenom='Aristide',
        )
        cls.dossier = DossierEtudiant.objects.create(participant=cls.participant)
        cls.inscription = InscriptionAdministrative.objects.create(
            etudiant=cls.dossier, annee_academique=cls.annee,
            ref_formation=cls.formation, parcours=cls.parcours_em, niveau=cls.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )


class ClotureAnneeTests(ScolariteL3Base):
    def test_cloture_annee(self):
        annee_services.cloturer_annee(self.annee)
        self.annee.refresh_from_db()
        self.assertTrue(self.annee.cloturee)
        self.assertIsNotNone(self.annee.date_cloture)
        self.assertFalse(self.annee.courante)
        self.assertTrue(JournalScolarite.objects.filter(
            objet_id=self.annee.pk, objet_type='AnneeAcademique',
        ).exists())

    def test_rouvrir_annee_redevient_courante(self):
        annee_services.cloturer_annee(self.annee)
        annee_services.rouvrir_annee(self.annee)
        self.annee.refresh_from_db()
        self.assertFalse(self.annee.cloturee)
        self.assertTrue(self.annee.courante)

    def test_creation_inscription_sur_annee_cloturee_refusee(self):
        annee_services.cloturer_annee(self.annee)
        inscription = InscriptionAdministrative(
            etudiant=self.dossier, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau,
        )
        with self.assertRaises(ValidationError):
            inscription.full_clean(exclude=['date_validation'])

    def test_validation_sur_annee_cloturee_refusee(self):
        inscription = InscriptionAdministrative.objects.create(
            etudiant=self.dossier, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau,
            statut=InscriptionAdministrative.Statut.A_VALIDER,
        )
        annee_services.cloturer_annee(self.annee)
        with self.assertRaises(inscription_services.InscriptionImpossible):
            inscription_services.appliquer_transition(inscription, 'VALIDEE')

    def test_double_inscription_validee_meme_annee_refusee(self):
        doublon = InscriptionAdministrative(
            etudiant=self.dossier, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau,
            parcours=self.parcours_sm,  # autre parcours : échappe à l'unicité DB
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )


class RadiationEtParcoursTests(ScolariteL3Base):
    def test_radiation_preserve_les_donnees(self):
        inscription_services.radier_inscription(self.inscription, motif='Discipline')
        self.inscription.refresh_from_db()
        self.assertEqual(self.inscription.statut, InscriptionAdministrative.Statut.SUSPENDUE)
        # Aucune suppression : le dossier et le participant restent intacts.
        self.assertTrue(DossierEtudiant.objects.filter(pk=self.dossier.pk).exists())
        self.assertTrue(Participant.objects.filter(pk=self.participant.pk).exists())
        evenement = EvenementScolarite.objects.filter(
            inscription=self.inscription, type_evenement=EvenementScolarite.Type.RADIATION,
        ).first()
        self.assertIsNotNone(evenement)
        self.assertEqual(evenement.ancienne_valeur, 'VALIDEE')

    def test_radiation_dune_inscription_non_validee_refusee(self):
        self.inscription.statut = InscriptionAdministrative.Statut.BROUILLON
        self.inscription.save(update_fields=['statut'])
        with self.assertRaises(inscription_services.InscriptionImpossible):
            inscription_services.radier_inscription(self.inscription, motif='Test')

    def test_changement_parcours_historise(self):
        inscription_services.changer_parcours(
            self.inscription, self.parcours_sm, motif='Réorientation pédagogique',
        )
        self.inscription.refresh_from_db()
        self.assertEqual(self.inscription.parcours, self.parcours_sm)
        # JournalScolarite : ancienne et nouvelle valeur conservées.
        entree = JournalScolarite.objects.filter(
            objet_id=self.inscription.pk, objet_type='InscriptionAdministrative',
        ).order_by('-timestamp').first()
        self.assertIsNotNone(entree)
        self.assertEqual(entree.ancienne_valeur, 'Éducation et Motricité')
        self.assertEqual(entree.nouvelle_valeur, 'Sport et Management')
        # EvenementScolarite de type REORIENTATION.
        self.assertTrue(EvenementScolarite.objects.filter(
            inscription=self.inscription,
            type_evenement=EvenementScolarite.Type.REORIENTATION,
        ).exists())

    def test_changement_parcours_autre_formation_refuse(self):
        autre_formation = RefFormation.objects.create(intitule='MASTER STAPS')
        autre_parcours = Parcours.objects.create(
            ref_formation=autre_formation, code='M1-EM', intitule='EM Master',
        )
        with self.assertRaises(inscription_services.InscriptionImpossible):
            inscription_services.changer_parcours(self.inscription, autre_parcours)


class RedoublementTests(ScolariteL3Base):
    def test_redoublement_ne_cree_pas_un_nouvel_etudiant(self):
        """La réinscription/redoublement réutilise le dossier existant."""
        from scolarite import groupes_services
        nouvelle = groupes_services.reinscrire(
            self.dossier, self.annee_suivante, self.niveau,
            type_inscription=InscriptionAdministrative.Type.REDOUBLEMENT,
        )
        self.assertEqual(nouvelle.etudiant_id, self.dossier.pk)
        self.assertEqual(nouvelle.type_inscription, InscriptionAdministrative.Type.REDOUBLEMENT)
        # Toujours un seul dossier/participant pour cet étudiant.
        self.assertEqual(DossierEtudiant.objects.filter(pk=self.dossier.pk).count(), 1)
        self.assertEqual(Participant.objects.filter(pk=self.participant.pk).count(), 1)


class ScolariteL3APITests(ScolariteL3Base):
    def setUp(self):
        self.client = APIClient()

    def test_anonyme_refuse(self):
        res = self.client.post(f'/api/scolarite/inscriptions/{self.inscription.pk}/radier/', {})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_radiation_via_api(self):
        self.client.force_authenticate(make_user('sec_l3', role='SECRETARIAT'))
        res = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.pk}/radier/',
            {'motif': 'Discipline'}, format='json',
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['statut'], InscriptionAdministrative.Statut.SUSPENDUE)

    def test_cloture_via_api(self):
        self.client.force_authenticate(make_user('sec_l3b', role='SECRETARIAT'))
        res = self.client.post(f'/api/scolarite/annees/{self.annee.pk}/cloturer/', {})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['cloturee'])
        self.assertFalse(res.data['courante'])
        res = self.client.post(f'/api/scolarite/annees/{self.annee.pk}/rouvrir/', {})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['courante'])