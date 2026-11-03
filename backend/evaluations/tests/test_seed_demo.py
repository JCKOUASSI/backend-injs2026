"""Évaluations d'exemple (tâche 34) : notes toujours en brouillon."""
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from authentication.models import User
from evaluations.models import (
    Evaluation, EvaluationGrade, EvaluationParticipant, SessionEvaluation,
    TypeEvaluation,
)
from formations.models import Participant, RefFormation
from scolarite.models import (
    ECUE, UE, AffectationPedagogique, AnneeAcademique, DossierEtudiant,
    InscriptionAdministrative, InscriptionPedagogique, Maquette, Niveau,
    Semestre,
)


class SeedEvaluationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='secr_eval', password='pass', role='SECRETARIAT',
        )
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01',
            date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.s1 = Semestre.objects.create(
            niveau=cls.niveau, numero=1, libelle='Semestre 1',
        )
        maquette = Maquette.objects.create(
            ref_formation=cls.formation, annee_academique=cls.annee,
            niveau=cls.niveau, statut=Maquette.Statut.BROUILLON,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=cls.s1, code='UE1',
            intitule='Unité 1', credits=6,
        )
        cls.ecue = ECUE.objects.create(
            ue=ue, code='UE1-E1', intitule='Élément 1', credits=6,
        )
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save(update_fields=['statut'])
        from formations.models import Formateur
        enseignant = Formateur.objects.create(
            nom='Enseignant', prenom='Test', specialite='STAPS',
        )
        AffectationPedagogique.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation,
            niveau=cls.niveau, semestre=cls.s1, ue=ue, ecue=cls.ecue,
            enseignant=enseignant, volume_horaire=30,
        )
        participant = Participant.objects.create(
            matricule='INJS26-0001', nom='ETU', prenom='Un',
        )
        dossier = DossierEtudiant.objects.create(participant=participant)
        cls.inscription = InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=cls.annee,
            ref_formation=cls.formation, niveau=cls.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @override_settings(INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=False)
    def test_notes_toujours_en_brouillon(self):
        call_command('seed_evaluations_demo')
        # La frontière métier tient : rien n'était automatique avant l'appel
        # explicite du seed, et la génération est passée par le service.
        self.assertEqual(TypeEvaluation.objects.filter(code__startswith='EX-').count(), 4)
        self.assertEqual(SessionEvaluation.objects.count(), 1)
        self.assertFalse(
            SessionEvaluation.objects.filter(verrouillee=True).exists(),
        )
        self.assertEqual(Evaluation.objects.count(), 1)
        assert InscriptionPedagogique.objects.exists()
        notes = EvaluationGrade.objects.all()
        self.assertEqual(notes.count(), 1)
        for note in notes:
            self.assertEqual(note.statut, 'BROUILLON')
            self.assertFalse(note.verrouillee)
        for p in EvaluationParticipant.objects.all():
            self.assertIn('[Exemple]', p.motif)

        res = self.client.get('/api/evaluations-academiques/hub/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['notes_par_statut'], {'BROUILLON': 1})
        self.assertEqual(res.data['avancement_validation'], 0.0)

        res = self.client.get('/api/evaluations-academiques/hub/notes/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['results'][0]['matricule'], 'INJS26-0001')

    def test_idempotent_puis_purge_conserve_les_ip(self):
        call_command('seed_evaluations_demo')
        call_command('seed_evaluations_demo')
        self.assertEqual(EvaluationGrade.objects.count(), 1)
        call_command('seed_evaluations_demo', '--purger')
        self.assertEqual(SessionEvaluation.objects.count(), 0)
        self.assertEqual(EvaluationGrade.objects.count(), 0)
        # Inscriptions pédagogiques : opération journalisée conservée.
        self.assertEqual(InscriptionPedagogique.objects.count(), 1)
