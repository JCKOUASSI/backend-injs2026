"""API du lot L7 — Ressources Humaines.

Pattern @api_view. NB : la paie formateurs (modèle formations) n'est pas
impactée — ce module couvre le personnel administratif et technique.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Agent, DisponibiliteAgent, DocumentRH, Fonction, Service
from .permissions import IsConsultationRH, IsGestionRH, IsGestionRHOrReadOnly


def _serialize_service(s):
    return {'id': s.id, 'nom': s.nom, 'description': s.description, 'actif': s.actif}


def _serialize_fonction(f):
    return {'id': f.id, 'intitule': f.intitule, 'service_id': f.service_id,
            'service_nom': f.service.nom, 'grade': f.grade, 'actif': f.actif}


def _serialize_agent(a):
    return {
        'id': a.id, 'matricule': a.matricule, 'nom': a.nom, 'prenom': a.prenom,
        'email': a.email, 'telephone': a.telephone,
        'type_contrat': a.type_contrat,
        'type_contrat_display': a.get_type_contrat_display(),
        'statut': a.statut, 'statut_display': a.get_statut_display(),
        'date_entree': a.date_entree.isoformat() if a.date_entree else None,
        'date_sortie': a.date_sortie.isoformat() if a.date_sortie else None,
        'affectations': [
            {'fonction': af.fonction.intitule,
             'service': af.fonction.service.nom,
             'date_debut': af.date_debut.isoformat(),
             'date_fin': af.date_fin.isoformat() if af.date_fin else None}
            for af in a.affectations.select_related('fonction__service').order_by('-date_debut')
        ],
    }


def _serialize_indispo(d):
    return {
        'id': d.id, 'agent_id': d.agent_id, 'agent': str(d.agent),
        'type_indispo': d.type_indispo,
        'type_indispo_display': d.get_type_indispo_display(),
        'motif': d.motif,
        'date_debut': d.date_debut.isoformat(), 'date_fin': d.date_fin.isoformat(),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def services_api(request):
    qs = Service.objects.filter(actif=True).order_by('nom')
    return Response({'results': [_serialize_service(s) for s in qs]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fonctions_api(request):
    qs = Fonction.objects.select_related('service').filter(actif=True).order_by('intitule')
    service_id = request.GET.get('service_id')
    if service_id:
        qs = qs.filter(service_id=service_id)
    return Response({'results': [_serialize_fonction(f) for f in qs]})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionRHOrReadOnly])
def agents_api(request):
    if request.method == 'GET':
        qs = Agent.objects.all().order_by('nom')
        statut = request.GET.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        return Response({'results': [_serialize_agent(a) for a in qs]})
    for ch in ('matricule', 'nom'):
        if not request.data.get(ch):
            return Response({'error': f'Champ obligatoire manquant : {ch}.'}, status=400)
    try:
        agent = services.creer_agent(
            matricule=request.data['matricule'], nom=request.data['nom'],
            prenom=request.data.get('prenom', ''),
            email=request.data.get('email', ''),
            telephone=request.data.get('telephone', ''),
            type_contrat=request.data.get('type_contrat', Agent.TypeContrat.CONTRAT),
            acteur=request.user,
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsConsultationRH])
def agent_detail_api(request, pk):
    try:
        a = Agent.objects.prefetch_related('affectations__fonction__service').get(pk=pk)
    except Agent.DoesNotExist:
        return Response({'error': 'Agent introuvable.'}, status=404)
    return Response(_serialize_agent(a))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsGestionRH])
def agent_affecter_api(request, pk):
    try:
        agent = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist:
        return Response({'error': 'Agent introuvable.'}, status=404)
    fonction_id = request.data.get('fonction_id')
    date_debut = request.data.get('date_debut')
    if not fonction_id or not date_debut:
        return Response({'error': 'fonction_id et date_debut sont requis.'}, status=400)
    try:
        fonction = Fonction.objects.get(pk=fonction_id)
        aff = services.affecter_agent(
            agent, fonction, date_debut, acteur=request.user,
            date_fin=request.data.get('date_fin'),
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({'id': aff.id, 'agent': str(agent), 'fonction': str(fonction)})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionRHOrReadOnly])
def agent_disponibilites_api(request, pk):
    if request.method == 'GET':
        qs = DisponibiliteAgent.objects.filter(agent_id=pk).order_by('-date_debut')
        return Response({'results': [_serialize_indispo(d) for d in qs]})
    for ch in ('date_debut', 'date_fin'):
        if not request.data.get(ch):
            return Response({'error': f'Champ obligatoire manquant : {ch}.'}, status=400)
    try:
        agent = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist:
        return Response({'error': 'Agent introuvable.'}, status=404)
    try:
        dispo = services.ajouter_indisponibilite(
            agent,
            type_indispo=request.data.get('type_indispo', DisponibiliteAgent.TypeIndispo.CONGE),
            date_debut=request.data['date_debut'],
            date_fin=request.data['date_fin'],
            acteur=request.user, motif=request.data.get('motif', ''),
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_indispo(dispo), status=201)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionRHOrReadOnly])
def documents_rh_api(request):
    if request.method == 'GET':
        qs = DocumentRH.objects.all().order_by('-created_at')
        agent_id = request.GET.get('agent_id')
        if agent_id:
            qs = qs.filter(agent_id=agent_id)
        return Response({'results': [
            {'id': d.id, 'agent_id': d.agent_id, 'agent': str(d.agent),
             'type_document': d.type_document,
             'type_document_display': d.get_type_document_display(),
             'intitule': d.intitule, 'fichier_url': d.fichier.url if d.fichier else None,
             'created_at': d.created_at.isoformat()}
            for d in qs
        ]})
    for ch in ('agent_id', 'intitule'):
        if not request.data.get(ch):
            return Response({'error': f'Champ obligatoire manquant : {ch}.'}, status=400)
    try:
        doc = DocumentRH.objects.create(
            agent_id=request.data['agent_id'],
            intitule=request.data['intitule'],
            type_document=request.data.get('type_document', DocumentRH.TypeDocument.CONTRAT),
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({'id': doc.id, 'agent': str(doc.agent), 'intitule': doc.intitule}, status=201)
    return Response(_serialize_agent(agent), status=201)