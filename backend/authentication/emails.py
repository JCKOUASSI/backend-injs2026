import base64
import logging
import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.mail import send_mail

from authentication.role_groups import get_user_role

logger = logging.getLogger(__name__)

_LOGO_DATA_URI_CACHE = None

# Couleurs alignées sur frontend/src/index.css (:root --ci-*, --text-*)
_CI_ORANGE = '#F5B100'
_CI_ORANGE_DARK = '#E69700'
_CI_GREEN = '#2277C1'
_CI_GREEN_DARK = '#1A68AC'
_CI_LIGHT = '#FFFBF0'
_TEXT_PRIMARY = '#1e293b'
_TEXT_SECONDARY = '#64748b'
_BORDER = '#e2e8f0'
_CARD_BG = '#ffffff'
_FONT = "'Segoe UI', system-ui, -apple-system, sans-serif"

ROLE_LABELS = {
    'ADMIN': 'Administrateur',
    'DIRECTION': 'Direction',
    'CHEF_INJS_ADMIN': 'Chef INJS Admin',
    'INJS_ADMIN': 'INJS Admin',
    'CHEF_SECRETARIAT': 'Chef Secrétariat',
    'SECRETARIAT': 'Secrétariat',
    'FINANCE': 'Finance',
    'ENCADRANT': 'Encadrant',
    'FORMATEUR': 'Enseignant',
    'AUDITEUR': 'Étudiant',
}


def _logo_candidates():
    base_dir = Path(settings.BASE_DIR)
    return [
        base_dir / 'static' / 'img' / 'logo-injs.png',
        base_dir.parent / 'frontend' / 'src' / 'assets' / 'logo.png',
        base_dir / 'static' / 'img' / 'logo-sygepcpfae.png',
    ]


def _logo_data_uri() -> str:
    """Retourne le logo INJS encodé en data URI pour les emails HTML."""
    global _LOGO_DATA_URI_CACHE
    if _LOGO_DATA_URI_CACHE is not None:
        return _LOGO_DATA_URI_CACHE

    for path in _logo_candidates():
        if not path.is_file():
            continue
        mime, _ = mimetypes.guess_type(path.name)
        mime = mime or 'image/png'
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        _LOGO_DATA_URI_CACHE = f'data:{mime};base64,{encoded}'
        return _LOGO_DATA_URI_CACHE

    _LOGO_DATA_URI_CACHE = ''
    return _LOGO_DATA_URI_CACHE


def _html_logo_block() -> str:
    data_uri = _logo_data_uri()
    if not data_uri:
        return ''
    return (
        f"<div style='margin-bottom:14px;'>"
        f"<img src='{data_uri}' alt='INJS' "
        f"style='width:88px; height:auto; display:inline-block;'>"
        f"</div>"
    )


def _html_email_shell(*, title: str, subtitle: str, inner: str) -> str:
    """Enveloppe HTML commune (charte INJS / frontend)."""
    logo = _html_logo_block()
    return f"""
<!DOCTYPE html>
<html lang="fr">
<body style="margin:0; padding:24px 12px; background:{_CI_LIGHT}; font-family:{_FONT}; color:{_TEXT_PRIMARY};">
  <div style="max-width:600px; margin:0 auto;">
    <div style="background:linear-gradient(180deg, {_CI_GREEN_DARK} 0%, {_CI_GREEN} 100%); background-color:{_CI_GREEN_DARK}; padding:24px; border-radius:12px 12px 0 0; text-align:center; border-bottom:3px solid {_CI_ORANGE};">
      {logo}
      <h1 style="color:#fff; margin:0; font-size:1.35rem; font-weight:700;">{title}</h1>
      <p style="color:rgba(255,255,255,0.88); margin:8px 0 0; font-size:0.9rem;">{subtitle}</p>
    </div>
    <div style="background:{_CARD_BG}; padding:28px; border:1px solid {_BORDER}; border-top:none; border-radius:0 0 12px 12px; box-shadow:0 4px 24px rgba(0,0,0,0.06);">
      {inner}
    </div>
  </div>
</body>
</html>
"""


def _html_cta_button(href: str, label: str) -> str:
    return (
        f"<div style='text-align:center; margin:24px 0;'>"
        f"<a href='{href}' style='display:inline-block; background:{_CI_ORANGE}; color:#fff; "
        f"padding:12px 28px; border-radius:10px; text-decoration:none; font-weight:600; "
        f"font-size:1rem; border:1px solid {_CI_ORANGE_DARK};'>"
        f"{label}</a></div>"
    )


