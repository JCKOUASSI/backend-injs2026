"""API REST des rattrapages inter-cohorte (création / suivi côté frontend web)."""
from datetime import date

from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrEncadrantOrDFRC
from formations.access import (
    modules_queryset_for_user,
    participants_queryset_for_user,
)
from formations.models import Module, Participant, SessionModule

from .models import Rattrapage
from .rattrapage_service import (
    RattrapageError,
    annuler_rattrapage,
    generer_presence_rattrapage,
    infer_module_origine,
    infer_seance_manquee,
    participant_deja_inscrit_module,
    reactiver_rattrapage_annule,
)


def _module_ids_for_user(user):
    return set(modules_queryset_for_user(user).values_list('id', flat=True))


def _seance_payload(seance):
    return {
        'id': seance.id,
        'date': seance.date_journee.isoformat() if seance.date_journee else None,
        'numero': seance.numero,
        'intitule': seance.intitule or f'Séance {seance.numero}',
        'heure_debut': seance.heure_debut_prevue.strftime('%H:%M') if seance.heure_debut_prevue else None,
        'heure_fin': seance.heure_fin_prevue.strftime('%H:%M') if seance.heure_fin_prevue else None,
    }


def _module_payload(module):
    if module is None:
        return None
    return {
        'id': module.id,
        'intitule': module.intitule,
        'formation': module.formation.formation if module.formation_id else '',
        'grade': module.grade,
        'groupe': module.groupe,
        'vague': module.vague,
        'cohorte': ' / '.join(x for x in (module.grade, module.groupe, module.vague) if x),
    }


def _participant_payload(p):
    return {
        'id': p.id,
        'matricule': p.matricule,
        'nom': p.nom,
        'prenom': p.prenom,
        'grade': p.grade,
        'groupe': p.groupe,
        'cohorte': ' / '.join(x for x in (p.grade, p.groupe) if x),
    }


def _rattrapage_payload(r):
    return {
        'id': r.id,
        'statut': r.statut,
        'statut_display': r.get_statut_display(),
        'motif': r.motif,
        'created_at': r.created_at.isoformat(),
        'participant': _participant_payload(r.participant),
        'seance_rattrapage': _seance_payload(r.seance_rattrapage),
        'module_accueil': _module_payload(r.module_rattrapage),
        'module_origine': _module_payload(r.module_origine),
        'seance_manquee': _seance_payload(r.seance_manquee) if r.seance_manquee_id else None,
        'pointage_id': r.pointage_id,
    }


def _rattrapages_scoped(user):
    module_ids = _module_ids_for_user(user)
    return (
        Rattrapage.objects
        .filter(seance_rattrapage__module_id__in=module_ids)
        .select_related(
            'participant',
            'seance_rattrapage', 'seance_rattrapage__module', 'seance_rattrapage__module__formation',
            'module_origine', 'module_origine__formation',
            'seance_manquee',
        )
    )


