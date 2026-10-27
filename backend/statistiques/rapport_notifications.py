"""Notifications lors de modification / suppression / workflow de rapports."""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from .models import NotificationRapport

logger = logging.getLogger(__name__)

ADMIN_RAPPORT_ROLES = {'ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'}
VALIDATION_RAPPORT_ROLES = ADMIN_RAPPORT_ROLES

WORKFLOW_EVENEMENTS = {
    'soumettre': NotificationRapport.Evenement.SOUMIS,
    'valider': NotificationRapport.Evenement.VALIDE,
    'publier': NotificationRapport.Evenement.PUBLIE,
    'rejeter': NotificationRapport.Evenement.REJETE,
}


def _destinataires_rapport(rapport, auteur):
    """Générateur, validateur et autres administrateurs (hors auteur de l'action)."""
    users = []
    seen = set()
    if auteur:
        seen.add(auteur.pk)

    for u in (getattr(rapport, 'generateur', None), getattr(rapport, 'validateur', None)):
        if u and u.pk not in seen:
            users.append(u)
            seen.add(u.pk)

    for u in get_user_model().objects.filter(role__in=ADMIN_RAPPORT_ROLES, is_active=True):
        if u.pk not in seen:
            users.append(u)
            seen.add(u.pk)

    return users


def _destinataires_workflow(rapport, auteur, action):
    """Destinataires selon l'étape du workflow."""
    seen = set()
    if auteur:
        seen.add(auteur.pk)
    users = []

    if action == 'soumettre':
        for u in get_user_model().objects.filter(role__in=VALIDATION_RAPPORT_ROLES, is_active=True):
            if u.pk not in seen:
                users.append(u)
                seen.add(u.pk)
    elif action in ('valider', 'publier', 'rejeter'):
        gen = getattr(rapport, 'generateur', None)
        if gen and gen.pk not in seen:
            users.append(gen)
    return users


def _envoyer_email(destinataire, sujet, corps):
    if not getattr(destinataire, 'email', None):
        return
    try:
        from django.core.mail import send_mail
        send_mail(
            sujet,
            corps,
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@sygep.local'),
            [destinataire.email],
            fail_silently=True,
        )
    except Exception as exc:
        logger.warning('E-mail notification rapport non envoyé à %s : %s', destinataire.email, exc)


def _creer_notifications(destinataires, rapport, evenement, auteur, message):
    titre = rapport.titre if rapport else ''
    rapport_id = rapport.pk if rapport else None
    label_evt = dict(NotificationRapport.Evenement.choices).get(evenement, evenement)
    auteur_nom = auteur.get_full_name() if auteur else 'Administrateur'

    for dest in destinataires:
        NotificationRapport.objects.create(
            destinataire=dest,
            evenement=evenement,
            rapport_id=rapport_id,
            rapport_titre=titre,
            message=message,
            auteur=auteur,
        )
        sujet = f"[SYGEP-CPFAE] {label_evt} — {titre}"
        corps = (
            f"Bonjour {dest.get_full_name() or dest.username},\n\n"
            f"{message}\n\n"
            f"Action effectuée par : {auteur_nom}\n\n"
            f"— SYGEP-CPFAE / Statistiques & Bilans"
        )
        _envoyer_email(dest, sujet, corps)


def notifier_rapport(rapport, evenement, auteur, message):
    """Crée les notifications in-app (+ e-mail) pour les parties prenantes."""
    _creer_notifications(
        _destinataires_rapport(rapport, auteur),
        rapport,
        evenement,
        auteur,
        message,
    )


def notifier_rapport_workflow(rapport, action, auteur, commentaire=''):
    """Notifications workflow : soumettre → validateurs ; valider/publier/rejeter → générateur."""
    evenement = WORKFLOW_EVENEMENTS.get(action)
    if not evenement:
        return

    auteur_nom = auteur.get_full_name() or auteur.username
    titre = rapport.titre
    messages = {
        'soumettre': f'Le rapport « {titre} » a été soumis à validation par {auteur_nom}.',
        'valider': f'Le rapport « {titre} » a été validé par {auteur_nom}.',
        'publier': f'Le rapport « {titre} » a été publié par {auteur_nom}.',
        'rejeter': f'Le rapport « {titre} » a été rejeté par {auteur_nom}.',
    }
    message = messages[action]
    commentaire = (commentaire or '').strip()
    if commentaire:
        message += f' Commentaire : {commentaire}'

    destinataires = _destinataires_workflow(rapport, auteur, action)
    if destinataires:
        _creer_notifications(destinataires, rapport, evenement, auteur, message)


def notifier_rapport_supprime(titre, rapport_id, generateur, validateur, auteur, message):
    """Notification après suppression (rapport déjà effacé)."""
    class _Stub:
        pass

    stub = _Stub()
    stub.titre = titre
    stub.pk = rapport_id
    stub.generateur = generateur
    stub.validateur = validateur
    notifier_rapport(stub, NotificationRapport.Evenement.SUPPRIME, auteur, message)
