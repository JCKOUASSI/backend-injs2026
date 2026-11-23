from datetime import date, time, timedelta

from django.test import TestCase

from formations.duree_prevue_resolve import (
    _ref_module_volume_hours,
    ensure_module_duree_prevue,
    module_edt_planned_hours,
    module_edt_raw_hours,
    module_edt_typical_hours,
    resolve_module_duree_prevue_heures,
)
from formations.models import Formation, Module, RefCategorie, RefFormation, RefModule, RefModuleVolumeHoraire, SessionModule


def _formation():
    return Formation.objects.create(formation='Cycle resolve')


def _module(formation, intitule='Module test', **kwargs):
    return Module.objects.create(formation=formation, intitule=intitule, **kwargs)


def _session(module, day_offset, debut, fin):
    return SessionModule.objects.create(
        module=module,
        date_journee=date(2026, 3, 1) + timedelta(days=day_offset),
        numero=1,
        heure_debut_prevue=debut,
        heure_fin_prevue=fin,
    )


class DureePrevueResolveTest(TestCase):
    def test_from_ref_module_linked(self):
        ref = RefModule.objects.create(intitule='Comptabilité', volume_horaire=30)
        module = _module(_formation(), intitule='Comptabilité', ref_module=ref, duree_prevue_heures=0)

        heures, source = resolve_module_duree_prevue_heures(module)
        self.assertEqual(heures, 30)
        self.assertEqual(source, 'ref_module')

    def test_from_ref_module_by_intitule(self):
        RefModule.objects.create(intitule='Gestion RH', volume_horaire=24)
        module = _module(_formation(), intitule='Gestion RH', duree_prevue_heures=None)

        heures, source = resolve_module_duree_prevue_heures(module)
        self.assertEqual(heures, 24)
        self.assertEqual(source, 'ref_module')

    def test_from_sessions_edt_when_no_ref(self):
        module = _module(_formation(), duree_prevue_heures=0)
        _session(module, 0, time(8, 0), time(18, 0))
        _session(module, 1, time(8, 0), time(20, 0))

        heures, source = resolve_module_duree_prevue_heures(module)
        self.assertEqual(heures, 22)
        self.assertEqual(source, 'sessions_edt')
        self.assertEqual(module_edt_planned_hours(module), 22)

    def test_ref_module_takes_priority_over_sessions(self):
        ref = RefModule.objects.create(intitule='Priorité ref', volume_horaire=30)
        module = _module(_formation(), intitule='Priorité ref', ref_module=ref, duree_prevue_heures=0)
        _session(module, 0, time(8, 0), time(18, 0))

        heures, source = resolve_module_duree_prevue_heures(module)
        self.assertEqual(heures, 30)
        self.assertEqual(source, 'ref_module')

    def test_ref_module_takes_priority_over_wrong_stored_duree(self):
        ref = RefModule.objects.create(intitule='Fiche erronée', volume_horaire=30)
        module = _module(
            _formation(), intitule='Fiche erronée', ref_module=ref, duree_prevue_heures=35,
        )

        heures, source = resolve_module_duree_prevue_heures(module)
        self.assertEqual(heures, 30)
        self.assertEqual(source, 'ref_module')

    def test_ref_module_volume_by_formation_and_categorie(self):
        """Volume = formation (cycle) × catégorie."""
        ref_formation = RefFormation.objects.create(intitule='FORMATION EN ADMINISTRATION DE BASE')
        cat_a = RefCategorie.objects.create(libelle='A')
        cat_b = RefCategorie.objects.create(libelle='B')
        ref = RefModule.objects.create(intitule='BUDGET FAMILIAL')
        ref.formations.add(ref_formation)
        RefModuleVolumeHoraire.objects.create(
            module=ref, formation=ref_formation, categorie=cat_a, volume_horaire=12,
        )
        RefModuleVolumeHoraire.objects.create(
            module=ref, formation=ref_formation, categorie=cat_b, volume_horaire=8,
        )
        formation = Formation.objects.create(formation='FORMATION EN ADMINISTRATION DE BASE')
        module = _module(formation, intitule='BUDGET FAMILIAL', ref_module=ref)

        self.assertEqual(_ref_module_volume_hours(module, 'A'), 12.0)
        self.assertEqual(_ref_module_volume_hours(module, 'B'), 8.0)

    def test_sigfae_et_teletravail_distinct_from_sigfae_ref(self):
        """SIGFAE ET TELETRAVAIL est un référentiel distinct de SIGFAE."""
        ref_formation = RefFormation.objects.create(intitule='FORMATION EN ADMINISTRATION DE BASE')
        cat_a = RefCategorie.objects.create(libelle='A')
        ref_sigfae = RefModule.objects.create(intitule='SIGFAE')
        ref_sigfae.formations.add(ref_formation)
        RefModuleVolumeHoraire.objects.create(
            module=ref_sigfae, formation=ref_formation, categorie=cat_a, volume_horaire=12,
        )
        ref_combo = RefModule.objects.create(intitule='SIGFAE ET TELETRAVAIL')
        ref_combo.formations.add(ref_formation)
        RefModuleVolumeHoraire.objects.create(
            module=ref_combo, formation=ref_formation, categorie=cat_a, volume_horaire=20,
        )
        formation = Formation.objects.create(formation='FORMATION EN ADMINISTRATION DE BASE')
        module_combo = _module(
            formation,
            intitule='SIGFAE ET TELETRAVAIL',
            ref_module=ref_combo,
            grade='A3',
            duree_prevue_heures=16,
        )
        module_sigfae = _module(formation, intitule='SIGFAE', ref_module=ref_sigfae, grade='A3')

        self.assertEqual(_ref_module_volume_hours(module_combo), 20.0)
        self.assertEqual(_ref_module_volume_hours(module_sigfae), 12.0)

    def test_ref_volume_fab_b_participant_maps_to_b(self):
        """FAB B (auditeurs) → catégorie B du référentiel, pas A."""
        ref_formation = RefFormation.objects.create(intitule='FORMATION EN ADMINISTRATION DE BASE')
        cat_a = RefCategorie.objects.create(libelle='A')
        cat_b = RefCategorie.objects.create(libelle='B')
        ref = RefModule.objects.create(intitule='SIGFAE')
        ref.formations.add(ref_formation)
        RefModuleVolumeHoraire.objects.create(
            module=ref, formation=ref_formation, categorie=cat_a, volume_horaire=20,
        )
        RefModuleVolumeHoraire.objects.create(
            module=ref, formation=ref_formation, categorie=cat_b, volume_horaire=16,
        )
        formation = Formation.objects.create(formation='FORMATION EN ADMINISTRATION DE BASE')
        module = _module(formation, intitule='SIGFAE', ref_module=ref, grade='B')

        self.assertEqual(_ref_module_volume_hours(module, 'FAB B'), 16.0)

    def test_ref_volume_inferred_from_grade_without_participants(self):
        """Sans auditeurs inscrits, la catégorie est déduite du grade (ex. B → 30 h réf.)."""
        ref_formation = RefFormation.objects.create(intitule='FORMATION EN ADMINISTRATION DE BASE')
        cat_a = RefCategorie.objects.create(libelle='A')
        cat_b = RefCategorie.objects.create(libelle='B')
        ref = RefModule.objects.create(intitule='DEONTOLOGIE')
        ref.formations.add(ref_formation)
        RefModuleVolumeHoraire.objects.create(
            module=ref, formation=ref_formation, categorie=cat_a, volume_horaire=30,
        )
        RefModuleVolumeHoraire.objects.create(
            module=ref, formation=ref_formation, categorie=cat_b, volume_horaire=30,
        )
        formation = Formation.objects.create(formation='FORMATION EN ADMINISTRATION DE BASE')
        module = _module(
            formation,
            intitule='DEONTOLOGIE',
            ref_module=ref,
            grade='B',
            duree_prevue_heures=32,
        )

        self.assertEqual(_ref_module_volume_hours(module), 30.0)
        heures, source = resolve_module_duree_prevue_heures(module)
        self.assertEqual(heures, 30)
        self.assertEqual(source, 'ref_module')

    def test_ensure_syncs_ref_over_wrong_stored_duree(self):
        ref = RefModule.objects.create(intitule='Sync ref', volume_horaire=30)
        module = _module(
            _formation(), intitule='Sync ref', ref_module=ref, duree_prevue_heures=35,
        )

        heures, source = ensure_module_duree_prevue(module)
        module.refresh_from_db()

        self.assertEqual(heures, 30)
        self.assertEqual(source, 'ref_module')
        self.assertEqual(float(module.duree_prevue_heures), 30)

    def test_ensure_persists_from_sessions_edt(self):
        module = _module(_formation(), duree_prevue_heures=0)
        _session(module, 0, time(8, 0), time(18, 0))
        _session(module, 1, time(8, 0), time(18, 0))
        _session(module, 2, time(8, 0), time(18, 0))

        heures, source = ensure_module_duree_prevue(module)
        module.refresh_from_db()

        self.assertEqual(heures, 30)
        self.assertEqual(source, 'sessions_edt')
        self.assertEqual(float(module.duree_prevue_heures), 30)

    def test_ensure_keeps_existing_value(self):
        module = _module(_formation(), duree_prevue_heures=28)
        _session(module, 0, time(8, 0), time(18, 0))

        heures, source = ensure_module_duree_prevue(module)
        module.refresh_from_db()

        self.assertEqual(heures, 28)
        self.assertIsNone(source)
        self.assertEqual(float(module.duree_prevue_heures), 28)

    def test_typical_hours_ignores_outlier_session(self):
        module = _module(_formation(), duree_prevue_heures=0)
        for day in range(5):
            _session(module, day, time(7, 30), time(12, 30))
        _session(module, 5, time(7, 30), time(13, 30))

        self.assertEqual(module_edt_raw_hours(module), 31)
        self.assertEqual(module_edt_typical_hours(module), 30)

    def test_ensure_corrects_raw_edt_mistake(self):
        module = _module(_formation(), duree_prevue_heures=31)
        for day in range(5):
            _session(module, day, time(7, 30), time(12, 30))
        _session(module, 5, time(13, 0), time(19, 0))

        heures, source = ensure_module_duree_prevue(module)
        module.refresh_from_db()

        self.assertEqual(heures, 30)
        self.assertEqual(source, 'sessions_edt')
        self.assertEqual(float(module.duree_prevue_heures), 30)
