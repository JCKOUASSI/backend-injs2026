"""Tests point journalier — format CPFAE (modèle FAC)."""
from datetime import date, time

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from types import SimpleNamespace

from formations.models import Formation, Module, ModuleParticipant, Participant, SessionModule
from statistiques.point_journalier import (
    _titre_ligne1,
    _organisme_label,
    _aggregate_total,
    compute_point_journalier,
)


class PointJournalierFormatUnitTest(SimpleTestCase):
    def test_titre_ligne1_fac_cat_a(self):
        formation = SimpleNamespace(formation='Formation en Accompagnement de Carrières (FAC)')
        titre = _titre_ligne1(formation, 'A')
        self.assertIn("FORMATION D'ACCOMPAGNEMENT DE CARRIER CAT A", titre)
        self.assertIn('POINT DES PRÉSENCES_CPFAE', titre)

    def test_titre_ligne1_fab(self):
        formation = SimpleNamespace(formation='Formation en Administration de Base')
        self.assertEqual(
            _titre_ligne1(formation),
            'FORMATION EN ADMINISTRATION DE BASE_POINT DES PRÉSENCES_CPFAE',
        )

    def test_organisme_label_includes_grade(self):
        self.assertEqual(_organisme_label('A', 'A3'), 'CATÉGORIE A_GRADE A3')

    def test_aggregate_total_matches_excel_formula(self):
        """Colonne N du modèle Excel = somme effectifs / somme présents."""
        groupes = [
            {'effectif': 55, 'presents': 53, 'absents': 2},
            {'effectif': 55, 'presents': 55, 'absents': 0},
            {'effectif': 53, 'presents': 52, 'absents': 1},
        ]
        total = _aggregate_total(groupes)
        self.assertEqual(total['effectif'], 163)
        self.assertEqual(total['presents'], 160)
        self.assertEqual(total['absents'], 3)
        self.assertAlmostEqual(total['taux_presence'], 160 / 163, places=4)
        self.assertAlmostEqual(total['taux_absence'], 3 / 163, places=4)


