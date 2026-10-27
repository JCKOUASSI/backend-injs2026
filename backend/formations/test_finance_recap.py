from datetime import timedelta, time as dt_time

from django.test import TestCase
from django.utils import timezone

from .models import Formation, Module, Formateur, ModuleFormateur, RefFormation, RefModule, SessionModule
from .api_views import (
    _finance_recap_par_module,
    _finance_group_sessions_by_groupe,
    _finance_report_rows,
)


def _make_formation(titre='Cycle test'):
    return Formation.objects.create(formation=titre)


def _make_module(formation, intitule='Module test', **kwargs):
    return Module.objects.create(
        formation=formation, intitule=intitule, statut='PLANIFIEE', **kwargs,
    )


def _make_formateur():
    return Formateur.objects.create(numerobadge='F100', nom='Dupont', prenom='Jean')


class FinanceRecapModulesTest(TestCase):

    def test_recap_par_module_sorted_by_grade_groupe(self):
        modules = [
            {'module_id': 2, 'module_intitule': 'B', 'grade': 'A4', 'groupe': 'G2',
             'sessions_count': 1, 'total_duree_minutes': 60, 'total_duree_realisee_minutes': 30,
             'taux_realisation_pct': 50, 'montant_realise': 1000},
            {'module_id': 1, 'module_intitule': 'A', 'grade': 'A4', 'groupe': 'G1',
             'sessions_count': 2, 'total_duree_minutes': 120, 'total_duree_realisee_minutes': 90,
             'taux_realisation_pct': 75, 'montant_realise': 2000},
        ]
        recap = _finance_recap_par_module(modules)
        self.assertEqual([r['module_intitule'] for r in recap], ['A', 'B'])

    def test_group_sessions_by_groupe_with_subtotals(self):
        sessions = [
            {'session_id': 1, 'grade': 'A4', 'groupe': 'G1', 'date_journee': '2026-01-02',
             'numero': 2, 'duree_minutes': 120, 'duree_realisee_minutes': 100, 'montant_realise': 5000},
            {'session_id': 2, 'grade': 'A4', 'groupe': 'G1', 'date_journee': '2026-01-01',
             'numero': 1, 'duree_minutes': 60, 'duree_realisee_minutes': 60, 'montant_realise': 3000},
            {'session_id': 3, 'grade': 'A3', 'groupe': 'G2', 'date_journee': '2026-01-03',
             'numero': 1, 'duree_minutes': 90, 'duree_realisee_minutes': 45, 'montant_realise': 2000},
        ]
        groups = _finance_group_sessions_by_groupe(sessions)
        self.assertEqual(len(groups), 2)
        g1 = next(g for g in groups if g['groupe'] == 'G1')
        self.assertEqual(g1['sous_total']['sessions_count'], 2)
        self.assertEqual(g1['sous_total']['creneau_minutes'], 180.0)
        self.assertEqual(g1['sous_total']['realise_minutes'], 160.0)
        self.assertEqual(g1['sessions'][0]['numero'], 1)

    def test_report_rows_includes_recap_and_groups(self):
        f = _make_formation()
        module = _make_module(
            f, intitule='Déontologie', grade='A4', groupe='GROUPE 4', duree_prevue_heures=4,
        )
        formateur = _make_formateur()
        ModuleFormateur.objects.create(module=module, formateur=formateur)
        now = timezone.now()
        SessionModule.objects.create(
            module=module,
            date_journee=timezone.localdate(),
            numero=1,
            demarree_le=now - timedelta(hours=2),
            terminee_le=now,
            heure_debut_prevue=dt_time(8, 0),
            heure_fin_prevue=dt_time(10, 0),
        )
        rows = _finance_report_rows([formateur], include_sessions=True)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(len(row['recap_modules']), 1)
        self.assertEqual(row['recap_modules'][0]['module_intitule'], 'Déontologie')
        self.assertEqual(row['modules_dispenses'], 'Déontologie')
        self.assertEqual(len(row['sessions_by_groupe']), 1)
        self.assertEqual(row['sessions_by_groupe'][0]['groupe'], 'GROUPE 4')
        self.assertEqual(row['sessions_by_groupe'][0]['sous_total']['sessions_count'], 1)

    def test_recap_modules_includes_montant_prevu(self):
        f = _make_formation('Cycle A')
        RefFormation.objects.create(intitule='Cycle A', prix_heure_realisee=7500, actif=True)
        module = _make_module(
            f, intitule='Rédaction', grade='A4', groupe='GROUPE 15', duree_prevue_heures=2,
        )
        formateur = _make_formateur()
        ModuleFormateur.objects.create(module=module, formateur=formateur)
        SessionModule.objects.create(
            module=module,
            date_journee=timezone.localdate(),
            numero=1,
            heure_debut_prevue=dt_time(8, 0),
            heure_fin_prevue=dt_time(10, 0),
        )
        rows = _finance_report_rows([formateur], include_sessions=True)
        recap = rows[0]['recap_modules'][0]
        self.assertEqual(recap['montant_prevu'], 15000.0)
        self.assertEqual(recap['montant_realise'], 0.0)

    def test_export_summary_preserves_recap_modules(self):
        """L'export fiche formateur ne doit pas écraser la ligne rapport finance."""
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory
        from exports.views import _finance_formateur_summary_rows, _finance_paie_recap_modules

        f = _make_formation()
        module = _make_module(
            f, intitule='Déontologie', grade='A4', groupe='GROUPE 4', duree_prevue_heures=4,
        )
        formateur = _make_formateur()
        ModuleFormateur.objects.create(module=module, formateur=formateur)
        now = timezone.now()
        SessionModule.objects.create(
            module=module,
            date_journee=timezone.localdate(),
            numero=1,
            demarree_le=now - timedelta(hours=2),
            terminee_le=now,
            heure_debut_prevue=dt_time(8, 0),
            heure_fin_prevue=dt_time(10, 0),
        )
        drf_req = Request(APIRequestFactory().get('/x/', {'preset': 'tout'}))
        summary = _finance_formateur_summary_rows(formateur, drf_req)
        self.assertEqual(len(summary['recap_modules']), 1)
        self.assertEqual(summary['recap_modules'][0]['module_intitule'], 'Déontologie')
        self.assertGreater(summary['total_planned'], 0)
        self.assertEqual(len(summary['rows']), 1)
        paie_recap = _finance_paie_recap_modules(summary['recap_modules'])
        self.assertEqual(len(paie_recap), 1)
        self.assertEqual(paie_recap[0]['sessions_count'], 1)

    def test_paie_recap_excludes_modules_without_sessions_in_period(self):
        from exports.views import _finance_paie_recap_modules

        f = _make_formation()
        dans_periode = _make_module(
            f, intitule='Dans période', grade='A4', groupe='G1', duree_prevue_heures=4,
        )
        hors_periode = _make_module(
            f, intitule='Hors période', grade='A4', groupe='G2', duree_prevue_heures=8,
        )
        formateur = _make_formateur()
        ModuleFormateur.objects.create(module=dans_periode, formateur=formateur)
        ModuleFormateur.objects.create(module=hors_periode, formateur=formateur)
        today = timezone.localdate()
        SessionModule.objects.create(
            module=dans_periode,
            date_journee=today,
            numero=1,
            heure_debut_prevue=dt_time(8, 0),
            heure_fin_prevue=dt_time(10, 0),
        )
        SessionModule.objects.create(
            module=hors_periode,
            date_journee=today + timedelta(days=60),
            numero=1,
            heure_debut_prevue=dt_time(8, 0),
            heure_fin_prevue=dt_time(12, 0),
        )
        rows = _finance_report_rows(
            [formateur],
            include_sessions=True,
            date_debut=today,
            date_fin=today,
        )
        recap = rows[0]['recap_modules']
        self.assertEqual(len(recap), 1)
        self.assertEqual(recap[0]['module_intitule'], 'Dans période')
        paie_recap = _finance_paie_recap_modules(recap)
        self.assertEqual(len(paie_recap), 1)
        self.assertEqual(paie_recap[0]['module_intitule'], 'Dans période')
        self.assertEqual(paie_recap[0]['total_creneau_periode_minutes'], 120.0)
        self.assertEqual(paie_recap[0]['total_duree_realisee_minutes'], 0.0)

    def test_paie_recap_three_groups_only_active_in_period(self):
        """DEONTOLOGIE sur 3 groupes : seuls ceux avec séance dans la période apparaissent."""
        from exports.views import _finance_formateur_export_context
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        f = _make_formation()
        ref = RefModule.objects.create(intitule='DEONTOLOGIE', volume_horaire=30)
        formateur = _make_formateur()
        today = timezone.localdate()
        for groupe, in_period in (('GROUPE 1', True), ('GROUPE 22', False), ('GROUPE 6', True)):
            mod = _make_module(
                f,
                intitule='DEONTOLOGIE',
                ref_module=ref,
                grade='A3',
                groupe=groupe,
                duree_prevue_heures=30,
            )
            ModuleFormateur.objects.create(module=mod, formateur=formateur)
            SessionModule.objects.create(
                module=mod,
                date_journee=today if in_period else today + timedelta(days=90),
                numero=1,
                heure_debut_prevue=dt_time(8, 0),
                heure_fin_prevue=dt_time(18, 0),
            )
        drf_req = Request(APIRequestFactory().get('/x/', {
            'preset': 'custom',
            'date_debut': today.isoformat(),
            'date_fin': today.isoformat(),
        }))
        ctx = _finance_formateur_export_context(formateur, drf_req)
        groupes = [m.get('groupe') for m in ctx['recap_modules']]
        self.assertEqual(len(ctx['recap_modules']), 2)
        self.assertIn('GROUPE 1', groupes)
        self.assertIn('GROUPE 6', groupes)
        self.assertNotIn('GROUPE 22', groupes)

    def test_paie_export_uses_period_creneau_not_full_contractual(self):
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory
        from exports.views import _finance_formateur_export_context

        f = _make_formation()
        ref = RefModule.objects.create(intitule='Long module', volume_horaire=30)
        module = _make_module(
            f,
            intitule='Long module',
            ref_module=ref,
            grade='A4',
            groupe='G1',
            duree_prevue_heures=30,
        )
        formateur = _make_formateur()
        ModuleFormateur.objects.create(module=module, formateur=formateur)
        today = timezone.localdate()
        SessionModule.objects.create(
            module=module,
            date_journee=today,
            numero=1,
            heure_debut_prevue=dt_time(8, 0),
            heure_fin_prevue=dt_time(13, 0),
        )
        drf_req = Request(APIRequestFactory().get('/x/', {
            'preset': 'custom',
            'date_debut': today.isoformat(),
            'date_fin': today.isoformat(),
        }))
        ctx = _finance_formateur_export_context(formateur, drf_req)
        self.assertEqual(len(ctx['recap_modules']), 1)
        item = ctx['recap_modules'][0]
        self.assertEqual(item['total_creneau_periode_minutes'], 300.0)
        self.assertEqual(item['total_duree_minutes'], 1800.0)

    def test_export_contacts_from_settings(self):
        from exports.views import _finance_paie_contacts, _finance_paie_parse_lines, _FINANCE_PAIE_CONTACTS
        from .models import FinanceSettings

        custom = _finance_paie_parse_lines(
            'Ligne intro\nContact A tel 0102030405',
            _FINANCE_PAIE_CONTACTS,
        )
        self.assertEqual(custom, ['Ligne intro', 'Contact A tel 0102030405'])
        self.assertEqual(
            _finance_paie_contacts({'contacts': custom}),
            custom,
        )
        settings = FinanceSettings.get_solo()
        settings.export_contacts = 'Service Finance\ntel 0700000000'
        settings.save(update_fields=['export_contacts'])
        parsed = _finance_paie_parse_lines(settings.export_contacts, _FINANCE_PAIE_CONTACTS)
        self.assertEqual(parsed, ['Service Finance', 'tel 0700000000'])

    def test_export_pied_page_from_settings(self):
        from exports.views import (
            _finance_paie_pied_de_page,
            _FINANCE_PAIE_PIED_ADRESSE,
        )

        titre, texte = _finance_paie_pied_de_page({})
        self.assertEqual(titre, 'DOCUMENT CONFIDENTIEL')
        self.assertEqual(texte, _FINANCE_PAIE_PIED_ADRESSE)

        titre, texte = _finance_paie_pied_de_page({
            'pied_page_titre': 'DOCUMENT INTERNE',
            'pied_page_texte': 'CPFAE Bouaké — Tel 20 21 34 08',
        })
        self.assertEqual(titre, 'DOCUMENT INTERNE')
        self.assertEqual(texte, 'CPFAE Bouaké — Tel 20 21 34 08')
