"""API du lot L7 — Patrimoine.

Pattern @api_view. Espaces référencés via formations.RefSalle (source unique).
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from formations.models import RefSalle

from . import services
from .models import Equipement, Inventaire, Maintenance, MouvementPatrimonial, ReservationEspace, Vehicule
from .permissions import IsGestionPatrimoine, IsGestionPatrimoineOrReadOnly, IsValidationPatrimoine


def _serialize_equipement(e):
    return {
        'id': e.id, 'nom': e.nom, 'type_equipement': e.type_equipement,
        'type_equipement_display': e.get_type_equipement_display(),
        'marque': e.marque, 'modele': e.modele, 'num_serie': e.num_serie,
        'etat': e.etat, 'etat_display': e.get_etat_display(),
        'salle_id': e.espace_id,
        'salle': str(e.espace) if e.espace_id else None,
        'date_acquisition': e.date_acquisition.isoformat() if e.date_acquisition else None,
    }


def _serialize_vehicule(v):
    return {
        'id': v.id, 'immatriculation': v.immatriculation, 'marque': v.marque,
        'modele': v.modele, 'annee_mise_en_circulation': v.annee_mise_en_circulation,
        'kilometrage': v.kilometrage,
        'prochaine_revision': v.prochaine_revision.isoformat() if v.prochaine_revision else None,
    }


def _serialize_maintenance(m):
    return {
        'id': m.id, 'equipement_id': m.equipement_id,
        'equipement': str(m.equipement) if m.equipement_id else None,
        'salle_id': m.salle_id, 'salle': str(m.salle) if m.salle_id else None,
        'type_maintenance': m.type_maintenance,
        'type_maintenance_display': m.get_type_maintenance_display(),
        'description': m.description,
        'date_debut': m.date_debut.isoformat(),
        'date_fin': m.date_fin.isoformat() if m.date_fin else None,
        'statut': m.statut, 'statut_display': m.get_statut_display(),
    }


def _serialize_reservation(r):
    return {
        'id': r.id, 'salle_id': r.salle_id, 'salle': str(r.salle),
        'motif': r.motif,
        'date_debut': r.date_debut.isoformat(), 'date_fin': r.date_fin.isoformat(),
        'statut': r.statut, 'statut_display': r.get_statut_display(),
        'demande_par': str(r.demande_par) if r.demande_par_id else None,
        'valide_par': str(r.valide_par) if r.valide_par_id else None,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionPatrimoineOrReadOnly])
def equipements_api(request):
    if request.method == 'GET':
        qs = Equipement.objects.select_related('espace').order_by('nom')
        etat = request.GET.get('etat')
        if etat:
            qs = qs.filter(etat=etat)
        return Response({'results': [_serialize_equipement(e) for e in qs]})
    if not request.data.get('nom'):
        return Response({'error': 'Le nom est obligatoire.'}, status=400)
    try:
        e = Equipement.objects.create(
            espace_id=request.data.get('salle_id'),
            nom=request.data['nom'],
            type_equipement=request.data.get('type_equipement', Equipement.TypeEquipement.AUTRE),
            marque=request.data.get('marque', ''),
            modele=request.data.get('modele', ''),
            num_serie=request.data.get('num_serie', ''),
            cree_par=request.user,
        )
        services.tracer_mouvement(
            MouvementPatrimonial.TypeMouvement.ACQUISITION,
            equipement=e, acteur=request.user, detail=f'Acquisition {e.nom}',
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_equipement(e), status=201)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionPatrimoineOrReadOnly])
def vehicules_api(request):
    if request.method == 'GET':
        qs = Vehicule.objects.all().order_by('immatriculation')
        return Response({'results': [_serialize_vehicule(v) for v in qs]})
    if not request.data.get('immatriculation'):
        return Response({'error': "L'immatriculation est obligatoire."}, status=400)
    try:
        v = Vehicule.objects.create(
            immatriculation=request.data['immatriculation'],
            marque=request.data.get('marque', ''),
            modele=request.data.get('modele', ''),
            kilometrage=request.data.get('kilometrage', 0),
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionPatrimoineOrReadOnly])
def inventaires_api(request):
    if request.method == 'GET':
        qs = Inventaire.objects.all().order_by('-date_inventaire')
        return Response({'results': [
            {'id': i.id, 'date_inventaire': i.date_inventaire.isoformat(),
             'responsable': str(i.responsable) if i.responsable_id else None,
             'commentaires': i.commentaires}
            for i in qs
        ]})
    if not request.data.get('date_inventaire'):
        return Response({'error': 'La date d’inventaire est obligatoire.'}, status=400)
    try:
        inv = Inventaire.objects.create(
            date_inventaire=request.data['date_inventaire'],
            responsable=request.user,
            commentaires=request.data.get('commentaires', ''),
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({'id': inv.id, 'date_inventaire': inv.date_inventaire.isoformat()}, status=201)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionPatrimoineOrReadOnly])
def maintenances_api(request):
    if request.method == 'GET':
        qs = Maintenance.objects.select_related('equipement', 'salle').order_by('-date_debut')
        statut = request.GET.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        return Response({'results': [_serialize_maintenance(m) for m in qs]})
    for ch in ('description', 'date_debut'):
        if not request.data.get(ch):
            return Response({'error': f'Champ obligatoire manquant : {ch}.'}, status=400)
    try:
        m = Maintenance.objects.create(
            equipement_id=request.data.get('equipement_id'),
            salle_id=request.data.get('salle_id'),
            type_maintenance=request.data.get('type_maintenance', Maintenance.TypeMaintenance.CORRECTIVE),
            description=request.data['description'],
            date_debut=request.data['date_debut'],
            date_fin=request.data.get('date_fin'),
            responsable=request.user,
        )
        m.full_clean()
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_maintenance(m), status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsGestionPatrimoine])
def maintenance_transition_api(request, pk):
    try:
        m = Maintenance.objects.get(pk=pk)
    except Maintenance.DoesNotExist:
        return Response({'error': 'Maintenance introuvable.'}, status=404)
    statut = request.data.get('statut')
    try:
        services.transitionner_maintenance(m, statut, acteur=request.user)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_maintenance(m))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionPatrimoineOrReadOnly])
def reservations_api(request):
    if request.method == 'GET':
        qs = ReservationEspace.objects.select_related('salle').order_by('-date_debut')
        statut = request.GET.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        return Response({'results': [_serialize_reservation(r) for r in qs]})
    salle_id = request.data.get('salle_id')
    for ch in ('motif', 'date_debut', 'date_fin'):
        if not request.data.get(ch):
            return Response({'error': f'Champ obligatoire manquant : {ch}.'}, status=400)
    if not salle_id:
        return Response({'error': 'salle_id est requis.'}, status=400)
    try:
        r = ReservationEspace.objects.create(
            salle_id=salle_id,
            motif=request.data['motif'],
            date_debut=request.data['date_debut'],
            date_fin=request.data['date_fin'],
            demande_par=request.user,
        )
        r.full_clean()
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_reservation(r), status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsValidationPatrimoine])
def reservation_valider_api(request, pk):
    try:
        r = ReservationEspace.objects.get(pk=pk)
    except ReservationEspace.DoesNotExist:
        return Response({'error': 'Réservation introuvable.'}, status=404)
    statut = request.data.get('statut', ReservationEspace.Statut.VALIDEE)
    try:
        services.valider_reservation(r, valide_par=request.user, statut=statut, acteur=request.user)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_reservation(r))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mouvements_api(request):
    qs = MouvementPatrimonial.objects.select_related('equipement', 'vehicule', 'acteur').order_by('-created_at')
    type_mouvement = request.GET.get('type')
    if type_mouvement:
        qs = qs.filter(type_mouvement=type_mouvement)
    return Response({'results': [
        {'id': m.id, 'type_mouvement': m.type_mouvement,
         'type_mouvement_display': m.get_type_mouvement_display(),
         'equipement': str(m.equipement) if m.equipement_id else None,
         'vehicule': m.vehicule.immatriculation if m.vehicule_id else None,
         'detail': m.detail, 'acteur': str(m.acteur) if m.acteur_id else None,
         'created_at': m.created_at.isoformat()}
        for m in qs
    ]})
    return Response(_serialize_vehicule(v), status=201)