def _app_url():
    return (
        getattr(settings, 'FRONTEND_URL', None)
        or getattr(settings, 'PUBLIC_APP_URL', '')
        or ''
    ).rstrip('/')


def send_welcome_email(user, plain_password, *, mobile: bool = False):
    """Envoie un email de bienvenue à l'utilisateur avec ses identifiants initiaux.
    Ne fait rien si l'utilisateur n'a pas d'adresse email renseignée."""
    if not user.email:
        return

    full_name = user.get_full_name() or user.username
    role_label = ROLE_LABELS.get(get_user_role(user) or user.role, user.role)
    app_url = _app_url()

    if mobile:
        subject = "INJS — Vos identifiants application mobile"
        platform_label = "l'application mobile INJS (badge QR)"
        usage_hint = (
            "Utilisez ces identifiants pour vous connecter à l'application mobile "
            "et badgez vos présences."
        )
        login_url_line = ''
        cta = ''
        security_hint = (
            "Changez votre mot de passe dès votre première connexion dans l'application "
            "(Menu → Mon profil → Changer mon mot de passe)."
        )
    else:
        subject = "Bienvenue sur INJS — Vos identifiants de connexion"
        platform_label = "la plateforme INJS"
        usage_hint = "Connectez-vous avec les identifiants ci-dessous."
        login_url_line = f"\nURL de connexion : {app_url}/login\n" if app_url else ''
        cta = _html_cta_button(app_url + '/login', 'Se connecter') if app_url else ''
        security_hint = (
            "Changez votre mot de passe dès votre première connexion "
            "(Menu → Changer mon mot de passe)."
        )

    message = f"""Bonjour {full_name},

Votre compte sur {platform_label} a été créé.

Voici vos identifiants de connexion :

  Identifiant : {user.username}
  Mot de passe : {plain_password}
  Rôle         : {role_label}
{login_url_line}
{usage_hint}

Pour des raisons de sécurité, veuillez changer votre mot de passe dès votre première connexion.

Cordialement,
L'équipe DFRC — INJS
"""

    inner = f"""
    <p style="margin:0 0 12px; line-height:1.6;">Bonjour <strong>{full_name}</strong>,</p>
    <p style="margin:0 0 20px; color:{_TEXT_SECONDARY}; line-height:1.6;">Votre compte sur <strong style="color:{_TEXT_PRIMARY};">{platform_label}</strong> a été créé avec succès.</p>

    <div style="background:{_CI_LIGHT}; border:1px solid {_BORDER}; border-radius:10px; padding:20px; margin:20px 0;">
      <h3 style="margin:0 0 16px; color:{_CI_GREEN_DARK}; font-size:1.05rem;">Vos identifiants</h3>
      <table style="width:100%; border-collapse:collapse;">
        <tr>
          <td style="padding:10px 0; color:{_TEXT_SECONDARY}; width:40%;">Identifiant</td>
          <td style="padding:10px 0; font-weight:700; font-family:ui-monospace,monospace; font-size:1.02rem; color:{_TEXT_PRIMARY};">{user.username}</td>
        </tr>
        <tr style="border-top:1px solid {_BORDER};">
          <td style="padding:10px 0; color:{_TEXT_SECONDARY};">Mot de passe</td>
          <td style="padding:10px 0; font-weight:700; font-family:ui-monospace,monospace; font-size:1.02rem; color:{_TEXT_PRIMARY};">{plain_password}</td>
        </tr>
        <tr style="border-top:1px solid {_BORDER};">
          <td style="padding:10px 0; color:{_TEXT_SECONDARY};">Rôle</td>
          <td style="padding:10px 0; color:{_TEXT_PRIMARY};">{role_label}</td>
        </tr>
      </table>
    </div>

    {cta}

    <div style="background:#FFF8E0; border-left:4px solid {_CI_ORANGE_DARK}; padding:14px 18px; border-radius:8px; margin-top:8px;">
      <strong style="color:{_CI_ORANGE_DARK};">Sécurité</strong><br>
      <span style="color:{_TEXT_PRIMARY}; font-size:0.95rem; line-height:1.5;">{security_hint}</span>
    </div>

    <p style="margin-top:28px; color:{_TEXT_SECONDARY}; font-size:0.9rem; line-height:1.5;">
      Cordialement,<br>
      <strong style="color:{_TEXT_PRIMARY};">L'équipe DFRC — INJS</strong>
    </p>
    """

    html_message = _html_email_shell(
        title='INJS — DFRC',
        subtitle='Institut National de la Jeunesse et des Sports',
        inner=inner,
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )
        logger.info("Email de bienvenue envoyé à %s (%s)", user.email, user.username)
    except Exception as exc:
        logger.error("Échec envoi email à %s : %s", user.email, exc)


