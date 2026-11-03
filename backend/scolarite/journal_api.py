"""API du Journal de scolarité — deux périmètres distincts, enfin lisibles.

L'écran historique branchait le descripteur « journal_scolarite » sur la
liste des étudiants : il affichait 3 527 dossiers avec leurs UUID, pas un
journal. Ce module expose proprement les deux journaux du domaine, que
l'ancien écran confondait :

- **Événements de parcours** (``EvenementScolarite``) : cycle de vie des
  dossiers étudiants (passages, redoublements, transferts, radiations,
  diplômations…) — alimentés par les services métier et, pour les
  chargements initiaux, reconstitués depuis les inscriptions validées
  (commande ``reconstruire_journal_parcours``, lignes étiquetées) ;
- **Traçabilité des opérations** (``JournalScolarite``) : audit append-only
  écrit par ``journaliser()`` dans tous les modules LMD (candidatures,
  pièces, inscriptions, jurys, EDT…). Il n'existait aucun endpoint de liste :
  ces 1 158 entrées étaient invisibles dans l'interface.

Lecture seule : l'écriture d'un événement de parcours continue de passer
par ``POST /scolarite/etudiants/<id>/evenements/`` (fiche étudiant).
"""
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC

from .models import EvenementScolarite, JournalScolarite

MARQUE_RECONSTITUE = '[Reconstitué]'
PAGE_TAILLE_MAX = 100


def _pagination(request):
    """(page, page_size) validés, ou ``Response`` 400 si incohérents."""
    try:
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 25))
    except (TypeError, ValueError):
        return Response(
            {'error': 'Les paramètres page et page_size doivent être numériques.'},
            status=400,
        )
    if page < 1 or page_size < 1 or page_size > PAGE_TAILLE_MAX:
        return Response(
            {'error': 'page doit être >= 1 et page_size compris entre 1 et 100.'},
            status=400,
        )
    return page, page_size


def _enveloppe(queryset, page, page_size, serialiser):
    total = queryset.count()
    start = (page - 1) * page_size
    return Response({
        'results': [serialiser(objet) for objet in queryset[start:start + page_size]],
        'count': total,
        'total_pages': (total + page_size - 1) // page_size,
        'page': page,
        'page_size': page_size,
    })


