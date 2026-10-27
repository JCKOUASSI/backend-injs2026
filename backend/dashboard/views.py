"""
Vues actives du dashboard Django.

Vues publiques / auth dans dashboard/urls.py :
  - login_view, logout_view, badge_view, qr_badge_privacy_view

Toutes les autres vues HTML (formations, participants, sessions…) ont été
remplacées par le frontend React. Elles sont archivées dans views_legacy.py.
"""
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from django.shortcuts import render, redirect

from presences.models import AuditLog, _log_audit

User = get_user_model()

from authentication.role_groups import DUAL_ACCESS_ROLES, ALLOWED_WEB_ROLES, get_user_role, user_in_roles


# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated and user_in_roles(request.user, ALLOWED_WEB_ROLES):
        return redirect('web-dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user and user_in_roles(user, ALLOWED_WEB_ROLES):
            login(request, user)
            _log_audit(
                action=AuditLog.Action.USER_LOGIN,
                request=request,
                cible_type='user',
                cible_numero=user.username,
                cible_nom=user.get_full_name() or user.username,
                extra={'role': get_user_role(user), 'via': 'web_dashboard'},
            )
            return redirect('web-dashboard')
        elif user:
            return render(request, 'dashboard/login.html', {
                'error': 'Accès réservé au personnel autorisé (administration, CPFAE, secrétariat, finance, encadrants).'
            })
        else:
            return render(request, 'dashboard/login.html', {
                'error': 'Identifiants invalides.'
            })
    return render(request, 'dashboard/login.html')


def logout_view(request):
    if request.user.is_authenticated:
        _log_audit(
            action=AuditLog.Action.USER_LOGOUT,
            request=request,
            cible_type='user',
            cible_numero=request.user.username,
            cible_nom=request.user.get_full_name() or request.user.username,
            extra={'via': 'web_dashboard'},
        )
    logout(request)
    return redirect('web-login')


def badge_view(request):
    """Page publique de badgeage — pas de login requis."""
    if not settings.PUBLIC_QR_SCAN_ENABLED:
        return render(request, 'dashboard/badge_disabled.html', status=403)
    return render(request, 'dashboard/badge.html')


def qr_badge_privacy_view(request):
    """Politique de confidentialité (app mobile QR Badge) — publique, pour URL Play Console / App Store."""
    return render(request, 'dashboard/qr_badge_privacy.html')


def qr_badge_support_view(request):
    """Page support (app mobile QR Badge) — publique, pour URL "Support" App Store Connect."""
    return render(request, 'dashboard/qr_badge_support.html')