def send_suspect_heartbeat_email(encadrant, personne_nom, personne_numero, formation_titre, module_intitule, seance_label, silence_minutes):
    """Notifie l'encadrant d'un module qu'un étudiant n'envoie plus de signal de présence
    depuis `silence_minutes` minutes et est passé en statut HORS_LIGNE_SUSPECT."""
    if not encadrant or not encadrant.email:
        return

    encadrant_nom = encadrant.get_full_name() or encadrant.username
    app_url = _app_url()

    subject = f"[INJS] Alerte présence — {personne_nom} hors ligne ({silence_minutes} min)"

    message = f"""Bonjour {encadrant_nom},

Une alerte de présence nécessite votre vérification.

L'étudiant suivant n'a plus envoyé de signal depuis {silence_minutes} minutes :

  Nom      : {personne_nom}
  Badge N° : {personne_numero}
  Module   : {module_intitule}
  Séance   : {seance_label}

Son statut est passé à « Hors ligne — suspect ». Veuillez vérifier sa présence physique en salle.

{"Tableau de bord : " + app_url if app_url else ""}

Cordialement,
L'équipe DFRC — INJS
"""

    cta = _html_cta_button(app_url, 'Accéder au tableau de bord') if app_url else ''

    inner = f"""
    <p style="margin:0 0 16px; line-height:1.6;">Bonjour <strong>{encadrant_nom}</strong>,</p>

    <div style="background:#FFF8E0; border-left:4px solid {_CI_ORANGE_DARK}; padding:16px 20px; border-radius:8px; margin-bottom:22px;">
      <strong style="font-size:1.05rem; color:{_CI_ORANGE_DARK};">Étudiant hors ligne depuis {silence_minutes} minutes</strong>
    </div>

    <div style="background:{_CI_LIGHT}; border:1px solid {_BORDER}; border-radius:10px; padding:20px; margin:20px 0;">
      <h3 style="margin:0 0 16px; color:{_CI_GREEN_DARK}; font-size:1.05rem;">Informations</h3>
      <table style="width:100%; border-collapse:collapse;">
        <tr>
          <td style="padding:10px 0; color:{_TEXT_SECONDARY}; width:40%;">Étudiant</td>
          <td style="padding:10px 0; font-weight:700; color:{_TEXT_PRIMARY};">{personne_nom}</td>
        </tr>
        <tr style="border-top:1px solid {_BORDER};">
          <td style="padding:10px 0; color:{_TEXT_SECONDARY};">Badge N°</td>
          <td style="padding:10px 0; font-family:ui-monospace,monospace; color:{_TEXT_PRIMARY};">{personne_numero}</td>
        </tr>
        <tr style="border-top:1px solid {_BORDER};">
          <td style="padding:10px 0; color:{_TEXT_SECONDARY};">Module</td>
          <td style="padding:10px 0; color:{_TEXT_PRIMARY};">{module_intitule}</td>
        </tr>
        <tr style="border-top:1px solid {_BORDER};">
          <td style="padding:10px 0; color:{_TEXT_SECONDARY};">Séance</td>
          <td style="padding:10px 0; color:{_TEXT_PRIMARY};">{seance_label}</td>
        </tr>
        <tr style="border-top:1px solid {_BORDER};">
          <td style="padding:10px 0; color:{_TEXT_SECONDARY};">Silence</td>
          <td style="padding:10px 0; color:{_CI_ORANGE_DARK}; font-weight:700;">{silence_minutes} minutes sans signal</td>
        </tr>
      </table>
    </div>

    <p style="margin:0 0 8px; color:{_TEXT_PRIMARY}; line-height:1.6;">Veuillez vérifier la présence physique de cet étudiant en salle.</p>

    {cta}

    <p style="margin-top:28px; color:{_TEXT_SECONDARY}; font-size:0.9rem; line-height:1.5;">
      Cordialement,<br>
      <strong style="color:{_TEXT_PRIMARY};">L'équipe DFRC — INJS</strong>
    </p>
    """

    html_message = _html_email_shell(
        title='INJS — DFRC',
        subtitle='Alerte de présence',
        inner=inner,
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[encadrant.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(
            "Alerte heartbeat envoyée à l'encadrant %s pour %s",
            encadrant.email, personne_nom,
        )
    except Exception as exc:
        logger.error("Échec envoi alerte heartbeat à %s : %s", encadrant.email, exc)
