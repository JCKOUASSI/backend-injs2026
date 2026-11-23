from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from parametres.models import Parametre, ParametreHistorique


def make_user(username, role='ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


class ParametresAPIAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.param = Parametre.objects.create(
            cle='test_param',
            libelle='Test Paramètre',
            categorie='general',
            type='text',
            valeur='valeur_initial',
            valeur_defaut='valeur_initial',
            modifiable=True,
            modifiable_par_roles='["ADMIN"]',
            lecturable_par_roles='["ADMIN", "DIRECTION"]',
            actif=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.url = f'/api/parametres/{self.param.pk}/'
        self.list_url = '/api/parametres/'

    def test_unauthenticated_denied(self):
        res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_list(self):
        admin = make_user('admin_param', role='ADMIN')
        self.client.force_authenticate(admin)
        res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_direction_can_view_but_not_edit(self):
        direction = make_user('dir_param', role='DIRECTION')
        self.client.force_authenticate(direction)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.patch(self.url, {'valeur': 'nouvelle'})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_secretariat_sees_empty_list(self):
        sec = make_user('sec_param', role='SECRETARIAT')
        self.client.force_authenticate(sec)
        res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)

    def test_auditeur_sees_empty_list(self):
        aud = make_user('aud_param', role='AUDITEUR')
        self.client.force_authenticate(aud)
        res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)

    def test_admin_can_update_and_history_created(self):
        admin = make_user('admin_upd', role='ADMIN')
        self.client.force_authenticate(admin)
        res = self.client.patch(self.url, {'valeur': 'nouvelle_valeur', 'motif_modification': 'test'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.param.refresh_from_db()
        self.assertEqual(self.param.valeur, 'nouvelle_valeur')
        self.assertTrue(ParametreHistorique.objects.filter(parametre=self.param).exists())

    def test_categories_endpoint(self):
        admin = make_user('admin_cat', role='ADMIN')
        self.client.force_authenticate(admin)
        res = self.client.get('/api/parametres/categories/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(any(c['value'] == 'general' for c in res.data))

    def test_types_endpoint(self):
        admin = make_user('admin_typ', role='ADMIN')
        self.client.force_authenticate(admin)
        res = self.client.get('/api/parametres/types/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(any(t['value'] == 'text' for t in res.data))

    def test_create_and_delete_forbidden(self):
        admin = make_user('admin_nodel', role='ADMIN')
        self.client.force_authenticate(admin)
        res = self.client.post(self.list_url, {'cle': 'injected', 'valeur': 'x'})
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        res = self.client.delete(self.url)
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_invalid_integer_rejected(self):
        admin = make_user('admin_int', role='ADMIN')
        self.client.force_authenticate(admin)
        p = Parametre.objects.create(
            cle='test_integer',
            libelle='Entier',
            categorie='presences',
            type='integer',
            valeur='10',
            valeur_defaut='10',
            modifiable=True,
            modifiable_par_roles='["ADMIN"]',
            lecturable_par_roles='["ADMIN"]',
            actif=True,
        )
        res = self.client.patch(f'/api/parametres/{p.pk}/', {'valeur': 'abc'})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        p.refresh_from_db()
        self.assertEqual(p.valeur, '10')

    def test_unknown_field_rejected(self):
        admin = make_user('admin_extra', role='ADMIN')
        self.client.force_authenticate(admin)
        res = self.client.patch(self.url, {'valeur': 'ok', 'cle': 'hacked'})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_critical_param_requires_confirmation_and_motif(self):
        admin = make_user('admin_crit', role='ADMIN')
        self.client.force_authenticate(admin)
        p = Parametre.objects.filter(cle='seuil_absence_minutes').first()
        if p is None:
            p = Parametre.objects.create(
                cle='seuil_absence_minutes',
                libelle='Seuil',
                categorie='presences',
                type='integer',
                valeur='60',
                valeur_defaut='60',
                modifiable=True,
                modifiable_par_roles='["ADMIN"]',
                lecturable_par_roles='["ADMIN"]',
                actif=True,
            )
        else:
            p.modifiable = True
            p.modifiable_par_roles = '["ADMIN"]'
            p.lecturable_par_roles = '["ADMIN"]'
            p.valeur = '60'
            p.save()
        url = f'/api/parametres/{p.pk}/'
        res = self.client.patch(url, {'valeur': '90'})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        res = self.client.patch(url, {
            'valeur': '90',
            'confirmation': True,
            'motif_modification': 'Ajustement délai badgeage',
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        p.refresh_from_db()
        self.assertEqual(p.valeur, '90')
        self.assertTrue(ParametreHistorique.objects.filter(parametre=p, nouvelle_valeur='90').exists())


class ParametresSocleEdgeCaseTests(TestCase):
    """Compléments L0/L7 : cas limites du cycle de vie et de l'audit."""

    @classmethod
    def setUpTestData(cls):
        cls.param = Parametre.objects.create(
            cle='test_edge',
            libelle='Cas limite',
            categorie='general',
            type='text',
            valeur='initial',
            valeur_defaut='initial',
            modifiable=True,
            modifiable_par_roles='["ADMIN"]',
            lecturable_par_roles='["ADMIN", "SECRETARIAT"]',
            actif=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.url = f'/api/parametres/{self.param.pk}/'

    def _admin(self):
        user = make_user('admin_edge', role='ADMIN')
        self.client.force_authenticate(user)
        return user

    def test_parametre_inactif_invisible_et_non_modifiable(self):
        # Contrat réel du ViewSet : get_queryset filtre actif=True par défaut
        # → un paramètre désactivé disparaît (404), donc non modifiable.
        self._admin()
        self.param.actif = False
        self.param.save(update_fields=['actif'])
        res = self.client.patch(self.url, {'valeur': 'pirate'})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.param.refresh_from_db()
        self.assertEqual(self.param.valeur, 'initial')
        self.assertFalse(ParametreHistorique.objects.filter(parametre=self.param).exists())

    def test_adresse_ip_enregistree_dans_historique(self):
        admin = self._admin()
        res = self.client.patch(self.url, {'valeur': 'avec-ip'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        hist = ParametreHistorique.objects.filter(parametre=self.param).latest('modifie_le')
        self.assertEqual(hist.nouvelle_valeur, 'avec-ip')
        self.assertEqual(hist.modifie_par, admin)
        # TestClient → '127.0.0.1' ; l'important est la présence du champ renseigné.
        self.assertTrue(hist.adresse_ip)

    def test_motif_modification_persiste(self):
        self._admin()
        motif = 'Mise à jour réglementaire INJS'
        self.client.patch(self.url, {'valeur': 'm2', 'motif_modification': motif})
        hist = ParametreHistorique.objects.filter(parametre=self.param).latest('modifie_le')
        self.assertEqual(hist.motif_modification, motif)

    def test_ancienne_valeur_conservee(self):
        self._admin()
        self.client.patch(self.url, {'valeur': 'apres'})
        hist = ParametreHistorique.objects.filter(parametre=self.param).latest('modifie_le')
        self.assertEqual(hist.ancienne_valeur, 'initial')
        self.assertEqual(hist.nouvelle_valeur, 'apres')

    def test_get_by_cle_helper(self):
        self.assertEqual(Parametre.get_by_cle('test_edge'), self.param)
        self.assertIsNone(Parametre.get_by_cle('cle_inexistante'))
        self.assertEqual(Parametre.get_by_cle('cle_inexistante', 'defaut'), 'defaut')

    def test_patch_vide_rejete_sans_historique(self):
        # Contrat réel du serializer : un PATCH sans champ modifiable → 400.
        self._admin()
        before = ParametreHistorique.objects.filter(parametre=self.param).count()
        res = self.client.patch(self.url, {})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            ParametreHistorique.objects.filter(parametre=self.param).count(),
            before,
        )
