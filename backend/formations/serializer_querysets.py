"""Querysets annotés pour éviter les N+1 dans les serializers."""
from django.db.models import (
    Count, IntegerField, OuterRef, Prefetch, Q, Subquery, Value,
)
from django.db.models.functions import Coalesce

from .models import Module, Participant, Secretariat, SessionModule


def annotate_sessions_for_serializer(qs):
    return qs.select_related('module', 'module__formateur').annotate(
        _nb_presences_part=Count(
            'pointages__participant',
            filter=Q(pointages__participant_id__isnull=False),
            distinct=True,
        ),
        _nb_presences_fmt=Count(
            'pointages__formateur',
            filter=Q(pointages__formateur_id__isnull=False),
            distinct=True,
        ),
        _nb_attendus_part=Count('module__module_participants__participant', distinct=True),
        _nb_attendus_fmt=Count('module__module_formateurs__formateur', distinct=True),
    )


def annotate_modules_for_serializer(qs):
    session_qs = annotate_sessions_for_serializer(
        SessionModule.objects.order_by('date_journee', 'numero')
    )
    return qs.select_related(
        'formation', 'secretariat', 'secretariat__type', 'formateur', 'site',
    ).annotate(
        _nb_participants=Count('module_participants', distinct=True),
    ).prefetch_related(
        Prefetch('sessions', queryset=session_qs),
    )


def annotate_secretariat_counts(qs):
    """Ajoute les compteurs d'un secrétariat via des sous-requêtes indépendantes.

    Trois Count sur des relations différentes dans une même requête feraient d'abord
    le produit participants × modules avant de dédupliquer, ce qui pousse Postgres à
    trier sur disque.
    """
    def compteur(sous_requete):
        return Coalesce(Subquery(sous_requete, output_field=IntegerField()), Value(0))

    participants = (
        Participant.objects.filter(secretariat=OuterRef('pk')).order_by().values('secretariat')
    )
    modules = (
        Module.objects.filter(secretariat=OuterRef('pk')).order_by().values('secretariat')
    )

    return qs.annotate(
        _nb_participants=compteur(participants.annotate(c=Count('id')).values('c')),
        _nb_modules=compteur(modules.annotate(c=Count('id')).values('c')),
        _nb_formations=compteur(
            modules.annotate(c=Count('formation_id', distinct=True)).values('c')
        ),
    )


def secretariat_queryset_for_serializer():
    return annotate_secretariat_counts(
        Secretariat.objects.select_related('responsable', 'type')
    ).prefetch_related('membres').order_by('nom')
