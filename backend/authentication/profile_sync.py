"""Synchronisation des profils métier (auditeur, formateur, encadrant) liés aux comptes User."""

import logging

from django.contrib.auth import get_user_model

from authentication.role_groups import user_in_roles, user_is_mobile_encadrant

User = get_user_model()
logger = logging.getLogger(__name__)


def _user_matricule(user):
    return (user.matricule or user.username or '').strip()


def _ensure_user_matricule(user):
    matricule = _user_matricule(user)
    if not matricule:
        return ''
    if not (user.matricule or '').strip():
        User.objects.filter(pk=user.pk).update(matricule=matricule)
        user.matricule = matricule
    return matricule


def _sync_encadrant_user_link(user):
    """Assure un matricule sur le compte encadrant (la fiche métier est le User lui-même)."""
    if not user_is_mobile_encadrant(user):
        return
    _ensure_user_matricule(user)


def _sync_formateur_user_link(user):
    """Lie le compte FORMATEUR à un profil Formateur, ou le crée s'il n'existe pas."""
    from formations.models import Formateur

    if not user_in_roles(user, {'FORMATEUR'}):
        return

    badge = _ensure_user_matricule(user)
    if not badge:
        Formateur.objects.filter(user=user).update(user=None)
        logger.warning(
            'sync_formateur_skipped user_id=%s username=%s reason=missing_badge',
            user.pk,
            getattr(user, 'username', None),
        )
        return

    Formateur.objects.filter(user=user).exclude(numerobadge__iexact=badge).update(user=None)

    formateur = Formateur.objects.filter(numerobadge__iexact=badge).first()
    if formateur:
        if formateur.user_id not in (None, user.id):
            logger.warning(
                'sync_formateur_skipped user_id=%s username=%s badge=%s reason=badge_linked_to_other_formateur other_formateur_id=%s',
                user.pk,
                getattr(user, 'username', None),
                badge,
                formateur.pk,
            )
            return
        updates = []
        if formateur.user_id != user.id:
            formateur.user = user
            updates.append('user')
        nom = (user.last_name or '').strip() or '—'
        prenom = (user.first_name or '').strip() or '—'
        if formateur.nom != nom:
            formateur.nom = nom
            updates.append('nom')
        if formateur.prenom != prenom:
            formateur.prenom = prenom
            updates.append('prenom')
        if formateur.email != (user.email or ''):
            formateur.email = user.email or ''
            updates.append('email')
        if formateur.telephone != (user.telephone or ''):
            formateur.telephone = user.telephone or ''
            updates.append('telephone')
        if formateur.organisation != (user.organisation or ''):
            formateur.organisation = user.organisation or ''
            updates.append('organisation')
        if updates:
            formateur.save(update_fields=updates)
        if user.secretariat_id and not formateur.secretariats.filter(pk=user.secretariat_id).exists():
            formateur.secretariats.add(user.secretariat)
        return

    formateur = Formateur.objects.create(
        numerobadge=badge,
        nom=(user.last_name or '').strip() or '—',
        prenom=(user.first_name or '').strip() or '—',
        email=user.email or '',
        telephone=user.telephone or '',
        organisation=user.organisation or '',
        user=user,
    )
    if user.secretariat_id:
        formateur.secretariats.add(user.secretariat)


def _update_participant_from_user(participant, user):
    """Aligne les champs profil de la fiche sur le compte + le matricule du compte sur la fiche."""
    updates = []
    if participant.user_id != user.id:
        participant.user = user
        updates.append('user')
    nom = (user.last_name or '').strip() or '—'
    prenom = (user.first_name or '').strip() or '—'
    if participant.nom != nom:
        participant.nom = nom
        updates.append('nom')
    if participant.prenom != prenom:
        participant.prenom = prenom
        updates.append('prenom')
    if participant.email != (user.email or ''):
        participant.email = user.email or ''
        updates.append('email')
    if participant.telephone != (user.telephone or ''):
        participant.telephone = user.telephone or ''
        updates.append('telephone')
    if participant.secretariat_id != getattr(user.secretariat, 'pk', None):
        participant.secretariat = user.secretariat
        updates.append('secretariat')
    user_mat = (user.matricule or '').strip()
    participant_mat = (participant.matricule or '').strip()
    if user_mat and user_mat != participant_mat:
        participant.matricule = user_mat
        updates.append('matricule')
    if updates:
        participant.save(update_fields=updates)
    # Matricule vide sur le compte : la fiche fait foi (dérive de format, badgeage).
    if participant_mat and not user_mat:
        User.objects.filter(pk=user.pk).update(matricule=participant_mat)
        user.matricule = participant_mat


def _sync_auditeur_user_link(user):
    """Lie le compte AUDITEUR à un profil Participant, ou le crée s'il n'existe pas.

    La fiche déjà rattachée au compte (``user_id``) fait autorité : on ne la
    délie jamais et on ne crée pas de doublon vide, même si le matricule/username
    du compte a un format différent (ex. « OPH-1 » vs « OPH1 »). C'est ce qui
    évitait auparavant qu'un simple écart de format fasse perdre l'inscription
    aux modules lors du badgeage.
    """
    from formations.models import Participant

    if not user_in_roles(user, {'AUDITEUR'}):
        return

    # 1. Fiche déjà liée au compte : autorité, on l'aligne et on s'arrête.
    linked = Participant.objects.filter(user=user).first()
    if linked is not None:
        _update_participant_from_user(linked, user)
        return

    matricule = _ensure_user_matricule(user)
    if not matricule:
        logger.warning(
            'sync_auditeur_skipped user_id=%s username=%s reason=missing_matricule',
            user.pk,
            getattr(user, 'username', None),
        )
        return

    # 2. Fiche existante par matricule (non liée à un autre compte).
    participant = Participant.objects.filter(matricule__iexact=matricule).first()
    if participant:
        if participant.user_id not in (None, user.id):
            logger.warning(
                'sync_auditeur_skipped user_id=%s username=%s matricule=%s reason=matricule_linked_to_other_participant other_participant_id=%s',
                user.pk,
                getattr(user, 'username', None),
                matricule,
                participant.pk,
            )
            return
        _update_participant_from_user(participant, user)
        return

    # 3. Aucun profil connu : on crée la fiche.
    Participant.objects.create(
        matricule=matricule,
        nom=(user.last_name or '').strip() or '—',
        prenom=(user.first_name or '').strip() or '—',
        email=user.email or '',
        telephone=user.telephone or '',
        secretariat=user.secretariat,
        user=user,
    )


def sync_user_profile_links(user):
    """Synchronise les profils métier selon le rôle du compte."""
    _sync_encadrant_user_link(user)
    _sync_formateur_user_link(user)
    _sync_auditeur_user_link(user)
