"""Lot L3 — API du module Jurys.

Conventions du projet : vues fonctions ``@api_view``, routes ``path()``
explicites, permissions IsSecretariatOrDFRC (traitement staff) et IsDFRC
(étapes officielles : PV/valide/verrouille/publie). Aucune suppression :
les propositions et décisions ne sont jamais détruites (append-only).

Routes préfixées par ``/api/juries/`` (cf. jurys/urls.py).
"""
from django.core.exceptions import ValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsDFRC, IsSecretariatOrDFRC
from authentication.role_groups import get_user_role

from . import pv as pv_services
from . import services
from .models import (
    DecisionJury,
    MembreJury,
    NotificationJury,
    PropositionJury,
    PVJury,
    SessionJury,
)


def _serializer_membre(membre):
    """Membre de jury sérialisé.

    ``nom_affiche`` est fourni parce que l'écran générique de composition le
    consomme : on n'expose pas une donnée inventée, mais l'identité réelle du
    membre (nom complet, ou identifiant si l'utilisateur n'a pas de nom).
    """
    return {
        'id': membre.id,
        'user_id': membre.user_id,
        'nom': membre.user.get_full_name() or membre.user.username,
        'nom_affiche': membre.user.get_full_name() or membre.user.username,
        'fonction': membre.fonction,
        'ajoute_par_id': membre.ajoute_par_id,
    }


def _get_session(pk):
    return SessionJury.objects.filter(pk=pk).first()


