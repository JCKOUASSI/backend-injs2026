"""Configuration du site admin Django (sans django-unfold)."""

from django.contrib import admin
from django.template.response import TemplateResponse

from config.admin_dashboard import admin_dashboard_callback
from authentication.admin_badge_accounts import attach_provision_badge_accounts_urls
from config.admin_guide import attach_admin_guide_urls


def setup_admin_site():
    from django.conf import settings

    admin.site.site_header = 'INJS LMD'
    admin.site.site_title = 'INJS LMD Admin'
    admin.site.index_title = 'Institut National de la Jeunesse et des Sports'
    admin.site.site_url = getattr(settings, 'PUBLIC_APP_URL', '')
    admin.site.enable_nav_sidebar = False

    def custom_index(request, extra_context=None):
        extra_context = extra_context or {}
        context = {
            **admin.site.each_context(request),
            **extra_context,
            'title': '',
            'subtitle': None,
            'app_list': admin.site.get_app_list(request),
        }
        context = admin_dashboard_callback(request, context)
        request.current_app = admin.site.name
        return TemplateResponse(
            request,
            admin.site.index_template or 'admin/index.html',
            context,
        )

    admin.site.index = custom_index

    def custom_logout(self, request, extra_context=None):
        from django.contrib.auth.views import LogoutView
        from django.urls import reverse

        defaults = {
            'next_page': reverse('admin:login', current_app=self.name),
            'extra_context': {
                **self.each_context(request),
                'has_permission': False,
                **(extra_context or {}),
            },
        }
        request.current_app = self.name
        return LogoutView.as_view(**defaults)(request)

    admin.site.logout = custom_logout.__get__(admin.site, type(admin.site))

    from django.views.decorators.csrf import csrf_exempt
    admin.site.login = csrf_exempt(admin.site.login)

    attach_admin_guide_urls()
    attach_provision_badge_accounts_urls()
