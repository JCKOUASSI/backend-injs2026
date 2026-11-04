"""API d'interopérabilité GET-INJS → futur module Présences.

Préfixe : ``/api/edts/interop/`` (alias ``/api/timetable/interop/``).

Contrat stable exposé au futur module de gestion des présences :

- ``GET  seances-publiees/`` : séances officiellement exploitables
  (PUBLIEE / MODIFIEE), filtrables et paginées ;
- ``GET  seances/<uuid>/`` : détail complet d'une séance par son identité
  permanente (contexte LMD retrouvé par relations, géolocalisation de la
  salle, 10 dernières traces d'historique) ;
- ``GET  seances/<uuid>/etudiants-attendus/`` : étudiants théoriquement
  attendus, calculés depuis les affectations de groupe actives ;
- ``POST seances/<uuid>/instantane/`` : fige un instantané des attendus
  (planification uniquement) ;
- ``POST seances/<uuid>/transition/`` : transition de cycle de vie tracée
  (planification ; validation/publication/clôture réservées DIRECTION et
  ADMIN, comme la publication des emplois du temps) ;
- ``POST emplois/<id>/reconcilier/`` : assure un registre par séance de
  l'emploi du temps (et publie les registres si l'EDT est PUBLIÉ) ;
- ``GET  salles-geolocalisation/`` : salles et configurations géographiques ;
- ``GET  evenements/?apres=<id>`` : file des événements contractuels
  (SEANCE_PUBLIEE, SEANCE_MODIFIEE, SEANCE_ANNULEE, SEANCE_REPROGRAMMEE,
  SEANCE_CLOTUREE) à consommer par le futur module.

Aucun pointage n'est accepté ici : GET reste la source des séances,
jamais le moteur de présence.
"""

from datetime import date

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import EmploiDuTemps
from .models_interop import (
    SalleGeolocalisation,
    SeanceEvenement,
    SeanceRegistre,
)
from .moteur import interop_presences as svc
from .permissions import IsEdtPlanification, _peut_valider

STATUTS_RESERVES_VALIDATION = {
    SeanceRegistre.Statut.VALIDEE,
    SeanceRegistre.Statut.PUBLIEE,
    SeanceRegistre.Statut.TERMINEE,
}


def _paginer(request, elements):
    """Pagination explicite et bornée (jamais de liste non maîtrisée)."""
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        taille = int(request.query_params.get('page_size', 50))
    except (TypeError, ValueError):
        taille = 50
    taille = min(100, max(1, taille))
    total = len(elements)
    debut = (page - 1) * taille
    return {
        'count': total,
        'page': page,
        'page_size': taille,
        'results': elements[debut:debut + taille],
    }


