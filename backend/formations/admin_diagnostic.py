from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

from .volume_horaire import run_organisation_diagnostic


class VolumeHoraireDiagnosticView(TemplateView):
    template_name = 'admin/formations/volume_horaire_diagnostic.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        depassements_only = self.request.GET.get('depassements_only') == '1'
        context.update({
            'title': 'Diagnostic volume horaire',
            'result': run_organisation_diagnostic(
                self.request,
                depassements_only=depassements_only,
            ),
            'depassements_only': depassements_only,
        })
        return context


def attach_volume_diagnostic_admin_urls():
    from formations.models import Module

    if getattr(admin.site, '_org_volume_diag_urls', False):
        return

    module_admin = admin.site._registry[Module]
    original_get_urls = admin.site.get_urls

    def get_urls():
        custom = [
            path(
                'diagnostique-volume-horaire/',
                admin.site.admin_view(
                    VolumeHoraireDiagnosticView.as_view()
                ),
                name='formations_volume_horaire_diagnostic',
            ),
        ]
        return custom + original_get_urls()

    admin.site.get_urls = get_urls
    admin.site._org_volume_diag_urls = True
