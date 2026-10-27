"""Tests bilans — dimension matière (agrégation tous groupes)."""
from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from formations.models import Formation, Module, ModuleParticipant, Participant, RefModule, SessionModule
from statistiques.bilans import compute_bilans, compute_bilan_effectifs_matiere


class BilansMatiereTest(TestCase):
    def test_deontologie_aggregates_all_groups(self):
        formation = Formation.objects.create(formation='Formation en Administration de Base')
        ref = RefModule.objects.create(intitule='DEONTOLOGIE')
        jour = timezone.localdate()

        for g in ('GROUPE 9', 'GROUPE 10', 'GROUPE 11'):
            mod = Module.objects.create(
                formation=formation,
                ref_module=ref,
                intitule='DEONTOLOGIE',
                grade='A4',
                groupe=g,
            )
            for i in range(3):
                p = Participant.objects.create(
                    matricule=f'MAT-{g}-{i}',
                    nom=f'Auditeur{i}',
                    prenom='Test',
                    categorie='A',
                    sexe=Participant.Sexe.MASCULIN,
                )
                ModuleParticipant.objects.create(module=mod, participant=p)
            SessionModule.objects.create(
                module=mod,
                date_journee=jour,
                numero=1,
                intitule='Matin',
                heure_debut_prevue=time(8, 0),
                heure_fin_prevue=time(12, 0),
            )

        data = compute_bilans(
            annee=jour.year,
            formation_id=formation.id,
            dimension='matiere',
        )
        deonto = [b for b in data['bilans'] if b['libelle'].upper() == 'DEONTOLOGIE']
        self.assertEqual(len(deonto), 1)
        self.assertEqual(deonto[0]['nb_groupes'], 3)
        self.assertEqual(deonto[0]['inscrits'], 9)

        tableau = compute_bilan_effectifs_matiere(
            formation.id,
            ref_module_id=ref.id,
            annee=jour.year,
        )
        self.assertEqual(tableau['type'], 'effectifs_matiere')
        self.assertEqual(tableau['effectifs_auditeurs'], 9)
        self.assertEqual(tableau['nb_groupes'], 3)

    def test_matiere_absente_de_la_liste_sans_seance_comptabilisable(self):
        formation = Formation.objects.create(formation='FAB sans seance')
        ref = RefModule.objects.create(intitule='SANS COURS')
        future = timezone.localdate() + timedelta(days=365)
        mod = Module.objects.create(
            formation=formation, ref_module=ref, intitule='SANS COURS', grade='A4', groupe='G1',
        )
        p = Participant.objects.create(
            matricule='MAT-0', nom='Test', prenom='Auditeur', categorie='A',
        )
        ModuleParticipant.objects.create(module=mod, participant=p)
        SessionModule.objects.create(
            module=mod,
            date_journee=future,
            numero=1,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )

        data = compute_bilans(annee=timezone.localdate().year, formation_id=formation.id, dimension='matiere')
        self.assertEqual(data['bilans'], [])
        self.assertIsNone(compute_bilan_effectifs_matiere(formation.id, ref_module_id=ref.id))