def _sans_decimals(obj):
    """Conversion récursive des Decimal en float (JSON-safe).

    Le JSONRenderer de DRF ne sait pas sérialiser les ``decimal.Decimal`` ;
    on convertit donc les moyennes/notes en ``float`` au moment de la
    sérialisation, sans toucher au modèle (champs DécimalField persistés).
    """
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, list):
        return [_sans_decimals(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _sans_decimals(v) for k, v in obj.items()}
    return obj


def _serializer_session(session, detail=False):
    data = {
        'id': session.id,
        'libelle': session.libelle,
        'annee_academique_id': session.annee_academique_id,
        'ref_formation_id': session.ref_formation_id,
        'parcours_id': session.parcours_id,
        'niveau_id': session.niveau_id,
        'semestre_id': session.semestre_id,
        'maquette_id': session.maquette_id,
        'type_session': session.type_session,
        'statut': session.statut,
        'verrouillee': session.verrouillee,
        'created_at': session.created_at,
    }
    if detail:
        data.update({
            'membres': [
                {
                    'id': m.id,
                    'user_id': m.user_id,
                    'nom': m.user.get_full_name() or m.user.username,
                    'fonction': m.fonction,
                }
                for m in session.membres.select_related('user')
            ],
            'decisions': [
                {
                    'id': d.id,
                    'inscription_id': d.inscription_id,
                    'participant_id': d.participant_id,
                    'matricule': d.participant.matricule,
                    'nom': f'{d.participant.nom} {d.participant.prenom}'.strip(),
                    'decision': d.decision,
                    'credits_acquis': d.credits_acquis,
                    'moyenne_generale': (
                        float(d.moyenne_generale) if d.moyenne_generale is not None else None
                    ),
                    'mention': d.mention,
                    'decision_manuelle': d.decision_manuelle,
                    'justification': d.justification,
                }
                for d in session.decisions.select_related('participant')
                .order_by('participant__nom', 'participant__prenom')
            ],
            'pv': _serializer_pv(session.pv) if hasattr(session, 'pv') else None,
            'prochain_statut': (
                SessionJury.TRANSITIONS.get(session.statut)
            ),
        })
    return data


def _serializer_pv(pv):
    return {
        'id': pv.id,
        'sha256': pv.sha256,
        'genere_le': pv.genere_le,
        'fichier': pv.fichier.url if pv.fichier else None,
    }


def _propositions_courantes(session):
    """Dernière proposition par inscription (le moteur est append-only)."""
    courantes = {}
    for p in PropositionJury.objects.filter(session=session).select_related('participant').order_by('calcule_le'):
        courantes[p.inscription_id] = p
    return list(courantes.values())


def _get_inscription(pk):
    from scolarite.models import InscriptionAdministrative
    return InscriptionAdministrative.objects.filter(pk=pk).first()


def _user_model():
    from django.contrib.auth import get_user_model
    return get_user_model()


#: Filtres réellement supportés par `SessionJury` (relations existantes).
#: Chaque paramètre est validé côté base : aucun filtre fantôme n'est exposé.
FILTRES_SESSION = {
    'statut': 'statut',
    'annee_academique': 'annee_academique_id',
    'formation': 'ref_formation_id',
    'parcours': 'parcours_id',
    'niveau': 'niveau_id',
    'semestre': 'semestre_id',
    'maquette': 'maquette_id',
    'type_session': 'type_session',
}

#: Champs de tri autorisés (évite l'injection d'ordre via l'API).
TRIS_SESSION = ['annee_academique__libelle', 'statut', 'created_at', 'id']


def _sessions_filtrees(request):
    """Queryset des sessions : filtres réels + recherche + tri.

    Réutilise la pagination globale du projet (``PageNumberPagination``,
    ``PAGE_SIZE``) sans format local (§16/§19 du lot).
    """
    qs = SessionJury.objects.all()
    for param, champ in FILTRES_SESSION.items():
        valeur = request.query_params.get(param)
        if valeur:
            qs = qs.filter(**{champ: valeur})
    recherche = (request.query_params.get('q') or '').strip()
    if recherche:
        # `libelle` est l'unique champ texte libre du modèle : la recherche ne
        # porte que sur lui, pas sur les libellés d'autres tables (§18).
        qs = qs.filter(libelle__icontains=recherche)
    tri = request.query_params.get('ordering')
    if tri in TRIS_SESSION:
        qs = qs.order_by(tri)
    return qs


def _paginer_requete(request, queryset, serializer_liste):
    """Pagination DRF du projet : ``PageNumberPagination`` + ``PAGE_SIZE``.

    `serializer_liste` reçoit une page de queryset et renvoie la liste déjà
    sérialisée. Aucun format local n'est introduit (§16).
    """
    from rest_framework.pagination import PageNumberPagination
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(serializer_liste(page))
    return Response(serializer_liste(queryset))


def _has_role_complet(user):
    """ADMIN / INJS_ADMIN / CHEF_INJS_ADMIN : accès complet (IsDFRC complet)."""
    return (user and user.is_authenticated
            and getattr(user, 'role', None) in ('ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN'))


@extend_schema(
    operation_id='jurys_session_list',
    summary='Sessions de délibération (paginées, filtrables)',
    description=(
        'GET : liste paginée des sessions de jury du périmètre autorisé. '
        'POST : création d\'une session (réservée au personnel DFRC).'
    ),
    parameters=[
        OpenApiParameter('statut', OpenApiTypes.STR, required=False,
                         description='Statut de la session (valeurs de SessionJury.Statut).'),
        OpenApiParameter('type_session', OpenApiTypes.STR, required=False,
                         description='Type de session (NORMALE / RATTRAPAGE / RECTIFICATION).'),
        OpenApiParameter('annee_academique', OpenApiTypes.INT, required=False),
        OpenApiParameter('formation', OpenApiTypes.INT, required=False),
        OpenApiParameter('parcours', OpenApiTypes.INT, required=False),
        OpenApiParameter('niveau', OpenApiTypes.INT, required=False),
        OpenApiParameter('semestre', OpenApiTypes.INT, required=False),
        OpenApiParameter('maquette', OpenApiTypes.INT, required=False),
        OpenApiParameter('q', OpenApiTypes.STR, required=False,
                         description='Recherche sur le libellé de la session.'),
        OpenApiParameter('ordering', OpenApiTypes.STR, required=False,
                         description='Tri : ' + ', '.join(TRIS_SESSION)),
        OpenApiParameter('page', OpenApiTypes.INT, required=False,
                         description='Page demandée (pagination globale, page size 50).'),
    ],
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def session_list(request):
    """GET : sessions (filtres annee/formation/niveau/statut) — POST : création (DFRC)."""
    if request.method == 'POST':
        from authentication.permissions import IsDFRC
        from formations.models import RefFormation
        from scolarite.models import AnneeAcademique, Maquette, Niveau, Parcours, Semestre

        permission = IsDFRC()
        if not permission.has_permission(request, None):
            return Response({'detail': 'Création réservée au personnel autorisé.'}, status=403)
        # Les FK doivent être des instances (pas de pk brut).
        fk_modeles = {
            'annee_academique': AnneeAcademique,
            'ref_formation': RefFormation,
            'parcours': Parcours,
            'niveau': Niveau,
            'maquette': Maquette,
            'semestre': Semestre,
        }
        valeurs = {}
        for champ in ('annee_academique', 'ref_formation', 'parcours', 'niveau',
                      'maquette', 'semestre', 'type_session'):
            valeur = request.data.get(champ)
            if valeur is None or valeur == '':
                continue
            if champ in fk_modeles:
                modele = fk_modeles[champ]
                valeurs[champ] = modele.objects.filter(pk=valeur).first()
                if valeurs[champ] is None:
                    return Response(
                        {'detail': f'{champ} (id={valeur}) introuvable.'}, status=400,
                    )
            else:
                valeurs[champ] = valeur
        for obligatoire in ('annee_academique', 'ref_formation', 'niveau', 'maquette'):
            if not valeurs.get(obligatoire):
                return Response({'detail': f'« {obligatoire} » est requis.'}, status=400)
        session = SessionJury(
            libelle=(request.data.get('libelle') or '').strip(),
            creee_par=request.user, **valeurs,
        )
        try:
            session.full_clean()
            session.save()
        except ValidationError as exc:
            return Response({'detail': exc.messages}, status=400)
        from scolarite.models import journaliser
        journaliser('JURY_SESSION_CREEE', objet=session, acteur=request.user)
        return Response(_serializer_session(session, detail=True), status=201)

    qs = _sessions_filtrees(request).select_related(
        'annee_academique', 'ref_formation', 'niveau', 'parcours', 'maquette',
    )
    # Pagination du projet : la liste brute tronquée à 100 laisse le front deviner
    # s'il y a plus de 100 sessions (§16).
    return _paginer_requete(
        request, qs, lambda page: [_serializer_session(s) for s in page],
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def session_detail(request, pk):
    """Détail : session + membres + propositions courantes + décisions."""
    session = _get_session(pk)
    if session is None:
        return Response({'detail': 'Session introuvable.'}, status=404)
    data = _serializer_session(session, detail=True)
    data['propositions'] = [
        {
            'inscription_id': p.inscription_id,
            'participant_id': p.participant_id,
            'matricule': p.participant.matricule,
            'nom': f'{p.participant.nom} {p.participant.prenom}'.strip(),
            'decision_proposee': p.decision_proposee,
            'credits_acquis': p.credits_acquis,
            'empreinte': p.empreinte,
            'complet': p.resultat.get('complet'),
            'semestres': _sans_decimals(p.resultat.get('semestres', [])),
        }
        for p in _propositions_courantes(session)
    ]
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def session_action(request, pk):
    """Actions de workflow : ``transition``, ``calcul``, ``generer_pv``,
    ``publier``, ``verifier_decisions`` (PV/publie : DFRC uniquement)."""
    session = _get_session(pk)
    if session is None:
        return Response({'detail': 'Session introuvable.'}, status=404)

    action = (request.data.get('action') or '').strip()
    est_complet = _has_role_complet(request.user)
    if action in ('generer_pv', 'publier') and not est_complet:
        return Response({'detail': 'Action réservée au personnel autorisé.'}, status=403)

    try:
        if action == 'transition':
            session = services.transition(session, request.user)
        elif action == 'calcul':
            crees = services.calculer_propositions(session, request.user)
            return Response({'detail': f'{crees} proposition(s) calculée(s).', 'calculees': crees})
        elif action == 'generer_pv':
            pv_services.generer_pv(session, request.user)
            session.refresh_from_db()
        elif action == 'publier':
            session = services.publier(session, request.user)
        elif action == 'verifier_decisions':
            services.decisions_verrouillables(session)
            return Response({'detail': 'Toutes les décisions sont enregistrées.'})
        else:
            return Response({'detail': 'Action inconnue.'}, status=400)
    except ValidationError as exc:
        message = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
        return Response({'detail': message}, status=400)
    return Response(_serializer_session(session, detail=True))


@extend_schema(
    operation_id='jurys_session_membres',
    summary='Composition du jury (lecture) / ajout d’un membre (écriture)',
    description=(
        'GET : liste des membres de la session. '
        'POST : ajoute un membre (session non verrouillée).'
    ),
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def membre_liste_ou_ajout(request, pk):
    """Composition du jury : GET = liste, POST = ajout.

    Une seule URL pour les deux opérations, comme le veut le contrat REST :
    la consultation de la composition est une lecture, l'ajout une écriture.
    """
    if request.method == 'GET':
        session = _get_session(pk)
        if session is None:
            return Response({'detail': 'Session introuvable.'}, status=404)
        return Response([
            _serializer_membre(m) for m in session.membres.select_related('user')
        ])
    return _ajouter_membre(request, pk)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def membre_ajout(request, pk):
    """Ajoute un membre au jury (session non verrouillée)."""
    return _ajouter_membre(request, pk)


def _ajouter_membre(request, pk):
    """Implémentation de l'ajout, réutilisée par la route GET/POST."""
    session = _get_session(pk)
    if session is None:
        return Response({'detail': 'Session introuvable.'}, status=404)
    user_id = request.data.get('user_id')
    fonction = request.data.get('fonction') or MembreJury.Fonction.MEMBRE
    if not user_id:
        return Response({'detail': '« user_id » est requis.'}, status=400)
    User = _user_model()
    try:
        cible = User.objects.get(pk=user_id, is_active=True)
        membre = services.ajouter_membre(session, cible, fonction, request.user)
    except User.DoesNotExist:
        return Response({'detail': 'Utilisateur introuvable.'}, status=404)
    except ValidationError as exc:
        return Response({'detail': exc.messages}, status=400)
    return Response(
        {'id': membre.id, 'user_id': membre.user_id, 'fonction': membre.fonction},
        status=201,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def decision_saisie(request, pk):
    """Saisit la décision officielle d'un étudiant (justification si manuelle)."""
    session = _get_session(pk)
    if session is None:
        return Response({'detail': 'Session introuvable.'}, status=404)
    inscription = _get_inscription(request.data.get('inscription_id'))
    if inscription is None:
        return Response({'detail': 'Inscription introuvable.'}, status=404)
    decision = (request.data.get('decision') or '').strip()
    if decision not in DecisionJury.Decision.values:
        return Response({'detail': 'Décision invalide.'}, status=400)
    try:
        obj, _created = services.enregistrer_decision(
            session, inscription, decision, request.user,
            justification=request.data.get('justification', ''),
            mention=request.data.get('mention', ''),
            decision_manuelle=request.data.get('decision_manuelle'),
        )
    except ValidationError as exc:
        message = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
        return Response({'detail': message}, status=400)
    return Response(
        {'id': obj.id, 'decision': obj.decision, 'decision_manuelle': obj.decision_manuelle},
        status=201,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def pv_telechargement(request, pk):
    """Télécharge le PV PDF de la session."""
    session = _get_session(pk)
    if session is None:
        return Response({'detail': 'Session introuvable.'}, status=404)
    pv = PVJury.objects.filter(session=session).first()
    if pv is None or not pv.fichier:
        return Response({'detail': 'Aucun PV généré.'}, status=404)
    from django.http import FileResponse
    reponse = FileResponse(pv.fichier.open('rb'), content_type='application/pdf')
    nom = pv.fichier.name.split('/')[-1]
    reponse['Content-Disposition'] = f'attachment; filename="{nom}"'
    return reponse


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def notifications_jury(request):
    """Notifications de publication du jury (Direction)."""
    if get_user_role(request.user) != _user_model().Role.DIRECTION:
        return Response({'detail': 'Accès réservé à la Direction.'}, status=403)
    qs = NotificationJury.objects.filter(destinataire=request.user).select_related('session')
    if request.method == 'PATCH':
        ids = request.data.get('ids') or []
        qs.filter(id__in=ids).update(lu=True)
    items = list(qs[:50])
    return Response({
        'notifications': [
            {'id': n.id, 'message': n.message, 'session_id': n.session_id,
             'lu': n.lu, 'created_at': n.created_at}
            for n in items
        ],
        'non_lues': qs.filter(lu=False).count(),
    })


# ── Exposition API « Délibérations » (lecture seule) ──────────────────────
# Ces deux actions n'introduisent AUCUNE règle métier : elles exposent
# `services.analyser_deliberation` et `services.statistiques_deliberation`,
# qui s'appuient sur les modèles canoniques et le moteur LMD existant.
# Elles ne mutent rien et ne contournent aucun verrouillage.


@extend_schema(
    operation_id='jurys_session_anomalies',
    summary='Anomalies de la session de délibération',
    description=(
        'Anomalies réellement contrôlées par le workflow Jury '
        '(propositions absentes, décisions manquantes, justification '
        'obligatoire). Une anomalie `bloquante` empêche le verrouillage.'
    ),
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def session_anomalies(request, pk):
    session = _get_session(pk)
    if session is None:
        return Response({'detail': 'Session introuvable.'}, status=404)
    anomalies = services.analyser_deliberation(session)
    return Response({
        'session_id': session.pk,
        'statut': session.statut,
        'total': len(anomalies),
        'bloquantes': sum(1 for a in anomalies if a['bloquante']),
        'verrouillage_possible': not any(a['bloquante'] for a in anomalies),
        'anomalies': anomalies,
    })


@extend_schema(
    operation_id='jurys_session_statistiques',
    summary='Statistiques agrégées de la session',
    description=(
        'Agrégats calculés à la demande depuis DecisionJury / '
        'PropositionJury / inscriptions concernées (aucune valeur figée).'
    ),
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def session_statistiques(request, pk):
    session = _get_session(pk)
    if session is None:
        return Response({'detail': 'Session introuvable.'}, status=404)
    return Response(services.statistiques_deliberation(session))