def _serialize_evenement(evenement):
    participant = evenement.etudiant.participant
    inscription = evenement.inscription
    return {
        'id': evenement.id,
        'type_evenement': evenement.type_evenement,
        'type_libelle': evenement.get_type_evenement_display(),
        'date_evenement': evenement.date_evenement,
        'etudiant_id': evenement.etudiant_id,
        'matricule': participant.matricule,
        'etudiant': ' '.join(
            (participant.nom, participant.prenom or ''),
        ).strip(),
        'inscription_id': evenement.inscription_id,
        'formation': inscription.ref_formation.intitule if inscription else None,
        'niveau': inscription.niveau.code if inscription else None,
        'annee_academique': (
            inscription.annee_academique.libelle if inscription else None
        ),
        'ancienne_valeur': evenement.ancienne_valeur,
        'nouvelle_valeur': evenement.nouvelle_valeur,
        'commentaire': evenement.commentaire,
        'enregistre_par': (
            evenement.enregistre_par.username if evenement.enregistre_par else None
        ),
        # Les lignes déduites des inscriptions (chargements initiaux) sont
        # explicitement marquées : l'écran les distingue des saisies humaines.
        'reconstitue': evenement.commentaire.startswith(MARQUE_RECONSTITUE),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def journal_evenements(request):
    """Chronologie globale des événements de parcours (paginée, filtrable)."""
    pagination = _pagination(request)
    if isinstance(pagination, Response):
        return pagination
    page, page_size = pagination

    queryset = EvenementScolarite.objects.select_related(
        'etudiant__participant', 'inscription__ref_formation',
        'inscription__niveau', 'inscription__annee_academique', 'enregistre_par',
    )
    type_evenement = request.query_params.get('type_evenement')
    if type_evenement:
        if type_evenement not in EvenementScolarite.Type.values:
            return Response({'error': 'Type d’événement inconnu.'}, status=400)
        queryset = queryset.filter(type_evenement=type_evenement)
    etudiant_id = request.query_params.get('etudiant_id')
    if etudiant_id:
        queryset = queryset.filter(etudiant_id=etudiant_id)
    for parametre, champ in (
        ('annee_academique_id', 'inscription__annee_academique_id'),
        ('ref_formation_id', 'inscription__ref_formation_id'),
        ('niveau_id', 'inscription__niveau_id'),
        ('date_debut', 'date_evenement__gte'),
        ('date_fin', 'date_evenement__lte'),
    ):
        valeur = request.query_params.get(parametre)
        if valeur:
            queryset = queryset.filter(**{champ: valeur})
    recherche = request.query_params.get('search') or request.query_params.get('q')
    if recherche:
        queryset = queryset.filter(
            Q(etudiant__participant__matricule__icontains=recherche)
            | Q(etudiant__participant__nom__icontains=recherche)
            | Q(etudiant__participant__prenom__icontains=recherche)
            | Q(commentaire__icontains=recherche)
        )
    return _enveloppe(queryset, page, page_size, _serialize_evenement)


def _serialize_audit(entree):
    horodatage = entree.timestamp
    return {
        'id': entree.id,
        'action': entree.action,
        'action_libelle': entree.get_action_display(),
        'objet_type': entree.objet_type,
        'objet_id': entree.objet_id,
        'objet_libelle': entree.objet_libelle,
        'acteur': entree.acteur.username if entree.acteur else None,
        'acteur_label': entree.acteur_label,
        'ancienne_valeur': entree.ancienne_valeur,
        'nouvelle_valeur': entree.nouvelle_valeur,
        'commentaire': entree.commentaire,
        'timestamp': timezone.localtime(horodatage).isoformat(),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def journal_audit(request):
    """Traçabilité des opérations LMD (JournalScolarite, lecture seule)."""
    pagination = _pagination(request)
    if isinstance(pagination, Response):
        return pagination
    page, page_size = pagination

    queryset = JournalScolarite.objects.select_related('acteur')
    action = request.query_params.get('action')
    if action:
        if action not in JournalScolarite.Action.values:
            return Response({'error': 'Action inconnue.'}, status=400)
        queryset = queryset.filter(action=action)
    objet_type = request.query_params.get('objet_type')
    if objet_type:
        queryset = queryset.filter(objet_type=objet_type)
    recherche = request.query_params.get('search') or request.query_params.get('q')
    if recherche:
        queryset = queryset.filter(
            Q(objet_libelle__icontains=recherche)
            | Q(acteur_label__icontains=recherche)
            | Q(commentaire__icontains=recherche)
            | Q(nouvelle_valeur__icontains=recherche)
        )
    return _enveloppe(queryset, page, page_size, _serialize_audit)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def journal_stats(request):
    """Panorama du journal : parcours par type/mois + facettes de traçabilité."""
    evenements = EvenementScolarite.objects.all()
    par_type = {code: 0 for code in EvenementScolarite.Type.values}
    for ligne in evenements.values('type_evenement').annotate(total=Count('id')):
        par_type[ligne['type_evenement']] = ligne['total']

    par_mois = [
        {'mois': ligne['mois'].strftime('%Y-%m'), 'total': ligne['total']}
        for ligne in evenements.annotate(mois=TruncMonth('date_evenement'))
        .values('mois').annotate(total=Count('id')).order_by('mois')
        if ligne['mois'] is not None
    ]

    audit = JournalScolarite.objects.all()
    return Response({
        'total': evenements.count(),
        'dossiers_concernes': evenements.values('etudiant').distinct().count(),
        'reconstitues': evenements.filter(
            commentaire__startswith=MARQUE_RECONSTITUE,
        ).count(),
        'par_type': par_type,
        'par_mois': par_mois,
        'audit_total': audit.count(),
        'audit_par_action': [
            {
                'action': ligne['action'],
                'libelle': JournalScolarite.Action(ligne['action']).label,
                'total': ligne['total'],
            }
            for ligne in audit.values('action').annotate(total=Count('id'))
            .order_by('-total', 'action')[:30]
        ],
        'audit_par_objet': [
            {'objet_type': ligne['objet_type'], 'total': ligne['total']}
            for ligne in audit.values('objet_type').annotate(total=Count('id'))
            .order_by('-total', 'objet_type')[:30]
        ],
    })
