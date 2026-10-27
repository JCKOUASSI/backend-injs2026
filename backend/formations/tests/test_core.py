from datetime import timedelta, time as dt_time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from authentication.models import User
from ..models import (
    Formation, Module, Participant, Formateur,
    Secretariat, ModuleParticipant, ModuleFormateur, SessionModule,
    RefFormation, RefModule, RefCategorie, RefModuleVolumeHoraire,
    RefSite, RefBatiment, RefSalle,
)
from ..volume_horaire import compute_dashboard_volume_horaire


def make_user(username, role='INJS_ADMIN', **kwargs):
    u = User.objects.create_user(username=username, password='pass', role=role, **kwargs)
    return u


def make_formation(titre='Cycle test'):
    return Formation.objects.create(formation=titre)


def make_module(formation, intitule='Module test', statut='PLANIFIEE', **kwargs):
    return Module.objects.create(formation=formation, intitule=intitule, statut=statut, **kwargs)


def make_participant(matricule='M001', nom='Dupont', prenom='Jean'):
    return Participant.objects.create(matricule=matricule, nom=nom, prenom=prenom)


def make_formateur(numero='F001', nom='Martin', prenom='Paul'):
    return Formateur.objects.create(numerobadge=numero, nom=nom, prenom=prenom)


# ──────────────────────────────────────────
# Modèles
# ──────────────────────────────────────────

class FormationModelTest(TestCase):

    def test_creation(self):
        f = make_formation('Formation Alpha')
        self.assertEqual(str(f), 'Formation Alpha')
        self.assertIsNotNone(f.created_at)

    def test_modules_relation(self):
        f = make_formation()
        m1 = make_module(f, 'Mod A')
        m2 = make_module(f, 'Mod B')
        self.assertEqual(f.modules.count(), 2)

    def test_cascade_delete(self):
        f = make_formation()
        m = make_module(f)
        f.delete()
        self.assertEqual(Module.objects.filter(pk=m.pk).count(), 0)


class ModuleModelTest(TestCase):

    def setUp(self):
        self.f = make_formation()

    def test_str(self):
        m = make_module(self.f, 'Droit Admin')
        self.assertIn('Droit Admin', str(m))

    def test_statut_default(self):
        m = make_module(self.f)
        self.assertEqual(m.statut, 'PLANIFIEE')

    def test_statut_choices(self):
        for s in ('PLANIFIEE', 'EN_COURS', 'SUSPENDUE', 'TERMINEE'):
            m = make_module(self.f, intitule=f'Module {s}', statut=s)
            self.assertEqual(m.statut, s)

    def test_module_participant_unique(self):
        m = make_module(self.f)
        p = make_participant()
        ModuleParticipant.objects.create(module=m, participant=p)
        with self.assertRaises(Exception):
            ModuleParticipant.objects.create(module=m, participant=p)

    def test_module_formateur_unique(self):
        m = make_module(self.f)
        f = make_formateur()
        ModuleFormateur.objects.create(module=m, formateur=f)
        with self.assertRaises(Exception):
            ModuleFormateur.objects.create(module=m, formateur=f)


class SecretariatModelTest(TestCase):

    def test_auto_numero(self):
        s = Secretariat.objects.create(nom='Secrétariat A')
        self.assertTrue(s.numero.startswith('S'))

    def test_numero_unique(self):
        s1 = Secretariat.objects.create(nom='Sec 1')
        s2 = Secretariat.objects.create(nom='Sec 2')
        self.assertNotEqual(s1.numero, s2.numero)


class SecretariatListAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_sec', role='INJS_ADMIN')
        self.client.force_authenticate(user=self.admin)
        self.f = make_formation()
        self.sec_a = Secretariat.objects.create(nom='Sec A')
        self.sec_b = Secretariat.objects.create(nom='Sec B')
        p1 = make_participant(matricule='SA001', nom='Alpha', prenom='A')
        p2 = make_participant(matricule='SA002', nom='Beta', prenom='B')
        p1.secretariat = self.sec_a
        p1.save(update_fields=['secretariat'])
        p2.secretariat = self.sec_a
        p2.save(update_fields=['secretariat'])
        make_module(self.f, intitule='Mod A', secretariat=self.sec_a)
        make_module(self.f, intitule='Mod B', secretariat=self.sec_b)

    def test_list_returns_annotated_counts(self):
        res = self.client.get('/api/formations/secretariats/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data.get('results', res.data)
        by_id = {row['id']: row for row in data}
        self.assertEqual(by_id[self.sec_a.id]['nb_participants'], 2)
        self.assertEqual(by_id[self.sec_a.id]['nb_modules'], 1)
        self.assertEqual(by_id[self.sec_a.id]['nb_formations'], 1)
        self.assertEqual(by_id[self.sec_b.id]['nb_participants'], 0)
        self.assertEqual(by_id[self.sec_b.id]['nb_modules'], 1)

    def test_list_query_count_bounded(self):
        with self.assertNumQueries(3):
            self.client.get('/api/formations/secretariats/')


# ──────────────────────────────────────────
# API — authentification requise
# ──────────────────────────────────────────

class APIAuthTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.f = make_formation()
        self.m = make_module(self.f)

    def test_module_list_unauthenticated(self):
        res = self.client.get(f'/api/formations/{self.f.pk}/modules/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_module_full_unauthenticated(self):
        res = self.client.get(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/full/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_stats_unauthenticated(self):
        res = self.client.get('/api/formations/stats/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


# ──────────────────────────────────────────
# API — module CRUD
# ──────────────────────────────────────────

class ModuleAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_module', role='INJS_ADMIN')
        self.client.force_authenticate(self.admin)
        self.f = make_formation()
        self.m = make_module(self.f, intitule='Module API', statut='PLANIFIEE')

    def test_list_modules(self):
        res = self.client.get(f'/api/formations/{self.f.pk}/modules/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_create_module(self):
        res = self.client.post(f'/api/formations/{self.f.pk}/modules/', {
            'intitule': 'Nouveau module',
            'statut': 'PLANIFIEE',
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Module.objects.filter(intitule='Nouveau module').exists())

    def test_get_module_full(self):
        res = self.client.get(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/full/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertEqual(data['intitule'], 'Module API')
        self.assertIn('sessions', data)
        self.assertIn('participants', data)
        self.assertIn('formateurs', data)
        self.assertIn('presences', data)
        self.assertIn('duree_totale_heures', data)
        self.assertIn('duree_contractuelle_heures', data)
        self.assertIn('duree_planifiee_heures', data)

    def test_module_full_duree_totale_somme_seances(self):
        SessionModule.objects.create(
            module=self.m,
            numero=1,
            date_journee=timezone.localdate(),
            heure_debut_prevue=dt_time(8, 0),
            heure_fin_prevue=dt_time(12, 0),
        )
        SessionModule.objects.create(
            module=self.m,
            numero=2,
            date_journee=timezone.localdate() + timedelta(days=1),
            heure_debut_prevue=dt_time(14, 0),
            heure_fin_prevue=dt_time(18, 0),
        )
        self.m.duree_prevue_heures = 28
        self.m.save(update_fields=['duree_prevue_heures'])

        res = self.client.get(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/full/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res.data['duree_totale_heures']), 8.0)
        self.assertEqual(float(res.data['duree_prevue_heures']), 28)

    def test_patch_module(self):
        res = self.client.patch(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/', {
            'statut': 'EN_COURS',
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.m.refresh_from_db()
        self.assertEqual(self.m.statut, 'EN_COURS')

    def test_delete_module(self):
        res = self.client.delete(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Module.objects.filter(pk=self.m.pk).exists())

    def test_archive_module(self):
        res = self.client.post(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/archive/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.m.refresh_from_db()
        self.assertTrue(self.m.archived)
        self.assertIsNotNone(self.m.archived_at)

    def test_archived_module_hidden_from_operational_list(self):
        self.m.archived = True
        self.m.save(update_fields=['archived'])
        res = self.client.get('/api/formations/list/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        module_ids = [row['module_id'] for row in res.data['results']]
        self.assertNotIn(self.m.pk, module_ids)

    def test_archived_module_visible_in_archives_list(self):
        self.m.archived = True
        self.m.save(update_fields=['archived'])
        res = self.client.get('/api/formations/archives/modules/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        module_ids = [row['module_id'] for row in res.data['results']]
        self.assertIn(self.m.pk, module_ids)

    def test_archive_forbidden_for_encadrant(self):
        enc = make_user('enc_archive', role='ENCADRANT')
        self.client.force_authenticate(enc)
        res = self.client.post(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/archive/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unarchive_module(self):
        self.m.archived = True
        self.m.save(update_fields=['archived'])
        res = self.client.post(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/unarchive/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.m.refresh_from_db()
        self.assertFalse(self.m.archived)
        self.assertIsNone(self.m.archived_at)
        self.assertIsNone(self.m.archived_by)

    def test_unarchived_module_visible_in_operational_list(self):
        self.m.archived = True
        self.m.save(update_fields=['archived'])
        self.client.post(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/unarchive/')
        res = self.client.get('/api/formations/list/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        module_ids = [row['module_id'] for row in res.data['results']]
        self.assertIn(self.m.pk, module_ids)

    def test_unarchive_not_archived_returns_400(self):
        res = self.client.post(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/unarchive/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unarchive_forbidden_for_encadrant(self):
        self.m.archived = True
        self.m.save(update_fields=['archived'])
        enc = make_user('enc_unarchive', role='ENCADRANT')
        self.client.force_authenticate(enc)
        res = self.client.post(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/unarchive/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_module_not_found(self):
        res = self.client.get(f'/api/formations/{self.f.pk}/modules/99999/full/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ──────────────────────────────────────────
# API — add/remove participants
# ──────────────────────────────────────────

class ModuleParticipantAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_mp', role='INJS_ADMIN')
        self.client.force_authenticate(self.admin)
        self.f = make_formation()
        self.m = make_module(self.f)
        self.p = make_participant()

    def test_add_participant(self):
        res = self.client.post(
            f'/api/formations/{self.f.pk}/modules/{self.m.pk}/participants/add/',
            {'participant_id': self.p.pk},
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ModuleParticipant.objects.filter(module=self.m, participant=self.p).exists())

    def test_add_participant_already_enrolled(self):
        ModuleParticipant.objects.create(module=self.m, participant=self.p)
        res = self.client.post(
            f'/api/formations/{self.f.pk}/modules/{self.m.pk}/participants/add/',
            {'participant_id': self.p.pk},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_participant_missing_id(self):
        res = self.client.post(
            f'/api/formations/{self.f.pk}/modules/{self.m.pk}/participants/add/',
            {},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_participant(self):
        ModuleParticipant.objects.create(module=self.m, participant=self.p)
        res = self.client.delete(
            f'/api/formations/{self.f.pk}/modules/{self.m.pk}/participants/{self.p.pk}/remove/',
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ModuleParticipant.objects.filter(module=self.m, participant=self.p).exists())

    def test_remove_participant_not_found(self):
        res = self.client.delete(
            f'/api/formations/{self.f.pk}/modules/{self.m.pk}/participants/99999/remove/',
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ──────────────────────────────────────────
# API — add/remove formateurs
# ──────────────────────────────────────────

class ModuleFormateurAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_mf', role='INJS_ADMIN')
        self.client.force_authenticate(self.admin)
        self.f = make_formation()
        self.m = make_module(self.f)
        self.fmt = make_formateur()

    def test_add_formateur(self):
        res = self.client.post(
            f'/api/formations/{self.f.pk}/modules/{self.m.pk}/formateurs/add/',
            {'formateur_id': self.fmt.pk},
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ModuleFormateur.objects.filter(module=self.m, formateur=self.fmt).exists())

    def test_add_formateur_already_assigned(self):
        ModuleFormateur.objects.create(module=self.m, formateur=self.fmt)
        res = self.client.post(
            f'/api/formations/{self.f.pk}/modules/{self.m.pk}/formateurs/add/',
            {'formateur_id': self.fmt.pk},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_formateur(self):
        ModuleFormateur.objects.create(module=self.m, formateur=self.fmt)
        res = self.client.delete(
            f'/api/formations/{self.f.pk}/modules/{self.m.pk}/formateurs/{self.fmt.pk}/remove/',
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ModuleFormateur.objects.filter(module=self.m, formateur=self.fmt).exists())

    def test_remove_formateur_not_found(self):
        res = self.client.delete(
            f'/api/formations/{self.f.pk}/modules/{self.m.pk}/formateurs/99999/remove/',
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_formateur_blocks_two_groups_same_day(self):
        m_g1 = make_module(self.f, intitule='Cours G1', groupe='GROUPE 1')
        m_g2 = make_module(self.f, intitule='Cours G2', groupe='GROUPE 2')
        day = timezone.localdate()
        SessionModule.objects.create(module=m_g1, date_journee=day, numero=1, intitule='Matin')
        SessionModule.objects.create(module=m_g2, date_journee=day, numero=1, intitule='Matin')
        ModuleFormateur.objects.create(module=m_g1, formateur=self.fmt)

        res = self.client.post(
            f'/api/formations/{self.f.pk}/modules/{m_g2.pk}/formateurs/add/',
            {'formateur_id': self.fmt.pk},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('GROUPE 1', res.data['detail'])
        self.assertIn('GROUPE 2', res.data['detail'])
        self.assertIn('deux groupes différents', res.data['detail'])
        self.assertFalse(ModuleFormateur.objects.filter(module=m_g2, formateur=self.fmt).exists())

    def test_add_formateur_allows_same_group_same_day(self):
        m_g1 = make_module(self.f, intitule='Cours G1 A', groupe='GROUPE 1')
        m_g1b = make_module(self.f, intitule='Cours G1 B', groupe='GROUPE 1')
        day = timezone.localdate()
        SessionModule.objects.create(
            module=m_g1, date_journee=day, numero=1,
            heure_debut_prevue=dt_time(8, 0), heure_fin_prevue=dt_time(12, 0),
        )
        SessionModule.objects.create(
            module=m_g1b, date_journee=day, numero=1,
            heure_debut_prevue=dt_time(14, 0), heure_fin_prevue=dt_time(17, 0),
        )
        ModuleFormateur.objects.create(module=m_g1, formateur=self.fmt)

        res = self.client.post(
            f'/api/formations/{self.f.pk}/modules/{m_g1b.pk}/formateurs/add/',
            {'formateur_id': self.fmt.pk},
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_add_formateur_blocks_same_group_overlapping_hours(self):
        m_g1 = make_module(self.f, intitule='Cours G1 A', groupe='GROUPE 1')
        m_g1b = make_module(self.f, intitule='Cours G1 B', groupe='GROUPE 1')
        day = timezone.localdate()
        SessionModule.objects.create(
            module=m_g1, date_journee=day, numero=1, intitule='Matin',
            heure_debut_prevue=dt_time(8, 0), heure_fin_prevue=dt_time(12, 0),
        )
        SessionModule.objects.create(
            module=m_g1b, date_journee=day, numero=1, intitule='Fin matinée',
            heure_debut_prevue=dt_time(10, 0), heure_fin_prevue=dt_time(13, 0),
        )
        ModuleFormateur.objects.create(module=m_g1, formateur=self.fmt)

        res = self.client.post(
            f'/api/formations/{self.f.pk}/modules/{m_g1b.pk}/formateurs/add/',
            {'formateur_id': self.fmt.pk},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('conflit horaire', res.data['detail'])
        self.assertFalse(ModuleFormateur.objects.filter(module=m_g1b, formateur=self.fmt).exists())


# ──────────────────────────────────────────
# API — dashboard stats
# ──────────────────────────────────────────

class DashboardStatsAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_stats', role='INJS_ADMIN')
        self.client.force_authenticate(self.admin)
        f = make_formation()
        make_module(f, intitule='Module en cours 1', statut='EN_COURS', groupe='GROUPE 1')
        make_module(f, intitule='Module en cours 2', statut='EN_COURS', groupe='GROUPE 2')
        make_module(f, intitule='Module planifié', statut='PLANIFIEE')
        make_module(f, intitule='Module terminé', statut='TERMINEE')

    def test_stats_keys(self):
        res = self.client.get('/api/formations/stats/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for key in ('total_modules', 'modules_en_cours', 'modules_termines',
                    'modules_planifies', 'groupes_en_cours',
                    'total_participants', 'total_formateurs'):
            self.assertIn(key, res.data)

    def test_stats_counts(self):
        res = self.client.get('/api/formations/stats/')
        self.assertEqual(res.data['total_modules'], 4)
        self.assertEqual(res.data['modules_en_cours'], 2)
        self.assertEqual(res.data['modules_planifies'], 1)
        self.assertEqual(res.data['modules_termines'], 1)
        self.assertEqual(res.data['groupes_en_cours'], 2)

    def test_stats_periode_mois(self):
        res = self.client.get('/api/formations/stats/?preset=mois&mois=2026-06')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('periode', res.data)
        self.assertEqual(res.data['periode']['preset'], 'mois')
        self.assertEqual(res.data['periode']['mois'], '2026-06')


# ──────────────────────────────────────────
# API — referentiels
# ──────────────────────────────────────────

class ReferentielsAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        u = make_user('admin_ref', role='INJS_ADMIN')
        self.client.force_authenticate(u)

    def test_referentiels(self):
        res = self.client.get('/api/formations/referentiels/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for key in ('formations', 'modules', 'sites', 'batiments', 'salles', 'grades', 'groupes', 'grades_modules'):
            self.assertIn(key, res.data)

    def test_referentiels_gestion(self):
        res = self.client.get('/api/formations/referentiels/gestion/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for key in (
            'formations', 'modules', 'categories', 'grades', 'vagues',
            'sites', 'batiments', 'salles', 'types_secretariat',
        ):
            self.assertIn(key, res.data)
            self.assertIsInstance(res.data[key], list)


class RefModuleFormationsAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        u = make_user('admin_ref_module', role='INJS_ADMIN')
        self.client.force_authenticate(u)
        # Préfixe [TEST] : repérable si du code est lancé hors manage.py test (shell, serveur dev).
        self.f1 = RefFormation.objects.create(intitule='[TEST] CYCLE A', actif=True)
        self.f2 = RefFormation.objects.create(intitule='[TEST] CYCLE B', actif=True)
        self.cat = RefCategorie.objects.create(libelle='A', actif=True)

    def _sample_volumes(self, *formation_ids):
        return [
            {'formation_id': fid, 'categorie_id': self.cat.id, 'volume_horaire': 8}
            for fid in formation_ids
        ]

    def test_create_ref_module_requires_formations(self):
        res = self.client.post('/api/formations/ref/modules/', {
            'intitule': 'Déontologie',
            'formation_ids': [],
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_ref_module_with_multiple_formations(self):
        res = self.client.post('/api/formations/ref/modules/', {
            'intitule': 'Déontologie',
            'formation_ids': [self.f1.id, self.f2.id],
            'volumes_horaires': self._sample_volumes(self.f1.id, self.f2.id),
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(res.data['formation_ids']), {self.f1.id, self.f2.id})

    def test_update_ref_module_formations(self):
        mod = RefModule.objects.create(intitule='COMPTABILITÉ', actif=True)
        mod.formations.add(self.f1)
        RefModuleVolumeHoraire.objects.create(
            module=mod, formation=self.f1, categorie=self.cat, volume_horaire=8,
        )
        res = self.client.put(f'/api/formations/ref/modules/{mod.id}/', {
            'intitule': 'COMPTABILITÉ',
            'formation_ids': [self.f1.id, self.f2.id],
            'volumes_horaires': self._sample_volumes(self.f1.id, self.f2.id),
            'actif': True,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(set(res.data['formation_ids']), {self.f1.id, self.f2.id})

    def test_create_ref_module_same_intitule_merges_formations(self):
        first = self.client.post('/api/formations/ref/modules/', {
            'intitule': 'Anatomie fonctionnelle',
            'formation_ids': [self.f1.id],
            'volumes_horaires': self._sample_volumes(self.f1.id),
        }, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        module_id = first.data['id']

        second = self.client.post('/api/formations/ref/modules/', {
            'intitule': 'ANATOMIE FONCTIONNELLE',
            'formation_ids': [self.f2.id],
            'volumes_horaires': self._sample_volumes(self.f2.id),
        }, format='json')
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data['id'], module_id)
        self.assertEqual(set(second.data['formation_ids']), {self.f1.id, self.f2.id})
        self.assertEqual(RefModule.objects.filter(intitule__iexact='ANATOMIE FONCTIONNELLE').count(), 1)
        volumes = RefModuleVolumeHoraire.objects.filter(module_id=module_id)
        self.assertEqual(volumes.count(), 2)


class RefSalleAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        u = make_user('admin_ref_salle', role='INJS_ADMIN')
        self.client.force_authenticate(u)
        self.site = RefSite.objects.create(nom='[TEST] INJS MARCORY', actif=True)
        self.other_site = RefSite.objects.create(nom='[TEST] AUTRE SITE', actif=True)
        self.batiment = RefBatiment.objects.create(nom='[TEST] Bâtiment A', site=self.site, actif=True)

    def test_create_salle_without_batiment(self):
        res = self.client.post('/api/formations/ref/salles/', {
            'nom': 'SALLE DE CONFÉRENCE',
            'site_id': self.site.id,
            'batiment_id': None,
            'actif': True,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertIsNone(res.data['batiment_id'])
        self.assertEqual(res.data['nom'], 'SALLE DE CONFÉRENCE')
        self.assertEqual(res.data['type_lieu'], 'SALLE')

    def test_create_salle_empty_batiment_id(self):
        res = self.client.post('/api/formations/ref/salles/', {
            'nom': 'SALLE A',
            'site_id': str(self.site.id),
            'batiment_id': '',
            'actif': True,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertIsNone(res.data['batiment_id'])

    def test_create_salle_duplicate_without_batiment(self):
        RefSalle.objects.create(nom='SALLE DE CONFÉRENCE', site=self.site, batiment=None)
        res = self.client.post('/api/formations/ref/salles/', {
            'nom': 'SALLE DE CONFÉRENCE',
            'site_id': self.site.id,
            'batiment_id': '',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('existe déjà', res.data['detail'])

    def test_create_salle_rejects_batiment_from_other_site(self):
        res = self.client.post('/api/formations/ref/salles/', {
            'nom': 'SALLE B',
            'site_id': self.other_site.id,
            'batiment_id': self.batiment.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


# ──────────────────────────────────────────
# API — dispatch secrétariat par matricule
# ──────────────────────────────────────────

class ParticipantSecretariatDispatchByMatriculeAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_dispatch_matricule', role='INJS_ADMIN')
        self.client.force_authenticate(self.admin)
        self.sec_fab = Secretariat.objects.create(nom='FAB')
        self.sec_fac = Secretariat.objects.create(nom='FAC')

    def test_create_participant_fnce_sets_fab_secretariat(self):
        res = self.client.post('/api/formations/participants/', {
            'matricule': 'FNCE26-001',
            'nom': 'KOUAME',
            'prenom': 'Jean',
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        participant = Participant.objects.get(matricule='FNCE26-001')
        self.assertEqual(participant.secretariat_id, self.sec_fab.id)

    def test_create_participant_fncp_sets_fac_secretariat(self):
        res = self.client.post('/api/formations/participants/', {
            'matricule': 'FNCP26-001',
            'nom': 'DIALLO',
            'prenom': 'Mariam',
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        participant = Participant.objects.get(matricule='FNCP26-001')
        self.assertEqual(participant.secretariat_id, self.sec_fac.id)

    def test_update_participant_matricule_fncp_reassigns_to_fac(self):
        participant = Participant.objects.create(
            matricule='M0001',
            nom='TRAORE',
            prenom='Fatou',
            secretariat=self.sec_fab,
        )
        res = self.client.patch(f'/api/formations/participants/{participant.pk}/', {
            'matricule': 'FNCP26-777',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        participant.refresh_from_db()
        self.assertEqual(participant.secretariat_id, self.sec_fac.id)


class DashboardVolumeHoraireTest(TestCase):

    def test_prevu_et_realise_par_seances(self):
        f = make_formation()
        module = make_module(f, duree_prevue_heures=10)
        now = timezone.now()
        for num in range(1, 3):
            SessionModule.objects.create(
                module=module,
                date_journee=timezone.localdate(),
                numero=num,
                demarree_le=now - timedelta(hours=5),
                terminee_le=now,
                heure_debut_prevue=dt_time(8, 0),
                heure_fin_prevue=dt_time(13, 0),
            )
        effectue, total, taux = compute_dashboard_volume_horaire(
            Module.objects.filter(pk=module.pk)
        )
        self.assertEqual(total, 10)
        self.assertEqual(effectue, 10)
        self.assertEqual(taux, 100)

    def test_realise_plafonne_au_prevu_seance(self):
        """Une séance laissée ouverte ne compte pas plus que son créneau planifié."""
        from ..volume_horaire import _accumulate_module_session_volumes

        f = make_formation()
        module = make_module(f, duree_prevue_heures=4)
        SessionModule.objects.create(
            module=module,
            date_journee=timezone.localdate(),
            numero=1,
            demarree_le=timezone.now() - timedelta(days=5),
            terminee_le=timezone.now(),
            heure_debut_prevue=dt_time(8, 0),
            heure_fin_prevue=dt_time(12, 0),
        )
        vol = _accumulate_module_session_volumes(module)
        self.assertEqual(vol['prevu_h'], 4.0)
        self.assertEqual(vol['realise_h'], 4.0)
        self.assertEqual(vol['ecart_h'], 0.0)

