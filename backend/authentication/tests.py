from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from django.contrib.auth.models import Group
from rest_framework.test import APIClient
from .role_groups import ROLE_GROUP_NAMES, ensure_role_groups

User = get_user_model()

URL = '/api/auth/me/change-password/'
ME_URL = '/api/auth/me/'
USERS_URL = '/api/auth/users/'


def make_user(username='testuser', password='oldpass123', role='SECRETARIAT'):
    u = User.objects.create_user(username=username, password=password)
    u.role = role
    u.save()
    return u


class ChangePasswordTests(TestCase):

    def setUp(self):
        self.password = 'oldpass123'
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    # ── happy path ──────────────────────────────────────────────────────────

    def test_change_password_success(self):
        """Valid old + new password → 200 + detail message."""
        resp = self.client.post(URL, {
            'old_password': 'oldpass123',
            'new_password': 'newpass456',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('detail', resp.data)

        # token invalide après changement du mdp ? Non — on vérifie juste que le hash a changé
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpass456'))
        self.assertFalse(self.user.check_password('oldpass123'))

    # ── mauvais ancien mot de passe ─────────────────────────────────────────

    def test_wrong_old_password(self):
        """Incorrect old_password → 400 with field error."""
        resp = self.client.post(URL, {
            'old_password': 'wrongpass!',
            'new_password': 'newpass456',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('old_password', resp.data)

    # ── nouveau = ancien ────────────────────────────────────────────────────

    def test_new_same_as_old(self):
        """new_password identical to old_password → 400."""
        resp = self.client.post(URL, {
            'old_password': 'oldpass123',
            'new_password': 'oldpass123',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('new_password', resp.data)

    # ── mot de passe trop court ─────────────────────────────────────────────

    def test_new_password_too_short(self):
        """new_password shorter than 8 chars → 400."""
        resp = self.client.post(URL, {
            'old_password': 'oldpass123',
            'new_password': 'abc',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('new_password', resp.data)

    # ── champs manquants ────────────────────────────────────────────────────

    def test_missing_old_password(self):
        """Missing old_password → 400."""
        resp = self.client.post(URL, {'new_password': 'newpass456'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('old_password', resp.data)

    def test_missing_new_password(self):
        """Missing new_password → 400."""
        resp = self.client.post(URL, {'old_password': 'oldpass123'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('new_password', resp.data)

    # ── non authentifié ─────────────────────────────────────────────────────

    def test_unauthenticated(self):
        """No token → 401."""
        anon = APIClient()
        resp = anon.post(URL, {
            'old_password': 'oldpass123',
            'new_password': 'newpass456',
        }, format='json')
        self.assertEqual(resp.status_code, 401)

    # ── tous rôles peuvent changer leur mdp ─────────────────────────────────

    def test_auditeur_can_change_password(self):
        """AUDITEUR role can also change password."""
        u = make_user(username='auditeur1', password='oldpass123', role='AUDITEUR')
        c = APIClient()
        c.force_authenticate(user=u)
        resp = c.post(URL, {
            'old_password': 'oldpass123',
            'new_password': 'newpass789',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        u.refresh_from_db()
        self.assertTrue(u.check_password('newpass789'))


class MeProfilePatchTests(TestCase):
    """PATCH /api/auth/me/ — mise à jour du profil par l'utilisateur connecté."""

    def setUp(self):
        self.user = make_user(username='profil_user', password='pass12345', role='SECRETARIAT')
        self.user.first_name = 'Jean'
        self.user.last_name = 'Test'
        self.user.email = 'jean@test.example'
        self.user.telephone = '0102030405'
        self.user.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_patch_profile_updates_fields(self):
        resp = self.client.patch(ME_URL, {
            'first_name': 'Jeanne',
            'last_name': 'Durand',
            'email': 'jeanne@example.com',
            'telephone': '0605040302',
            'organisation': 'CPFAE',
            'grade': 'A3',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['first_name'], 'Jeanne')
        self.assertEqual(resp.data['last_name'], 'Durand')
        self.assertEqual(resp.data['email'], 'jeanne@example.com')
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Jeanne')
        self.assertEqual(self.user.organisation, 'CPFAE')

    def test_patch_matricule_unique_conflict(self):
        other = make_user(username='other_mat', password='pass12345', role='ENCADRANT')
        other.matricule = 'MAT-UNIQUE-1'
        other.save()
        resp = self.client.patch(ME_URL, {'matricule': 'MAT-UNIQUE-1'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('matricule', resp.data)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class WelcomeEmailTests(TestCase):
    """Tests pour l'envoi d'email de bienvenue lors de la création d'un utilisateur."""

    def setUp(self):
        self.admin = make_user(username='email_admin', password='adminpass', role='CHEF_INJS_ADMIN')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    # ── email envoyé si adresse renseignée ──────────────────────────────────

    def test_welcome_email_sent_when_email_provided(self):
        """Créer un utilisateur avec email → 1 email envoyé."""
        resp = self.client.post(USERS_URL, {
            'username': 'newuser1',
            'password': 'pass1234!',
            'email': 'newuser1@example.com',
            'first_name': 'Jean',
            'last_name': 'Dupont',
            'role': 'SECRETARIAT',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn('newuser1@example.com', sent.to)
        self.assertIn('newuser1', sent.body)
        self.assertIn('pass1234!', sent.body)

    def test_welcome_email_contains_credentials(self):
        """Le corps de l'email contient bien le username et le mot de passe en clair."""
        self.client.post(USERS_URL, {
            'username': 'usertest',
            'password': 'monSecret9',
            'email': 'usertest@example.com',
            'role': 'ENCADRANT',
        }, format='json')
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn('usertest', body)
        self.assertIn('monSecret9', body)

    # ── pas d'email si adresse absente ──────────────────────────────────────

    def test_no_email_sent_when_no_email(self):
        """Créer un utilisateur sans email → aucun email envoyé."""
        resp = self.client.post(USERS_URL, {
            'username': 'noemail',
            'password': 'pass1234!',
            'role': 'ENCADRANT',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)

    # ── plusieurs créations → autant d'emails ───────────────────────────────

    def test_each_user_gets_own_email(self):
        """Deux utilisateurs avec email → deux emails distincts."""
        for i in range(2):
            self.client.post(USERS_URL, {
                'username': f'user{i}',
                'password': 'pass1234!',
                'email': f'user{i}@example.com',
                'role': 'ENCADRANT',
            }, format='json')
        self.assertEqual(len(mail.outbox), 2)
        recipients = [m.to[0] for m in mail.outbox]
        self.assertIn('user0@example.com', recipients)
        self.assertIn('user1@example.com', recipients)


class EncadrantSecretariatTests(TestCase):

    def test_encadrant_secretariat_cleared_on_create(self):
        from formations.models import Secretariat
        from authentication.serializers import UserCreateSerializer
        from rest_framework.test import APIRequestFactory

        sec = Secretariat.objects.create(nom='Sec Enc Create')
        admin = make_user('enc-admin', role='CHEF_INJS_ADMIN')
        request = APIRequestFactory().post('/api/auth/users/')
        request.user = admin
        serializer = UserCreateSerializer(
            data={
                'username': 'enc_no_sec',
                'password': 'pass1234!',
                'email': 'enc_no_sec@example.com',
                'role': 'ENCADRANT',
                'secretariat': sec.id,
            },
            context={'request': request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertIsNone(user.secretariat_id)


class RoleGroupsTest(TestCase):

    def setUp(self):
        ensure_role_groups()

    def test_creates_one_group_per_role(self):
        for group_name in ROLE_GROUP_NAMES.values():
            self.assertTrue(
                Group.objects.filter(name=group_name).exists(),
                f"Groupe manquant: {group_name}",
            )

    def test_assign_group_on_user_create(self):
        user = make_user(username='group-user-create', role=User.Role.SECRETARIAT)
        self.assertTrue(user.groups.filter(name=ROLE_GROUP_NAMES[User.Role.SECRETARIAT]).exists())

    def test_move_group_on_role_change(self):
        user = make_user('group-user-update', role=User.Role.AUDITEUR)
        old_group = ROLE_GROUP_NAMES[User.Role.AUDITEUR]
        new_group = ROLE_GROUP_NAMES[User.Role.ENCADRANT]

        self.assertTrue(user.groups.filter(name=old_group).exists())

        user.role = User.Role.ENCADRANT
        user.save()

        self.assertTrue(user.groups.filter(name=old_group).exists())
        self.assertTrue(user.groups.filter(name=new_group).exists())

    def test_multiple_role_groups(self):
        from authentication.role_groups import get_user_role, get_user_roles, user_in_roles

        user = make_user('multi-role-user', role=User.Role.SECRETARIAT)
        secretariat_group = Group.objects.get(name=ROLE_GROUP_NAMES[User.Role.SECRETARIAT])
        encadrant_group = Group.objects.get(name=ROLE_GROUP_NAMES[User.Role.ENCADRANT])
        user.groups.set([secretariat_group, encadrant_group])
        user.refresh_from_db()

        self.assertEqual(
            get_user_roles(user),
            frozenset({User.Role.SECRETARIAT, User.Role.ENCADRANT}),
        )
        self.assertEqual(get_user_role(user), User.Role.SECRETARIAT)
        self.assertTrue(user_in_roles(user, {User.Role.AUDITEUR, User.Role.ENCADRANT}))

    def test_validate_role_combination_allowed_pair(self):
        from authentication.role_groups import validate_role_combination

        validate_role_combination({User.Role.SECRETARIAT, User.Role.ENCADRANT})

    def test_validate_role_combination_rejects_mobile_mix(self):
        from django.core.exceptions import ValidationError
        from authentication.role_groups import validate_role_combination

        with self.assertRaises(ValidationError):
            validate_role_combination({User.Role.AUDITEUR, User.Role.SECRETARIAT})

    def test_validate_role_combination_rejects_unlisted_pair(self):
        from django.core.exceptions import ValidationError
        from authentication.role_groups import validate_role_combination

        with self.assertRaises(ValidationError):
            validate_role_combination({User.Role.ADMIN, User.Role.SECRETARIAT})

    def test_dual_access_roles_get_staff_status(self):
        from authentication.role_groups import DUAL_ACCESS_ROLES, MOBILE_ONLY_ROLES

        for role in DUAL_ACCESS_ROLES:
            user = make_user(f'staff-{role.lower()}', role=role)
            user.refresh_from_db()
            self.assertTrue(user.is_staff, f'is_staff attendu pour {role}')

        for role in MOBILE_ONLY_ROLES:
            user = make_user(f'mobile-{role.lower()}', role=role)
            user.refresh_from_db()
            self.assertFalse(user.is_staff, f'is_staff interdit pour {role}')

        encadrant = make_user('staff-encadrant', role=User.Role.ENCADRANT)
        encadrant.refresh_from_db()
        self.assertFalse(encadrant.is_staff)

    def test_staff_status_kept_while_admin_group_present(self):
        user = make_user('staff-role-change', role=User.Role.ADMIN)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

        user.role = User.Role.SECRETARIAT
        user.save()
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_staff_status_removed_when_admin_group_replaced(self):
        user = make_user('staff-role-change-2', role=User.Role.ADMIN)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

        secretariat_group = Group.objects.get(name=ROLE_GROUP_NAMES[User.Role.SECRETARIAT])
        user.groups.set([secretariat_group])
        user.refresh_from_db()
        self.assertFalse(user.is_staff)

    def test_create_superuser_assigns_admin_role(self):
        user = User.objects.create_superuser(
            username='superadmin',
            email='super@example.com',
            password='superpass123',
        )
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.groups.filter(name=ROLE_GROUP_NAMES[User.Role.ADMIN]).exists())

    def test_sync_role_from_group_when_admin_changes_group(self):
        user = make_user('group-sync-user', role=User.Role.AUDITEUR)
        encadrant_group = Group.objects.get(name=ROLE_GROUP_NAMES[User.Role.ENCADRANT])
        user.groups.set([encadrant_group])
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.ENCADRANT)

    def test_custom_permissions_assigned_to_secretariat_group(self):
        group = Group.objects.get(name=ROLE_GROUP_NAMES[User.Role.SECRETARIAT])
        codenames = set(group.permissions.values_list('codename', flat=True))
        self.assertIn('mutate_users', codenames)
        self.assertIn('access_web', codenames)
        self.assertIn('operational_web', codenames)

    def test_get_user_role_from_groups(self):
        from authentication.role_groups import get_user_role

        user = make_user('role-from-group', role=User.Role.FINANCE)
        self.assertEqual(get_user_role(user), User.Role.FINANCE)
        user.role = User.Role.ADMIN  # champ désynchronisé volontairement
        self.assertEqual(get_user_role(user), User.Role.FINANCE)


class AuditeurProfileSyncTests(TestCase):

    def test_auditeur_user_creates_participant_profile(self):
        user = User.objects.create_user(
            username='FNCE26-999',
            password='pass12345',
            first_name='Marie',
            last_name='Martin',
            email='marie@example.com',
            role=User.Role.AUDITEUR,
        )
        participant = user.participant_profile
        self.assertEqual(participant.matricule, 'FNCE26-999')
        self.assertEqual(participant.prenom, 'Marie')
        self.assertEqual(participant.nom, 'Martin')
        self.assertEqual(participant.email, 'marie@example.com')

    def test_auditeur_user_links_existing_participant_by_matricule(self):
        from formations.models import Participant

        participant = Participant.objects.create(
            matricule='FNCE26-100',
            nom='Durand',
            prenom='Paul',
            email='paul@example.com',
        )
        user = User.objects.create_user(
            username='auditeur_link',
            password='pass12345',
            matricule='FNCE26-100',
            first_name='Paul',
            last_name='Durand',
            role=User.Role.AUDITEUR,
        )
        participant.refresh_from_db()
        self.assertEqual(participant.user_id, user.id)
        self.assertEqual(user.participant_profile.pk, participant.pk)

    def test_resync_does_not_unlink_participant_on_matricule_format_drift(self):
        """Une dérive de format (matricule vidé / username sans séparateur) ne doit
        plus délier la fiche ni créer de doublon vide — sinon le badgeage échoue."""
        from formations.models import Participant
        from authentication.profile_sync import sync_user_profile_links

        participant = Participant.objects.create(
            matricule='OPH-1', nom='Nom', prenom='Prenom',
        )
        user = User.objects.create_user(
            username='OPH-1', password='pass12345', role=User.Role.AUDITEUR,
        )
        participant.refresh_from_db()
        self.assertEqual(participant.user_id, user.id)

        # Dérive : matricule vidé, username réécrit dans un autre format.
        User.objects.filter(pk=user.pk).update(matricule='', username='OPH1')
        user.refresh_from_db()

        sync_user_profile_links(user)

        participant.refresh_from_db()
        self.assertEqual(participant.user_id, user.id, 'La fiche liée ne doit pas être déliée.')
        self.assertEqual(Participant.objects.count(), 1, 'Aucune fiche fantôme ne doit être créée.')
        user.refresh_from_db()
        self.assertEqual(user.matricule, 'OPH-1', 'Le matricule du compte doit être réaligné sur la fiche.')

    def test_repair_command_relinks_account_to_enrolled_fiche(self):
        """La commande repair_auditeur_fiches doit rebrancher le compte sur la fiche
        inscrite et supprimer le doublon vide, en migrant les pointages."""
        from io import StringIO
        from django.core.management import call_command
        from django.utils import timezone
        from formations.models import (
            Formation, Module, ModuleParticipant, Participant, SessionModule,
        )
        from presences.models import Pointage

        formation = Formation.objects.create(formation='F repair')
        module = Module.objects.create(formation=formation, intitule='M repair', statut='EN_COURS')
        seance = SessionModule.objects.create(
            module=module, date_journee=timezone.localdate(), numero=1,
        )

        # Fiche réellement inscrite (matricule avec tiret).
        enrolled = Participant.objects.create(matricule='OPH-1', nom='Vrai', prenom='Fiche')
        ModuleParticipant.objects.create(module=module, participant=enrolled)

        # Compte au format compact : la synchro crée un doublon vide « OPH1 ».
        user = User.objects.create_user(
            username='OPH1', password='pass12345', role=User.Role.AUDITEUR,
        )
        phantom = Participant.objects.get(user=user)
        self.assertNotEqual(phantom.pk, enrolled.pk)
        self.assertEqual(phantom.modules_inscrits.count(), 0)

        # Pointage historique enregistré (avant correctif) sur le doublon vide.
        Pointage.objects.create(
            participant=phantom, session=seance,
            date_journee=timezone.localdate(), timestamp_entree=timezone.now(),
        )

        call_command('repair_auditeur_fiches', '--apply', stdout=StringIO())

        enrolled.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(enrolled.user_id, user.id, 'Le compte doit être rebranché sur la fiche inscrite.')
        self.assertEqual(user.matricule, 'OPH-1', 'Le matricule du compte doit être réaligné.')
        self.assertFalse(
            Participant.objects.filter(pk=phantom.pk).exists(),
            'Le doublon vide doit être supprimé.',
        )
        self.assertTrue(
            Pointage.objects.filter(participant=enrolled, session=seance).exists(),
            'Le pointage doit avoir été migré vers la fiche inscrite.',
        )

    def test_admin_user_does_not_create_participant_profile(self):
        from formations.models import Participant

        user = User.objects.create_superuser(
            username='admin_no_profile',
            email='admin@example.com',
            password='superpass123',
        )
        self.assertFalse(Participant.objects.filter(user=user).exists())

    def test_my_fiche_creates_missing_auditeur_profile(self):
        from formations.models import Participant
        from rest_framework.test import APIClient

        user = User.objects.create_user(
            username='FNCE26-888',
            password='pass12345',
            first_name='Luc',
            last_name='Bernard',
            role=User.Role.AUDITEUR,
        )
        Participant.objects.filter(user=user).delete()

        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get('/api/me/fiche/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Participant.objects.filter(user=user).exists())

    def test_formateur_user_creates_formateur_profile(self):
        from formations.models import Formateur

        user = User.objects.create_user(
            username='F1234',
            password='pass12345',
            first_name='Anne',
            last_name='Leroy',
            matricule='F1234',
            role=User.Role.FORMATEUR,
        )
        formateur = user.formateur_profile
        self.assertEqual(formateur.numerobadge, 'F1234')
        self.assertEqual(formateur.prenom, 'Anne')
        self.assertEqual(formateur.nom, 'Leroy')

    def test_my_fiche_creates_missing_formateur_profile(self):
        from formations.models import Formateur
        from rest_framework.test import APIClient

        user = User.objects.create_user(
            username='F5678',
            password='pass12345',
            first_name='Paul',
            last_name='Martin',
            matricule='F5678',
            role=User.Role.FORMATEUR,
        )
        Formateur.objects.filter(user=user).delete()

        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get('/api/me/fiche/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Formateur.objects.filter(user=user).exists())
        self.assertEqual(resp.data['profil']['type_personne'], 'formateur')

    def test_encadrant_user_gets_matricule_for_fiche(self):
        from rest_framework.test import APIClient

        user = User.objects.create_user(
            username='ENC-001',
            password='pass12345',
            first_name='Sophie',
            last_name='Moreau',
            role=User.Role.ENCADRANT,
        )
        User.objects.filter(pk=user.pk).update(matricule='')
        user.refresh_from_db()
        self.assertEqual(user.matricule, '')

        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get('/api/me/fiche/')
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.matricule, 'ENC-001')
        self.assertEqual(resp.data['profil']['type_personne'], 'encadrant')

    def test_my_fiche_secretariat_encadrant_dual_role(self):
        ensure_role_groups()
        user = User.objects.create_user(
            username='ENC-DUAL',
            password='pass12345',
            first_name='Jean',
            last_name='Dupont',
            role=User.Role.SECRETARIAT,
            matricule='ENC-DUAL',
        )
        user.groups.set([
            Group.objects.get(name=ROLE_GROUP_NAMES[User.Role.SECRETARIAT]),
            Group.objects.get(name=ROLE_GROUP_NAMES[User.Role.ENCADRANT]),
        ])
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.SECRETARIAT)

        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get('/api/me/fiche/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['profil']['type_personne'], 'encadrant')

    def test_my_fiche_superviseur_role(self):
        user = User.objects.create_user(
            username='SUP-FICHE',
            password='pass12345',
            first_name='Marc',
            last_name='Super',
            role=User.Role.SUPERVISEUR,
            matricule='SUP-FICHE',
        )
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get('/api/me/fiche/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['profil']['type_personne'], 'encadrant')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class BadgeAccountProvisionTests(TestCase):

    def setUp(self):
        from formations.models import Participant, Formateur

        self.participant = Participant.objects.create(
            matricule='FNCP26-100',
            nom='Kouassi',
            prenom='Aya',
            email='aya.kouassi@example.com',
        )
        self.formateur = Formateur.objects.create(
            numerobadge='F0100',
            nom='Traore',
            prenom='Ibrahim',
            email='ibrahim.traore@example.com',
        )

    def test_auditeur_account_created_with_email_on_import_provision(self):
        from authentication.badge_accounts import provision_auditeur_accounts

        stats = provision_auditeur_accounts([self.participant.pk])
        self.participant.refresh_from_db()

        self.assertEqual(stats['created'], 1)
        self.assertEqual(stats['emails_sent'], 1)
        self.assertIsNotNone(self.participant.user_id)
        self.assertEqual(self.participant.user.role, User.Role.AUDITEUR)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('FNCP26-100', mail.outbox[0].body)
        self.assertIn('application mobile', mail.outbox[0].body.lower())

    def test_formateur_account_created_with_email_on_import_provision(self):
        from authentication.badge_accounts import provision_formateur_accounts

        stats = provision_formateur_accounts([self.formateur.pk])
        self.formateur.refresh_from_db()

        self.assertEqual(stats['created'], 1)
        self.assertEqual(stats['emails_sent'], 1)
        self.assertIsNotNone(self.formateur.user_id)
        self.assertEqual(self.formateur.user.role, User.Role.FORMATEUR)
        self.assertEqual(len(mail.outbox), 1)

    def test_no_email_when_address_missing(self):
        from authentication.badge_accounts import provision_auditeur_accounts

        self.participant.email = ''
        self.participant.save(update_fields=['email'])

        stats = provision_auditeur_accounts([self.participant.pk])
        self.assertEqual(stats['created'], 1)
        self.assertEqual(stats['emails_sent'], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_auditeur_account_links_existing_user_without_duplicate(self):
        from formations.models import Participant
        from authentication.badge_accounts import provision_auditeur_accounts

        existing = User.objects.create_user(
            username='FNCP26-100',
            password='pass12345',
            first_name='Ancien',
            last_name='Nom',
            role=User.Role.AUDITEUR,
            matricule='FNCP26-100',
        )
        # Compte orphelin : user existe mais la fiche importée garde les données Excel.
        Participant.objects.filter(pk=self.participant.pk).update(
            user_id=None,
            prenom='Aya',
            nom='Kouassi',
        )
        self.participant.refresh_from_db()

        stats = provision_auditeur_accounts([self.participant.pk])
        self.participant.refresh_from_db()
        existing.refresh_from_db()

        self.assertEqual(stats['errors'], 0)
        self.assertEqual(stats['updated'], 1)
        self.assertEqual(self.participant.user_id, existing.id)
        self.assertEqual(existing.first_name, 'Aya')
        self.assertEqual(existing.last_name, 'Kouassi')

    def test_auditeur_reimport_does_not_reset_password(self):
        from authentication.badge_accounts import ensure_auditeur_account

        self.participant.user = None
        self.participant.save(update_fields=['user'])
        ensure_auditeur_account(self.participant, send_email=False)
        self.participant.refresh_from_db()
        old_hash = self.participant.user.password

        ensure_auditeur_account(self.participant, send_email=False, reset_password=False)
        self.participant.user.refresh_from_db()
        self.assertEqual(self.participant.user.password, old_hash)

    def test_welcome_email_contains_logo(self):
        from authentication.emails import send_welcome_email

        user = make_user('logo-user', role=User.Role.SECRETARIAT)
        user.email = 'logo-user@example.com'
        user.save(update_fields=['email'])

        send_welcome_email(user, 'pass1234!')
        self.assertEqual(len(mail.outbox), 1)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn('data:image', html)
        self.assertIn('INJS Abidjan', html)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class BadgeProvisionMissingTests(TestCase):

    def setUp(self):
        from formations.models import (
            Formation, Formateur, Module, ModuleFormateur, ModuleParticipant, Participant,
        )

        formation = Formation.objects.create(formation='F provision')
        module = Module.objects.create(formation=formation, intitule='M provision', statut='EN_COURS')

        self.participant = Participant.objects.create(
            matricule='FNCP26-200',
            nom='Diallo',
            prenom='Mariam',
            email='mariam@example.com',
        )
        self.formateur = Formateur.objects.create(
            numerobadge='F0200',
            nom='Koné',
            prenom='Paul',
            email='paul@example.com',
        )
        ModuleParticipant.objects.create(module=module, participant=self.participant)
        ModuleFormateur.objects.create(module=module, formateur=self.formateur)

        self.participant_sans_module = Participant.objects.create(
            matricule='FNCP26-999',
            nom='Seul',
            prenom='Sans',
        )

    def test_participants_sans_compte_excludes_linked_and_unenrolled(self):
        from formations.models import Participant
        from authentication.badge_provision import participants_sans_compte, formateurs_sans_compte

        qs = participants_sans_compte()
        self.assertEqual(list(qs.values_list('matricule', flat=True)), ['FNCP26-200'])
        self.assertNotIn('FNCP26-999', list(qs.values_list('matricule', flat=True)))

        linked = User.objects.create_user(
            username='linked-auditeur',
            password='pass12345',
            role=User.Role.AUDITEUR,
            matricule='FNCP26-200',
        )
        Participant.objects.filter(user=linked).exclude(pk=self.participant.pk).delete()
        self.participant.user = linked
        self.participant.save(update_fields=['user'])
        self.assertEqual(participants_sans_compte().count(), 0)
        self.assertEqual(formateurs_sans_compte().count(), 1)

    def test_provision_missing_creates_only_unlinked_accounts(self):
        from authentication.badge_provision import (
            participants_sans_compte,
            provision_missing_badge_accounts,
        )

        stats = provision_missing_badge_accounts()
        self.participant.refresh_from_db()
        self.formateur.refresh_from_db()

        self.assertEqual(stats['auditeurs']['created'], 1)
        self.assertEqual(stats['formateurs']['created'], 1)
        self.assertIsNotNone(self.participant.user_id)
        self.assertIsNotNone(self.formateur.user_id)
        self.assertEqual(len(mail.outbox), 2)

        stats_again = provision_missing_badge_accounts()
        self.assertEqual(stats_again['auditeurs']['created'], 0)
        self.assertEqual(stats_again['formateurs']['created'], 0)
        self.assertEqual(participants_sans_compte().count(), 0)


class UserListScopeTests(TestCase):

    def setUp(self):
        from formations.models import Secretariat
        self.client = APIClient()
        self.sec_a = Secretariat.objects.create(nom='Sec List A')
        self.sec_b = Secretariat.objects.create(nom='Sec List B')
        self.secretariat_user = make_user('sec-list', role='SECRETARIAT')
        self.secretariat_user.secretariat = self.sec_a
        self.secretariat_user.save(update_fields=['secretariat'])
        self.encadrant = make_user('enc-global', role='ENCADRANT')
        self.client.force_authenticate(user=self.secretariat_user)

    def test_secretariat_lists_all_encadrants_for_assignment(self):
        res = self.client.get('/api/auth/users/?role=ENCADRANT')
        self.assertEqual(res.status_code, 200)
        data = res.data.get('results', res.data)
        usernames = {u['username'] for u in data}
        self.assertIn('enc-global', usernames)

    def test_secretariat_still_scopes_other_roles_to_own_secretariat(self):
        aud_a = make_user('aud-a', role='AUDITEUR')
        aud_a.secretariat = self.sec_a
        aud_a.save(update_fields=['secretariat'])
        aud_b = make_user('aud-b', role='AUDITEUR')
        aud_b.secretariat = self.sec_b
        aud_b.save(update_fields=['secretariat'])
        res = self.client.get('/api/auth/users/?role=AUDITEUR')
        self.assertEqual(res.status_code, 200)
        data = res.data.get('results', res.data)
        usernames = {u['username'] for u in data}
        self.assertIn('aud-a', usernames)
        self.assertNotIn('aud-b', usernames)


class LoginAccessTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.auditeur = make_user('auditeur-login', password='pass12345', role=User.Role.AUDITEUR)
        self.formateur = make_user('formateur-login', password='pass12345', role=User.Role.FORMATEUR)
        self.admin = make_user('admin-login', password='admin123', role=User.Role.ADMIN)

    def test_auditeur_web_login_forbidden(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'auditeur-login',
            'password': 'pass12345',
        })
        self.assertEqual(resp.status_code, 403)
        self.assertIn('mobile', resp.data['detail'].lower())

    def test_auditeur_mobile_login_allowed(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'auditeur-login',
            'password': 'pass12345',
            'device_id': 'test-device-001',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)

    def test_formateur_web_login_forbidden(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'formateur-login',
            'password': 'pass12345',
        })
        self.assertEqual(resp.status_code, 403)
        self.assertIn('mobile', resp.data['detail'].lower())

    def test_formateur_mobile_login_allowed(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'formateur-login',
            'password': 'pass12345',
            'device_id': 'test-device-formateur',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)

    def test_admin_login_success(self):
        """Admin peut se connecter via l'endpoint JWT — retourne 200 avec access token."""
        resp = self.client.post('/api/auth/login/', {
            'username': 'admin-login',
            'password': 'admin123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)
        self.assertTrue(resp.data['refresh_in_cookie'])
        self.assertEqual(resp.data['user']['role'], 'ADMIN')

    def test_login_does_not_enforce_csrf(self):
        """Le login endpoint ne doit pas exiger de jeton CSRF.

        Verifie que le csrf_exempt de @api_view + @authentication_classes([])
        empêche toute vérification CSRF (middleware ou SessionAuthentication).
        """
        client = APIClient(enforce_csrf_checks=True)
        resp = client.post('/api/auth/login/', {
            'username': 'admin-login',
            'password': 'admin123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)


class RoleContextTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        ensure_role_groups()
        self.direction = make_user('direction-ctx', role=User.Role.DIRECTION)
        self.secretariat_user = make_user('secretariat-ctx', role=User.Role.SECRETARIAT)

    def test_me_includes_role_context(self):
        self.client.force_authenticate(user=self.direction)
        resp = self.client.get(ME_URL)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.data['role_context']
        self.assertFalse(ctx['can_mutate_users'])
        self.assertEqual(ctx['labels']['DIRECTION'], 'Direction')

    def test_roles_endpoint_matches_me_context(self):
        self.client.force_authenticate(user=self.secretariat_user)
        me_ctx = self.client.get(ME_URL).data['role_context']
        roles_ctx = self.client.get('/api/auth/roles/').data
        self.assertEqual(me_ctx['creatable_roles'], roles_ctx['creatable_roles'])
        self.assertTrue(roles_ctx['can_mutate_users'])

    def test_direction_staff_filter_roles_for_read_only_users_page(self):
        self.client.force_authenticate(user=self.direction)
        ctx = self.client.get('/api/auth/roles/').data
        self.assertFalse(ctx['can_mutate_users'])
        self.assertTrue(len(ctx['staff_filter_roles']) > 0)

