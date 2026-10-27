from django.conf import settings


def public_urls(request):
    return {
        'PUBLIC_APP_URL': getattr(settings, 'PUBLIC_APP_URL', 'https://injs.badge-qr-code.pro'),
        'PUBLIC_QR_SCAN_ENABLED': getattr(settings, 'PUBLIC_QR_SCAN_ENABLED', False),
    }


def admin_ui(request):
    """Navigation latérale et variables pour l'interface admin personnalisée."""
    path = getattr(request, 'path', '') or ''
    if not path.startswith('/admin'):
        return {}
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {}

    from config.admin_sidebar import get_admin_sidebar_navigation

    return {
        'admin_sidebar_navigation': get_admin_sidebar_navigation(),
    }
