"""L'admin Django du journal core est strictement en lecture seule."""
from django.contrib import admin
from django.test import RequestFactory, TestCase

from core.admin import CompteurCodeAdmin, EvenementAuditAdmin
from core.models import CompteurCode, EvenementAudit


class AdminLectureSeuleTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/admin/')

    def test_evenements_audit_sans_ecriture(self):
        modele_admin = EvenementAuditAdmin(EvenementAudit, admin.site)
        self.assertFalse(modele_admin.has_add_permission(self.request))
        self.assertFalse(modele_admin.has_change_permission(self.request))
        self.assertFalse(modele_admin.has_delete_permission(self.request))
        # Tous les champs sont en lecture seule.
        self.assertEqual(
            sorted(modele_admin.readonly_fields),
            sorted(f.name for f in EvenementAudit._meta.fields),
        )

    def test_compteurs_sans_ecriture(self):
        modele_admin = CompteurCodeAdmin(CompteurCode, admin.site)
        self.assertFalse(modele_admin.has_add_permission(self.request))
        self.assertFalse(modele_admin.has_change_permission(self.request))
        self.assertFalse(modele_admin.has_delete_permission(self.request))
