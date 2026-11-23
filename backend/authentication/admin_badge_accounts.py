"""Vue admin : création des comptes badge auditeurs / formateurs manquants."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from admin_mixins import admin_user_has_global_access, log_admin_audit

from .badge_provision import preview_missing_badge_accounts, provision_missing_badge_accounts
from .role_groups import user_has_perm
from presences.models import AuditLog


def can_provision_badge_accounts(user):
    if not user or not user.is_authenticated or not user.is_staff:
        return False
    if admin_user_has_global_access(user):
        return True
    return user_has_perm(user, 'authentication.mutate_users')


def _parse_formation_id(request):
    raw = request.GET.get('formation_id') or request.POST.get('formation_id') or ''
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@require_http_methods(['GET', 'POST'])
def provision_badge_accounts_view(request):
    if not can_provision_badge_accounts(request.user):
        raise PermissionDenied

    formation_id = _parse_formation_id(request)
    preview = preview_missing_badge_accounts(formation_id=formation_id)
    result = None

    if request.method == 'POST':
        include_auditeurs = request.POST.get('include_auditeurs') == '1'
        include_formateurs = request.POST.get('include_formateurs') == '1'
        if not include_auditeurs and not include_formateurs:
            messages.error(request, _('Sélectionnez au moins auditeurs ou formateurs.'))
        else:
            result = provision_missing_badge_accounts(
                formation_id=formation_id,
                include_auditeurs=include_auditeurs,
                include_formateurs=include_formateurs,
                send_email=True,
            )
            aud = result['auditeurs']
            frm = result['formateurs']
            messages.success(
                request,
                _(
                    'Comptes créés — auditeurs : %(a_created)s, formateurs : %(f_created)s. '
                    'Emails envoyés : %(emails)s. Erreurs : %(errors)s.'
                ) % {
                    'a_created': aud['created'],
                    'f_created': frm['created'],
                    'emails': aud['emails_sent'] + frm['emails_sent'],
                    'errors': aud['errors'] + frm['errors'],
                },
            )
            log_admin_audit(
                AuditLog.Action.USER_CREATE,
                request,
                cible_type='badge_provision',
                cible_numero='bulk',
                cible_nom='Provisionnement comptes badge',
                extra={
                    'formation_id': formation_id,
                    'auditeurs': aud,
                    'formateurs': frm,
                },
            )
            preview = preview_missing_badge_accounts(formation_id=formation_id)

    context = {
        **admin.site.each_context(request),
        'title': _('Créer les comptes badge manquants'),
        'preview': preview,
        'result': result,
        'formation_id': formation_id or '',
        'can_provision': True,
    }
    return render(request, 'admin/authentication/provision_badge_accounts.html', context)


class AdminBadgeAccountsMixin:
    """Ajoute un lien vers la page de provisionnement sur la liste User."""

    change_list_template = 'admin/authentication/user/change_list.html'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_provision_badge_accounts_link'] = can_provision_badge_accounts(
            request.user,
        )
        return super().changelist_view(request, extra_context=extra_context)


def attach_provision_badge_accounts_urls():
    if getattr(admin.site, '_provision_badge_accounts_urls', False):
        return

    original_get_urls = admin.site.get_urls

    def get_urls():
        custom = [
            path(
                'authentication/provision-badge-accounts/',
                admin.site.admin_view(provision_badge_accounts_view),
                name='authentication_provision_badge_accounts',
            ),
        ]
        return custom + original_get_urls()

    admin.site.get_urls = get_urls
    admin.site._provision_badge_accounts_urls = True


def provision_badge_accounts_admin_url():
    return reverse('admin:authentication_provision_badge_accounts')