def _registre_ou_404(uuid):
    return SeanceRegistre.objects.select_related(
        'affectation__emploi_du_temps__annee_academique',
        'affectation__creneau_template',
        'affectation__affectation_pedagogique__ref_formation',
        'affectation__affectation_pedagogique__niveau',
        'affectation__affectation_pedagogique__semestre',
        'affectation__affectation_pedagogique__ue',
        'affectation__affectation_pedagogique__ecue',
        'affectation__affectation_pedagogique__enseignant',
        'affectation__salle',
        'seance_origine',
    ).filter(uuid=uuid).first()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seances_publiees_api(request):
    """Séances officiellement publiées, exploitables par les présences."""
    registres = (
        SeanceRegistre.objects
        .filter(statut__in=svc.STATUTS_EXPLOITABLES_PRESENCE)
        .select_related('affectation')
        .order_by('id')
    )
    annee = request.query_params.get('annee')
    if annee:
        registres = registres.filter(
            affectation__emploi_du_temps__annee_academique__libelle=annee,
        )
    groupe = request.query_params.get('groupe')
    if groupe:
        registres = registres.filter(affectation__groupe_id=groupe)
    formation = request.query_params.get('formation')
    if formation:
        registres = registres.filter(
            affectation__affectation_pedagogique__ref_formation_id=formation,
        )
    elements = [svc.contexte_seance(r) for r in registres]
    return Response(_paginer(request, elements))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seance_detail_api(request, uuid):
    registre = _registre_ou_404(uuid)
    if registre is None:
        return Response({'error': 'Séance introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    payload = svc.contexte_seance(registre)
    payload['historique'] = [
        {
            'action': h.action,
            'statut_avant': h.statut_avant,
            'statut_apres': h.statut_apres,
            'motif': h.motif,
            'horodatage': h.horodatage.isoformat(),
        }
        for h in registre.historique.all()[:10]
    ]
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seance_etudiants_attendus_api(request, uuid):
    registre = _registre_ou_404(uuid)
    if registre is None:
        return Response({'error': 'Séance introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    if registre.affectation is None:
        return Response(
            {'error': 'Séance sans placement courant : attendus non calculables.'},
            status=status.HTTP_409_CONFLICT,
        )
    date_seance = None
    brut = request.query_params.get('date')
    if brut:
        try:
            date_seance = date.fromisoformat(brut)
        except ValueError:
            return Response(
                {'error': 'Paramètre date invalide (AAAA-MM-JJ attendu).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
    attendus = svc.etudiants_attendus(registre.affectation, date_seance=date_seance)
    attendus['seance_uuid'] = str(registre.uuid)
    attendus['peut_ouvrir_session_presence'] = svc.peut_ouvrir_session_presence(registre)
    return Response(attendus)


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def seance_instantane_api(request, uuid):
    registre = _registre_ou_404(uuid)
    if registre is None:
        return Response({'error': 'Séance introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    date_seance = None
    brut = (request.data or {}).get('date_seance')
    if brut:
        try:
            date_seance = date.fromisoformat(str(brut))
        except ValueError:
            return Response(
                {'error': 'date_seance invalide (AAAA-MM-JJ attendu).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
    try:
        instantane = svc.creer_instantane(
            registre, acteur=request.user, date_seance=date_seance,
        )
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(
        {
            'instantane_id': instantane.id,
            'seance_uuid': str(registre.uuid),
            'effectif': instantane.effectif,
            'base_calculee': instantane.base_calculee,
            'cree_le': instantane.cree_le.isoformat(),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def seance_transition_api(request, uuid):
    registre = _registre_ou_404(uuid)
    if registre is None:
        return Response({'error': 'Séance introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    nouveau = (request.data or {}).get('statut')
    if nouveau not in dict(SeanceRegistre.Statut.choices):
        return Response(
            {'error': 'Statut inconnu.', 'statuts': list(dict(SeanceRegistre.Statut.choices))},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if nouveau in STATUTS_RESERVES_VALIDATION and not _peut_valider(request.user):
        return Response(
            {'error': 'Validation, publication et clôture sont réservées à DIRECTION et ADMIN.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    try:
        registre = svc.transitionner(
            registre, nouveau, acteur=request.user,
            motif=(request.data or {}).get('motif', ''),
        )
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(svc.contexte_seance(registre))


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def emploi_reconcilier_api(request, pk):
    emploi = EmploiDuTemps.objects.filter(pk=pk).first()
    if emploi is None:
        return Response(
            {'error': 'Emploi du temps introuvable.'}, status=status.HTTP_404_NOT_FOUND,
        )
    bilan = svc.reconcilier_emploi_du_temps(emploi, acteur=request.user)
    return Response({'emploi_du_temps_id': emploi.id, **bilan})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def salles_geolocalisation_api(request):
    """Salles du référentiel et leur configuration géographique éventuelle."""
    from formations.models import RefSalle

    configs = {
        c.salle_id: c for c in SalleGeolocalisation.objects.all()
    }
    elements = []
    for salle in RefSalle.objects.order_by('nom'):
        geo = configs.get(salle.id)
        elements.append({
            'salle_id': salle.id,
            'nom': salle.nom,
            'capacite': salle.capacite,
            'geolocalisation': {
                'latitude': str(geo.latitude) if geo and geo.latitude is not None else None,
                'longitude': str(geo.longitude) if geo and geo.longitude is not None else None,
                'rayon_tolerance_m': geo.rayon_tolerance_m if geo else None,
                'zone_libelle': geo.zone_libelle if geo else '',
                'type_espace': geo.type_espace if geo else None,
                'statut_configuration': (
                    geo.statut_configuration if geo else 'NON_CONFIGUREE'
                ),
                'coordonnees_disponibles': bool(geo and geo.coordonnees_disponibles),
            },
        })
    return Response(_paginer(request, elements))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def evenements_api(request):
    """File des événements contractuels (consommation par le futur module)."""
    evenements = SeanceEvenement.objects.select_related('registre').order_by('id')
    apres = request.query_params.get('apres')
    if apres:
        try:
            evenements = evenements.filter(id__gt=int(apres))
        except (TypeError, ValueError):
            return Response(
                {'error': 'Paramètre apres invalide (entier attendu).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
    if request.query_params.get('non_consommes') in ('1', 'true'):
        evenements = evenements.filter(consomme=False)
    elements = [
        {
            'id': e.id,
            'type': e.type,
            'seance_uuid': str(e.registre.uuid),
            'charge_utile': e.charge_utile,
            'consomme': e.consomme,
            'cree_le': e.cree_le.isoformat(),
        }
        for e in evenements[:200]
    ]
    return Response({'count': len(elements), 'results': elements})