class PointJournalierPlannedSessionsTest(TestCase):
    """Séances planifiées (import EDT) sans démarrage badge → fiche visible."""

    def test_planned_session_without_demarree_le_appears_in_index(self):
        formation = Formation.objects.create(formation='Formation en Administration de Base')
        module = Module.objects.create(
            formation=formation,
            intitule='Module PJ test',
            grade='A3',
            groupe='GROUPE 1',
        )
        participant = Participant.objects.create(
            matricule='PJ-001',
            nom='Test',
            prenom='Auditeur',
            categorie='A',
        )
        ModuleParticipant.objects.create(module=module, participant=participant)

        jour = timezone.localdate()
        SessionModule.objects.create(
            module=module,
            date_journee=jour,
            numero=1,
            intitule='Matin',
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )
        SessionModule.objects.create(
            module=module,
            date_journee=jour,
            numero=2,
            intitule='Soir',
            heure_debut_prevue=time(13, 0),
            heure_fin_prevue=time(17, 0),
        )

        data = compute_point_journalier(annee=jour.year, mois=jour.month, index_only=True)
        self.assertGreaterEqual(data['total_tableaux'], 1)
        ids = {t['id'] for t in data['tableaux']}
        self.assertTrue(any('A' in tid and jour.isoformat() in tid for tid in ids))

        detail = compute_point_journalier(
            annee=jour.year,
            mois=jour.month,
            categorie='A',
            formation_id=formation.id,
            index_only=False,
        )
        self.assertEqual(len(detail['tableaux']), 1)
        tb = detail['tableaux'][0]
        self.assertIn('matin', tb)
        self.assertIn('soir', tb)
        self.assertEqual(tb['matin']['total']['effectif'], 1)
        self.assertEqual(tb['matin']['total']['presents'], 0)

    def test_same_groupe_multiple_modules_one_column(self):
        """Un groupe physique = une colonne, même si plusieurs matières (modules)."""
        formation = Formation.objects.create(formation='Formation en Administration de Base')
        participant = Participant.objects.create(
            matricule='PJ-002',
            nom='Dupont',
            prenom='Marie',
            categorie='A',
        )
        jour = timezone.localdate()
        modules = []
        for intitule in ('DEONTOLOGIE', 'REDACTION ADMINISTRATIVE', 'CULTURE CIVIQUE'):
            mod = Module.objects.create(
                formation=formation,
                intitule=intitule,
                grade='A4',
                groupe='GROUPE 10',
                salle='DISTRICT DES LACS',
            )
            ModuleParticipant.objects.create(module=mod, participant=participant)
            SessionModule.objects.create(
                module=mod,
                date_journee=jour,
                numero=1,
                intitule='Matin',
                heure_debut_prevue=time(8, 0),
                heure_fin_prevue=time(12, 0),
            )
            modules.append(mod)

        detail = compute_point_journalier(
            annee=jour.year,
            mois=jour.month,
            categorie='A',
            formation_id=formation.id,
            jour=jour.isoformat(),
            index_only=False,
        )
        tb = detail['tableaux'][0]
        matin_groupes = tb['matin']['groupes']
        self.assertEqual(len(matin_groupes), 1)
        self.assertEqual(matin_groupes[0]['label'], 'G10')
        self.assertEqual(matin_groupes[0]['effectif'], 1)
        self.assertEqual(len(matin_groupes[0]['module_ids']), 3)

    def test_seuls_groupes_avec_cours_le_jour(self):
        """Un groupe sans séance le jour J n'apparaît pas dans le point journalier."""
        formation = Formation.objects.create(formation='Formation en Administration de Base')
        jour = timezone.localdate()
        participant = Participant.objects.create(
            matricule='PJ-003', nom='Test', prenom='Groupe', categorie='A',
        )

        mod_cours = Module.objects.create(
            formation=formation, intitule='DEONTOLOGIE', grade='A4',
            groupe='GROUPE 10', salle='SALLE A',
        )
        mod_sans = Module.objects.create(
            formation=formation, intitule='CULTURE CIVIQUE', grade='A4',
            groupe='GROUPE 11', salle='SALLE B',
        )
        for mod in (mod_cours, mod_sans):
            ModuleParticipant.objects.create(module=mod, participant=participant)
        SessionModule.objects.create(
            module=mod_cours,
            date_journee=jour,
            numero=1,
            intitule='Matin',
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )

        detail = compute_point_journalier(
            annee=jour.year,
            mois=jour.month,
            categorie='A',
            formation_id=formation.id,
            jour=jour.isoformat(),
            index_only=False,
        )
        tb = detail['tableaux'][0]
        labels = [g['label'] for g in tb['matin']['groupes']]
        self.assertIn('G10', labels)
        self.assertNotIn('G11', labels)
        self.assertEqual(len(tb['matin']['groupes']), 1)

    def test_groupe_matin_uniquement_absent_du_bloc_soir(self):
        """Groupe avec séance MATIN seulement : colonne MATIN oui, SOIR non."""
        formation = Formation.objects.create(formation='FAB test creneau')
        jour = timezone.localdate()
        participant = Participant.objects.create(
            matricule='PJ-004', nom='Matin', prenom='Seul', categorie='A',
        )
        mod = Module.objects.create(
            formation=formation, intitule='MODULE TEST', grade='A3',
            groupe='GROUPE 9',
        )
        ModuleParticipant.objects.create(module=mod, participant=participant)
        SessionModule.objects.create(
            module=mod,
            date_journee=jour,
            numero=1,
            intitule='Matin',
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )

        detail = compute_point_journalier(
            annee=jour.year,
            categorie='A',
            formation_id=formation.id,
            jour=jour.isoformat(),
            index_only=False,
        )
        tb = detail['tableaux'][0]
        self.assertEqual(len(tb['matin']['groupes']), 1)
        self.assertEqual(len(tb['soir']['groupes']), 0)
