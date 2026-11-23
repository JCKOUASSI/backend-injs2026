"""Notifications à la Direction lors de modification de notes par un administrateur."""
from decimal import Decimal

from django.contrib.auth import get_user_model

from authentication.role_groups import ADMIN_LEVEL_ROLES, get_user_role

from .models import NotificationModificationNote


def _is_admin_modificateur(user):
    return get_user_role(user) in ADMIN_LEVEL_ROLES


def _notes_egales(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return Decimal(str(a)) == Decimal(str(b))


def note_deja_enregistree(existing):
    """True si une note numérique était déjà persistée (première saisie exclue)."""
    return existing is not None and existing.note is not None


def notifier_modification_note(modificateur, participant, module, colonne, ancienne_note, nouvelle_note):
    """
    Crée une notification pour chaque utilisateur Direction active.
    Ne fait rien si le modificateur n'est pas admin ou si la note n'était pas déjà enregistrée.
    """
    if not _is_admin_modificateur(modificateur):
        return
    if ancienne_note is None:
        return
    if _notes_egales(ancienne_note, nouvelle_note):
        return

    auteur_nom = modificateur.get_full_name() or modificateur.username
    auditeur_nom = f'{participant.nom} {participant.prenom}'.strip() or participant.matricule or 'Étudiant'
    module_lib = module.intitule or str(module)
    colonne_lib = colonne.libelle
    old_str = f'{ancienne_note}' if ancienne_note is not None else '—'
    new_str = f'{nouvelle_note}' if nouvelle_note is not None else '—'

    message = (
        f'{auteur_nom} a modifié la note de {auditeur_nom} '
        f'({colonne_lib}, module « {module_lib} ») : {old_str} → {new_str}.'
    )

    User = get_user_model()
    for dest in User.objects.filter(role=User.Role.DIRECTION, is_active=True).exclude(pk=modificateur.pk):
        NotificationModificationNote.objects.create(
            destinataire=dest,
            auteur=modificateur,
            participant=participant,
            module=module,
            colonne_libelle=colonne_lib,
            ancienne_note=ancienne_note,
            nouvelle_note=nouvelle_note,
            message=message,
        )
