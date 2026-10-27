"""Notifications d'habilitation (U5).

Le SMTP n'existe pas dans le sandbox de démonstration : les notifications
sont matérialisées en base (``NotificationHabilitation``), traçables et
lisibles à l'écran ; en production, ce même service est le point d'accroche
du canal d'envoi (courriel/SMS), sans modifier les appelants.
"""
from ..models import CompteUtilisateur, NotificationHabilitation


def notifier(destinataire, categorie, titre, message='', compte=None, meta=None):
    """Crée une notification (idempotence à la charge de l'appelant)."""
    return NotificationHabilitation.objects.create(
        destinataire=destinataire,
        categorie=categorie,
        titre=titre,
        message=message,
        compte=compte,
        metadonnees=meta or {},
    )


def notifier_admins(categorie, titre, message='', meta=None):
    """Notifie le trio d'administration legacy (comptes actifs uniquement)."""
    from authentication.models import User
    admins = User.objects.filter(
        role__in=('ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN'),
        is_active=True,
    )
    return [
        notifier(admin, categorie, titre, message, None, meta)
        for admin in admins
    ]


def responsable_du_compte(compte):
    """Meilleur destinataire « responsable » disponible pour un compte.

    En l'absence d'annuaire de hiérarchie dans le périmètre U5, on retombe
    sur le créateur du compte, puis sur les administrateurs.
    """
    if compte and compte.cree_par_id:
        return compte.cree_par
    return None


def serialiser_notification(n):
    return {
        'id': n.pk,
        'categorie': n.categorie,
        'categorie_libelle': n.get_categorie_display(),
        'titre': n.titre,
        'message': n.message,
        'lu': n.lu,
        'date_creation': n.date_creation.isoformat(),
        'compte': n.compte_id,
    }
