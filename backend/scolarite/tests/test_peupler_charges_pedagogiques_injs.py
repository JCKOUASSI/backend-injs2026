"""Peuplement des charges pédagogiques INJS : volumes MODELISE, activation
des maquettes (via finaliser), enseignants fictifs et affectations par ECUE.
"""
from datetime import date

from django.core.management import call_command
from django.test import TestCase

from formations.models import Formateur, RefFormation
from referentiels.models import RefGradeEnseignant
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, Maquette, Niveau, Semestre,
    UE,
)

GRADES = [
    'MAITRE_ASSISTANT', 'MAITRE_EPS', 'ASSISTANT', 'MAITRE_CONFERENCES',
    'PROF_AGREGE_EPS', 'PROFESSEUR_TITULAIRE',
]


class PeuplerChargesPedagogiquesTests(TestCase):
    def setUp(self):
        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1),
            date_fin=date(2027, 7, 31), courante=True, actif=True,
        )
        self.formation = RefFormation.objects.create(
            intitule='ÉDUCATION ET MOTRICITÉ — LICENCE',
            filiere_code='F01', type_diplome='LICENCE', actif=True,
        )
        self.niveau = Niveau.objects.create(code='L1', libelle='Licence 1')
        self.semestre = Semestre.objects.create(
            niveau=self.niveau, numero=1, libelle='S1')
        for code in GRADES:
            RefGradeEnseignant.objects.create(code=code, libelle=code, actif=True)
        self.maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, statut=Maquette.Statut.BROUILLON,
        )
        ue = UE.objects.create(
            maquette=self.maquette, semestre=self.semestre,
            code='EM-S1-UE01', intitule='Sciences de la vie et de la santé',
            credits=6, ordre=1,
        )
        ECUE.objects.create(
            ue=ue, code='EM-S1-UE01-EC01', ordre=1,
            intitule='Anatomie fonctionnelle du corps humain')
        ECUE.objects.create(
            ue=ue, code='EM-S1-UE01-EC02', ordre=2,
            intitule='Physiologie de l’effort')
        # UE saturante : 12 ECUE de sports collectifs (30 h MODELISE chacune)
        # remplissent deux enseignants au-delà de la cible de création —
        # la seconde passe ne doit créer aucun enseignant supplémentaire.
        ue2 = UE.objects.create(
            maquette=self.maquette, semestre=self.semestre,
            code='EM-S1-UE02', intitule='Sports collectifs',
            credits=12, ordre=2,
        )
        for rang, sport in enumerate(
                ['Football', 'Handball', 'Basketball', 'Volleyball', 'Rugby'] * 3,
                start=1):
            if rang > 12:
                break
            ECUE.objects.create(
                ue=ue2, code=f'EM-S1-UE02-EC{rang:02d}', ordre=rang,
                intitule=f'Initiation aux fondamentaux du {sport} {rang}')

    def test_peuplement_complet_et_idempotent(self):
        call_command('peupler_charges_pedagogiques_injs', sans_exemples=True)

        # La maquette est validée puis activée par la commande officielle.
        self.maquette.refresh_from_db()
        self.assertEqual(self.maquette.statut, Maquette.Statut.ACTIVE)

        # Volumes MODELISE renseignés avant activation, jamais nuls.
        for ecue in ECUE.objects.all():
            self.assertGreater(float(ecue.volume_total), 0)

        # Une affectation VALIDEE par ECUE, rattachée à un enseignant fictif
        # à la fiche complète, sans dépasser le seuil de surcharge (192 h).
        affectations = AffectationPedagogique.objects.filter(annee_academique=self.annee)
        self.assertEqual(affectations.count(), ECUE.objects.count())
        self.assertTrue(affectations.filter(
            statut=AffectationPedagogique.Statut.VALIDEE).exists())
        enseignants = Formateur.objects.filter(numerobadge__startswith='ENS-DEMO-')
        self.assertGreaterEqual(enseignants.count(), 1)
        for enseignant in enseignants:
            self.assertTrue(enseignant.nom and enseignant.prenom)
            self.assertIsNotNone(enseignant.grade_ref)
            self.assertTrue(enseignant.specialite)
            self.assertTrue(enseignant.organisation)
            self.assertTrue(enseignant.statut_enseignant)
            self.assertTrue(enseignant.user_id)
            self.assertEqual(enseignant.numero_compte_bancaire, '')
        for enseignant in enseignants:
            total = sum(
                float(a.volume_horaire)
                for a in affectations.filter(enseignant=enseignant))
            self.assertLessEqual(total, 192)

        # Seconde passe : aucun doublon.
        call_command('peupler_charges_pedagogiques_injs', sans_exemples=True)
        self.assertEqual(
            AffectationPedagogique.objects.filter(annee_academique=self.annee).count(),
            ECUE.objects.count())
        self.assertEqual(
            Formateur.objects.filter(numerobadge__startswith='ENS-DEMO-').count(),
            enseignants.count())