@api_view(['GET', 'POST'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def rattrapage_list_create(request):
    if request.method == 'GET':
        qs = _rattrapages_scoped(request.user).order_by('-created_at')
        statut = request.query_params.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        q = (request.query_params.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(participant__matricule__icontains=q)
                | Q(participant__nom__icontains=q)
                | Q(participant__prenom__icontains=q)
                | Q(seance_rattrapage__module__intitule__icontains=q)
                | Q(seance_rattrapage__module__formation__formation__icontains=q)
            )
        return Response([_rattrapage_payload(r) for r in qs[:300]])

    # POST — création (une ou plusieurs séances / plusieurs jours)
    data = request.data
    participant_id = data.get('participant_id')
    seance_ids = data.get('seance_rattrapage_ids')
    if not seance_ids:
        single = data.get('seance_rattrapage_id')
        seance_ids = [single] if single else []
    if isinstance(seance_ids, (str, int)):
        seance_ids = [seance_ids]

    if not participant_id or not seance_ids:
        return Response(
            {'detail': "L'auditeur et au moins une séance de rattrapage sont obligatoires."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    participant = participants_queryset_for_user(request.user).filter(pk=participant_id).first()
    if participant is None:
        return Response(
            {'detail': "Auditeur introuvable ou hors de votre périmètre."},
            status=status.HTTP_404_NOT_FOUND,
        )

    module_ids = _module_ids_for_user(request.user)
    seances = list(
        SessionModule.objects.select_related('module', 'module__formation')
        .filter(pk__in=seance_ids, module_id__in=module_ids)
    )
    if not seances:
        return Response(
            {'detail': "Aucune séance de rattrapage valide dans votre périmètre."},
            status=status.HTTP_404_NOT_FOUND,
        )

    module_origine = None
    if data.get('module_origine_id'):
        module_origine = Module.objects.filter(pk=data['module_origine_id']).first()
        if module_origine is None:
            return Response(
                {'detail': "Module d'origine introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not ModuleParticipant.objects.filter(
            participant=participant, module=module_origine,
        ).exists():
            return Response(
                {'detail': "L'auditeur n'est pas inscrit au module d'origine indiqué."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    seance_manquee = None
    if data.get('seance_manquee_id'):
        seance_manquee = SessionModule.objects.filter(pk=data['seance_manquee_id']).first()
        if seance_manquee is None:
            return Response(
                {'detail': 'Séance manquée introuvable.'},
                status=status.HTTP_404_NOT_FOUND,
            )

    motif = (data.get('motif') or '').strip()
    generer = str(data.get('generer_presence', '')).lower() in ('1', 'true', 'yes', 'on')

    deja_inscrit_ids = [
        s.id for s in seances
        if participant_deja_inscrit_module(participant, s.module)
    ]
    if deja_inscrit_ids:
        return Response(
            {
                'detail': (
                    "L'auditeur est déjà inscrit au module d'accueil — "
                    "le rattrapage inter-cohorte n'est pas nécessaire."
                ),
                'seance_ids': deja_inscrit_ids,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    from .models import AuditLog, _log_audit

    created, skipped, reactivated, errors = [], [], [], []
    for seance in seances:
        if module_origine and seance.module_id == module_origine.id:
            return Response(
                {'detail': "Le module d'origine ne peut pas être le module d'accueil."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        origine = infer_module_origine(participant, seance, module_origine=module_origine)
        manquee = infer_seance_manquee(
            participant,
            origine,
            seance,
            seance_manquee=seance_manquee if len(seances) == 1 else None,
        )

        existing = Rattrapage.objects.filter(
            participant=participant,
            seance_rattrapage=seance,
        ).first()
        if existing:
            if existing.statut == Rattrapage.Statut.ANNULE:
                rattrapage = reactiver_rattrapage_annule(
                    existing,
                    motif=motif,
                    module_origine=origine,
                    seance_manquee=manquee,
                    cree_par=request.user,
                )
                reactivated.append(seance.id)
                _log_audit(
                    action=AuditLog.Action.RATTRAPAGE_CREATE,
                    request=request,
                    cible_type='participant',
                    cible_numero=participant.matricule or str(participant.pk),
                    cible_nom=f"{participant.nom} {participant.prenom}".strip(),
                    formation=seance.module.formation if seance.module_id else None,
                    extra={
                        'rattrapage_id': rattrapage.pk,
                        'via_api': True,
                        'reactivated': True,
                    },
                )
            else:
                skipped.append(seance.id)
                continue
        else:
            rattrapage = Rattrapage.objects.create(
                participant=participant,
                seance_rattrapage=seance,
                module_origine=origine,
                seance_manquee=manquee,
                motif=motif,
                cree_par=request.user,
            )
            module = rattrapage.module_rattrapage
            _log_audit(
                action=AuditLog.Action.RATTRAPAGE_CREATE,
                request=request,
                cible_type='participant',
                cible_numero=participant.matricule or str(participant.pk),
                cible_nom=f"{participant.nom} {participant.prenom}".strip(),
                formation=module.formation if module else None,
                extra={'rattrapage_id': rattrapage.pk, 'via_api': True},
            )

        if generer:
            try:
                generer_presence_rattrapage(rattrapage, request=request)
            except RattrapageError as exc:
                errors.append({'seance_id': seance.id, 'detail': str(exc)})

        rattrapage.refresh_from_db()
        created.append(_rattrapage_payload(rattrapage))

    if not created:
        return Response(
            {'detail': "Un rattrapage existe déjà pour cet auditeur sur la/les séance(s) choisie(s).",
             'skipped': skipped},
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            'created': created,
            'skipped': skipped,
            'reactivated': reactivated,
            'errors': errors,
            'count': len(created),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def rattrapage_generer_presence(request, pk):
    rattrapage = _rattrapages_scoped(request.user).filter(pk=pk).first()
    if rattrapage is None:
        return Response({'detail': 'Rattrapage introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    if rattrapage.statut == Rattrapage.Statut.ANNULE:
        return Response(
            {'detail': 'Ce rattrapage est annulé.'}, status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        generer_presence_rattrapage(rattrapage, request=request)
    except RattrapageError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    rattrapage.refresh_from_db()
    return Response(_rattrapage_payload(rattrapage))


@api_view(['POST'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def rattrapage_annuler(request, pk):
    rattrapage = _rattrapages_scoped(request.user).filter(pk=pk).first()
    if rattrapage is None:
        return Response({'detail': 'Rattrapage introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    supprimer = str(request.data.get('supprimer_pointage', '')).lower() in ('1', 'true', 'yes', 'on')
    annuler_rattrapage(rattrapage, request=request, supprimer_pointage=supprimer)
    rattrapage.refresh_from_db()
    return Response(_rattrapage_payload(rattrapage))


@api_view(['GET'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def rattrapage_participants_search(request):
    q = (request.query_params.get('q') or '').strip()
    qs = participants_queryset_for_user(request.user)
    if q:
        qs = qs.filter(
            Q(matricule__icontains=q)
            | Q(nom__icontains=q)
            | Q(prenom__icontains=q)
        )
    qs = qs.order_by('nom', 'prenom')[:30]
    return Response([_participant_payload(p) for p in qs])


@api_view(['GET'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def rattrapage_seances_search(request):
    """Séances candidates (cohortes d'accueil) pour un rattrapage, scopées.

    Si ``participant`` est fourni, on privilégie les séances des modules
    correspondant aux cours où l'auditeur est inscrit ailleurs (même intitulé),
    et on signale les modules où il est déjà inscrit (``deja_inscrit``).
    """
    q = (request.query_params.get('q') or '').strip()
    module_ids = _module_ids_for_user(request.user)
    qs = (
        SessionModule.objects
        .filter(module_id__in=module_ids)
        .select_related('module', 'module__formation')
    )

    participant_id = request.query_params.get('participant')
    inscrit_module_ids = set()
    if participant_id:
        inscrit_module_ids = set(
            Module.objects.filter(
                module_participants__participant_id=participant_id,
            ).values_list('id', flat=True)
        )

    date_str = request.query_params.get('date')
    if date_str:
        try:
            qs = qs.filter(date_journee=date.fromisoformat(date_str))
        except ValueError:
            pass

    if q:
        qs = qs.filter(
            Q(module__intitule__icontains=q)
            | Q(module__formation__formation__icontains=q)
            | Q(module__grade__icontains=q)
            | Q(module__groupe__icontains=q)
            | Q(module__vague__icontains=q)
        )

    qs = qs.order_by('-date_journee', 'module__intitule', 'numero')[:60]
    out = []
    for s in qs:
        payload = _seance_payload(s)
        payload['module'] = _module_payload(s.module)
        payload['deja_inscrit'] = s.module_id in inscrit_module_ids
        out.append(payload)
    return Response(out)


@api_view(['GET'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def rattrapage_modules_search(request):
    """Modules d'accueil candidats, chacun avec toutes ses séances.

    Permet d'ajouter « tout le module en un clic » (rattrapage sur plusieurs jours).
    """
    q = (request.query_params.get('q') or '').strip()
    module_ids = _module_ids_for_user(request.user)
    modules = Module.objects.filter(id__in=module_ids).select_related('formation')
    if q:
        modules = modules.filter(
            Q(intitule__icontains=q)
            | Q(formation__formation__icontains=q)
            | Q(grade__icontains=q)
            | Q(groupe__icontains=q)
            | Q(vague__icontains=q)
        )
    modules = modules.order_by('formation__formation', 'intitule', 'grade', 'groupe')[:40]

    participant_id = request.query_params.get('participant')
    inscrit_module_ids = set()
    if participant_id:
        inscrit_module_ids = set(
            Module.objects.filter(
                module_participants__participant_id=participant_id,
            ).values_list('id', flat=True)
        )

    module_list = list(modules)
    seances_by_module = {}
    for s in (
        SessionModule.objects
        .filter(module_id__in=[m.id for m in module_list])
        .order_by('date_journee', 'numero')
    ):
        seances_by_module.setdefault(s.module_id, []).append(s)

    out = []
    for m in module_list:
        seances = seances_by_module.get(m.id, [])
        out.append({
            **_module_payload(m),
            'deja_inscrit': m.id in inscrit_module_ids,
            'nb_seances': len(seances),
            'seances': [_seance_payload(s) for s in seances],
        })
    return Response(out)
