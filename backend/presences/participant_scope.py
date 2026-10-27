"""Résolution du périmètre Participant pour un compte auditeur."""

from django.db.models import Count, Q

from formations.models import Participant


def _compact_identifier(value):
    """Normalise un identifiant pour comparer les variantes de format (casse, espaces, ponctuation)."""
    return ''.join(ch for ch in (value or '').strip().upper() if ch.isalnum())


def _user_matricule_candidates(user):
    """Variantes compactes du matricule/username du compte."""
    candidates = set()
    for raw in (getattr(user, 'matricule', ''), getattr(user, 'username', '')):
        compact = _compact_identifier(raw)
        if compact:
            candidates.add(compact)
    return candidates


def _participant_matricule_filters(numero_upper, numero_compact, *, prefix=''):
    """Filtre Q sur matricule exact (casse) pour lookup SQL indexé."""
    field = f'{prefix}matricule' if prefix else 'matricule'
    filters = Q()
    if numero_upper:
        filters |= Q(**{f'{field}__iexact': numero_upper})
    if numero_compact and numero_compact != numero_upper:
        filters |= Q(**{f'{field}__iexact': numero_compact})
    return filters


def participant_in_module_by_matricule(module, numero_upper, numero_compact):
    """Fiche inscrite au module correspondant au matricule scanné (lookup SQL prioritaire)."""
    from formations.models import ModuleParticipant

    mat_filters = _participant_matricule_filters(
        numero_upper, numero_compact, prefix='participant__'
    )
    if mat_filters:
        insc = (
            ModuleParticipant.objects
            .filter(module=module)
            .filter(mat_filters)
            .select_related('participant')
            .first()
        )
        if insc and insc.participant:
            return insc.participant

    # Formats divergents (ex. OPH-2026-1 vs OPH20261) : repli compact léger.
    if not numero_upper and not numero_compact:
        return None
    for insc in (
        ModuleParticipant.objects
        .filter(module=module)
        .select_related('participant')
        .only(
            'participant__id',
            'participant__matricule',
            'participant__nom',
            'participant__prenom',
        )
    ):
        p = insc.participant
        if not p:
            continue
        stored_compact = _compact_identifier(p.matricule)
        if numero_compact and stored_compact == numero_compact:
            return p
        if numero_upper and (p.matricule or '').strip().upper() == numero_upper:
            return p
    return None


def participant_for_module(user, module, seance=None):
    """Fiche Participant de l'utilisateur réellement inscrite au module donné.

    Contrairement à ``primary_participant_for_user`` (qui choisit une fiche
    « principale » indépendamment du module), cette résolution s'appuie sur les
    inscriptions du module et tolère les écarts de format de matricule. Elle
    évite les faux négatifs « pas inscrit à ce module » lorsque le compte est
    rattaché à une autre fiche (ou à une fiche vide) que celle inscrite.

    Priorité : lien de compte (``user_id``) puis correspondance de matricule.
    Retourne ``None`` si aucune fiche inscrite ne correspond au compte.
    """
    from formations.models import ModuleParticipant

    insc = (
        ModuleParticipant.objects
        .filter(module=module, participant__user_id=user.pk)
        .select_related('participant')
        .first()
    )
    if insc and insc.participant:
        return insc.participant

    mat_filters = Q()
    for raw in (getattr(user, 'matricule', ''), getattr(user, 'username', '')):
        val = (raw or '').strip()
        if val:
            mat_filters |= Q(participant__matricule__iexact=val)
    if mat_filters:
        insc = (
            ModuleParticipant.objects
            .filter(module=module)
            .filter(mat_filters)
            .select_related('participant')
            .first()
        )
        if insc and insc.participant:
            return insc.participant

    candidates = _user_matricule_candidates(user)
    if candidates:
        for insc in (
            ModuleParticipant.objects
            .filter(module=module)
            .select_related('participant')
            .only('participant__id', 'participant__matricule', 'participant__user_id')
        ):
            p = insc.participant
            if p and _compact_identifier(p.matricule) in candidates:
                return p

    # Autoriser un rattrapage inter-cohorte planifié sur ce module.
    from .models import Rattrapage

    ids = participant_ids_for_user(user)
    if ids:
        rattrapage_qs = Rattrapage.objects.filter(
            participant_id__in=ids,
            seance_rattrapage__module=module,
            statut=Rattrapage.Statut.PLANIFIE,
        )
        if seance is not None:
            rattrapage_qs = rattrapage_qs.filter(seance_rattrapage=seance)
        rattrapage = rattrapage_qs.select_related('participant').first()
        if rattrapage is not None:
            return rattrapage.participant
    return None


def participant_ids_for_user(user):
    """IDs des fiches Participant dont les pointages concernent cet auditeur."""
    ids = set()
    for pk in Participant.objects.filter(user_id=user.pk).values_list('pk', flat=True):
        ids.add(pk)
    for matricule in {(user.matricule or '').strip(), (user.username or '').strip()}:
        if not matricule:
            continue
        for pk in Participant.objects.filter(matricule__iexact=matricule).values_list('pk', flat=True):
            ids.add(pk)
    return ids


def primary_participant_for_user(user):
    """Fiche Participant principale (liée au compte ou la plus badgeée)."""
    linked = Participant.objects.filter(user_id=user.pk).first()
    if linked is not None:
        return linked
    ids = participant_ids_for_user(user)
    if not ids:
        return None
    return (
        Participant.objects.filter(pk__in=ids)
        .annotate(nb_pt=Count('pointages'))
        .order_by('-user_id', '-nb_pt', 'pk')
        .first()
    )


def link_user_to_primary_participant(user):
    """Lie le compte à la fiche matricule existante si possible."""
    participant = primary_participant_for_user(user)
    if participant is None:
        return None
    updates = []
    if participant.user_id is None:
        participant.user = user
        updates.append('user')
    if updates:
        participant.save(update_fields=updates)
    matricule = (participant.matricule or '').strip()
    if matricule and (user.matricule or '').strip() != matricule:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.filter(pk=user.pk).update(matricule=matricule)
        user.matricule = matricule
    return participant
