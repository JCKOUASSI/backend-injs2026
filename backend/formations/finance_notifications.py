"""Notifications in-app pour le workflow ajustements finance."""
from django.contrib.auth import get_user_model

from .models import NotificationFinanceAjustement


def _auteur_label(user):
    return user.get_full_name() or user.username if user else 'Système'


def _session_label(ajustement):
    session = ajustement.session
    module = session.module if session else None
    parts = []
    if module:
        parts.append(module.intitule or str(module))
    if session:
        parts.append(session.intitule or f'Séance {session.numero}')
    return ' — '.join(parts) or 'Séance'


def _creer(destinataires, ajustement, evenement, auteur, message):
    for dest in destinataires:
        NotificationFinanceAjustement.objects.create(
            destinataire=dest,
            auteur=auteur,
            ajustement=ajustement,
            evenement=evenement,
            message=message,
        )


def notifier_ajustement_propose(ajustement, auteur):
    """Proposition → Direction (hors auteur)."""
    User = get_user_model()
    seen = {auteur.pk} if auteur else set()
    destinataires = [
        u for u in User.objects.filter(role=User.Role.DIRECTION, is_active=True)
        if u.pk not in seen
    ]
    if not destinataires:
        return

    formateur = ajustement.formateur
    formateur_nom = f'{formateur.nom} {formateur.prenom}'.strip() if formateur else 'Formateur'
    delta = ajustement.minutes_delta
    signe = '+' if delta > 0 else ''
    message = (
        f'{_auteur_label(auteur)} a proposé un ajustement de {signe}{delta} min '
        f'pour {formateur_nom} ({_session_label(ajustement)}). '
        f'Motif : {ajustement.motif}'
    )
    _creer(destinataires, ajustement, NotificationFinanceAjustement.Evenement.PROPOSE, auteur, message)


def notifier_ajustement_valide(ajustement, auteur):
    """Validation → proposeur."""
    proposeur = ajustement.proposed_by
    if not proposeur or not proposeur.is_active or (auteur and proposeur.pk == auteur.pk):
        return

    delta = ajustement.minutes_delta
    signe = '+' if delta > 0 else ''
    message = (
        f'{_auteur_label(auteur)} a validé votre ajustement de {signe}{delta} min '
        f'({_session_label(ajustement)}).'
    )
    _creer([proposeur], ajustement, NotificationFinanceAjustement.Evenement.VALIDE, auteur, message)


def notifier_ajustement_rejete(ajustement, auteur, rejection_motif=''):
    """Rejet → proposeur."""
    proposeur = ajustement.proposed_by
    if not proposeur or not proposeur.is_active or (auteur and proposeur.pk == auteur.pk):
        return

    delta = ajustement.minutes_delta
    signe = '+' if delta > 0 else ''
    message = (
        f'{_auteur_label(auteur)} a rejeté votre ajustement de {signe}{delta} min '
        f'({_session_label(ajustement)}).'
    )
    motif = (rejection_motif or ajustement.rejection_motif or '').strip()
    if motif:
        message += f' Motif : {motif}'
    _creer([proposeur], ajustement, NotificationFinanceAjustement.Evenement.REJETE, auteur, message)
