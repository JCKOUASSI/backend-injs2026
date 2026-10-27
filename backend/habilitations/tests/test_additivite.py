"""U1 — Garantie d'additivité : l'ancien dispositif d'authentification est intact.

Aucun signal, aucune permission DRF, aucune route n'est branché depuis
l'application ``habilitations`` en U1. Un compte existant sans profil CURP
se comporte donc exactement comme avant. Ces tests sont des gardes anti-dérive
pour les unités suivantes.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from habilitations.models import CompteUtilisateur

User = get_user_model()
MOT_DE_PASSE = 'Addit#2026x'
URL_CONNEXION = '/api/auth/login/'


class AdditiviteAuthentificationTests(APITestCase):
    def test_la_creation_d_un_user_ne_cree_pas_de_profil(self):
        user = User.objects.create_user(
            username='add-user', password=MOT_DE_PASSE, role='ADMIN')
        self.assertEqual(CompteUtilisateur.objects.filter(user=user).count(), 0)

    def test_login_web_admin_sans_profil_reste_autorise(self):
        User.objects.create_user(
            username='add-admin', password=MOT_DE_PASSE, role='ADMIN')
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'add-admin', 'password': MOT_DE_PASSE}, format='json')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.content)

    def test_login_web_auditeur_sans_profil_reste_refuse(self):
        User.objects.create_user(
            username='add-aud', password=MOT_DE_PASSE, role='AUDITEUR')
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'add-aud', 'password': MOT_DE_PASSE}, format='json')
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('mobile', reponse.json()['detail'].lower())

    def test_login_mobile_auditeur_sans_profil_reste_autorise(self):
        User.objects.create_user(
            username='add-aud-mob', password=MOT_DE_PASSE, role='AUDITEUR')
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'add-aud-mob', 'password': MOT_DE_PASSE,
             'device_id': 'add-device-001'}, format='json')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.content)

    def test_les_permissions_existantes_ne_sont_pas_modifiees(self):
        from authentication.role_groups import ensure_role_groups
        ensure_role_groups()
        finance = User.objects.create_user(
            username='add-fin', password=MOT_DE_PASSE, role='FINANCE')
        # Droit constant caractérisé en U0 : FINANCE n'a pas mutate_users.
        self.assertFalse(finance.has_perm('authentication.mutate_users'))
        self.assertTrue(finance.has_perm('authentication.finance_module'))

    def test_aucun_profil_n_existe_pour_les_comptes_herites(self):
        for role in ('ADMIN', 'SECRETARIAT', 'FORMATEUR', 'AUDITEUR'):
            User.objects.create_user(
                username=f'add-{role.lower()}', password=MOT_DE_PASSE, role=role)
        self.assertEqual(CompteUtilisateur.objects.count(), 0)
