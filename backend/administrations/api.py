"""API du lot L7 — Administration générale.

Pattern @api_view (cohérent avec stages/jurys/graduation).
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Courrier, DocumentOfficiel, Mission, ReunionCommission
from .permissions import IsGestionOrReadOnly, IsGestionAdministration, IsDirectionOrAdminAdministration


def _serialize_courrier(c):
    return {
        'id': c.id, 'sens': c.sens, 'sens_display': c.get_sens_display(),
        'reference': c.reference, 'objet': c.objet,
        'expediteur': c.expediteur, 'destinataire': c.destinataire,
        'date_courrier': c.date_courrier.isoformat() if c.date_courrier else None,
        'statut': c.statut, 'statut_display': c.get_statut_display(),
        'fichier_url': c.fichier.url if c.fichier else None,
        'created_at': c.created_at.isoformat(),
    }


def _serialize_document(d):
    return {
        'id': d.id, 'type_document': d.type_document,
        'type_document_display': d.get_type_document_display(),
        'reference': d.reference, 'titre': d.titre, 'contenu': d.contenu,
        'statut': d.statut, 'statut_display': d.get_statut_display(),
        'document_pdf_url': d.document_pdf.url if d.document_pdf else None,
        'signe_par': str(d.signe_par) if d.signe_par_id else None,
        'date_signature': d.date_signature.isoformat() if d.date_signature else None,
        'versions': [
            {'numero': v.numero_version, 'contenu': v.contenu,
             'created_at': v.created_at.isoformat()}
            for v in d.versions.all()
        ],
    }


# ---------- Courriers ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def courriers_list_api(request):
    qs = Courrier.objects.all().select_related('cree_par').order_by('-created_at')
    sens = request.GET.get('sens')
    statut = request.GET.get('statut')
    if sens in ('ENTRANT', 'SORTANT'):
        qs = qs.filter(sens=sens)
    if statut:
        qs = qs.filter(statut=statut)
    return Response({'results': [_serialize_courrier(c) for c in qs]})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsGestionAdministration])
def courrier_creer_api(request):
    for ch in ('reference', 'objet'):
        if not request.data.get(ch):
            return Response({'error': f'Champ obligatoire manquant : {ch}.'}, status=400)
    try:
        c = Courrier.objects.create(
            sens=request.data.get('sens', Courrier.Sens.ENTRANT),
            reference=request.data['reference'],
            objet=request.data['objet'],
            expediteur=request.data.get('expediteur', ''),
            destinataire=request.data.get('destinataire', ''),
            cree_par=request.user,
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_courrier(c), status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsGestionAdministration])
def courrier_transition_api(request, pk):
    try:
        c = Courrier.objects.get(pk=pk)
    except Courrier.DoesNotExist:
        return Response({'error': 'Courrier introuvable.'}, status=404)
    statut = request.data.get('statut')
    if not statut:
        return Response({'error': 'Statut manquant.'}, status=400)
    try:
        services.transitionner_courrier(c, statut, acteur=request.user)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_courrier(c))


# ---------- Documents officiels ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def documents_list_api(request):
    qs = DocumentOfficiel.objects.all().select_related('signe_par', 'cree_par').order_by('-created_at')
    statut = request.GET.get('statut')
    if statut:
        qs = qs.filter(statut=statut)
    return Response({'results': [_serialize_document(d) for d in qs]})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsGestionAdministration])
def document_creer_api(request):
    if not request.data.get('titre'):
        return Response({'error': 'Le titre est obligatoire.'}, status=400)
    try:
        d = DocumentOfficiel.objects.create(
            type_document=request.data.get('type_document', DocumentOfficiel.Type.NOTE_SERVICE),
            reference=request.data.get('reference', ''),
            titre=request.data['titre'],
            contenu=request.data.get('contenu', ''),
            cree_par=request.user,
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_document(d), status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsGestionAdministration])
def document_transition_api(request, pk):
    try:
        d = DocumentOfficiel.objects.get(pk=pk)
    except DocumentOfficiel.DoesNotExist:
        return Response({'error': 'Document introuvable.'}, status=404)
    action = request.data.get('action')
    if action == 'versionner':
        try:
            services.creer_version_document(d, contenu=request.data.get('contenu', ''), acteur=request.user)
        except Exception as exc:
            return Response({'error': str(exc)}, status=400)
    elif action == 'signer':
        try:
            services.valider_document(d, acteur=request.user)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
    else:
        statut = request.data.get('statut')
        if not statut:
            return Response({'error': 'Action ou statut manquant.'}, status=400)
        try:
            services.transitionner_document(d, statut, acteur=request.user)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
def _serialize_reunion(r):
    return {
        'id': r.id, 'type_reunion': r.type_reunion, 'titre': r.titre,
        'date_reunion': r.date_reunion.isoformat(),
        'lieu': r.lieu, 'ordre_du_jour': r.ordre_du_jour,
        'statut': r.statut, 'statut_display': r.get_statut_display(),
        'pv_contenu': r.pv_contenu,
        'participants': [str(p) for p in r.participants.all()],
    }


def _serialize_mission(m):
    return {
        'id': m.id, 'objet': m.objet, 'lieu': m.lieu,
        'date_debut': m.date_debut.isoformat(), 'date_fin': m.date_fin.isoformat(),
        'statut': m.statut, 'statut_display': m.get_statut_display(),
        'budget': float(m.budget), 'motif_refus': m.motif_refus,
        'valide_par': str(m.valide_par) if m.valide_par_id else None,
    }


# ---------- Réunions ----------

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionOrReadOnly])
def reunions_api(request):
    if request.method == 'GET':
        qs = ReunionCommission.objects.all().order_by('-date_reunion')
        return Response({'results': [_serialize_reunion(r) for r in qs]})
    for ch in ('titre', 'date_reunion', 'type_reunion'):
        if not request.data.get(ch):
            return Response({'error': f'Champ obligatoire manquant : {ch}.'}, status=400)
    try:
        r = ReunionCommission.objects.create(
            titre=request.data['titre'], type_reunion=request.data['type_reunion'],
            date_reunion=request.data['date_reunion'],
            lieu=request.data.get('lieu', ''),
            ordre_du_jour=request.data.get('ordre_du_jour', ''),
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_reunion(r), status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsGestionAdministration])
def reunion_transition_api(request, pk):
    try:
        r = ReunionCommission.objects.get(pk=pk)
    except ReunionCommission.DoesNotExist:
        return Response({'error': 'Réunion introuvable.'}, status=404)
    statut = request.data.get('statut')
    pv_contenu = request.data.get('pv_contenu', '')
    if statut == ReunionCommission.Statut.PV_EMIS and pv_contenu:
        r.pv_contenu = pv_contenu
        r.save(update_fields=['pv_contenu'])
    try:
        services.transitionner_reunion(r, statut, acteur=request.user)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_reunion(r))


# ---------- Missions ----------

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsGestionOrReadOnly])
def missions_api(request):
    if request.method == 'GET':
        qs = Mission.objects.all().order_by('-date_debut')
        statut = request.GET.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        return Response({'results': [_serialize_mission(m) for m in qs]})
    for ch in ('objet', 'lieu', 'date_debut', 'date_fin'):
        if not request.data.get(ch):
            return Response({'error': f'Champ obligatoire manquant : {ch}.'}, status=400)
    try:
        m = Mission.objects.create(
            agent=request.user, objet=request.data['objet'], lieu=request.data['lieu'],
            date_debut=request.data['date_debut'], date_fin=request.data['date_fin'],
            budget=request.data.get('budget', 0),
        )
        m.full_clean()
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_mission(m), status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDirectionOrAdminAdministration])
def mission_transition_api(request, pk):
    try:
        m = Mission.objects.get(pk=pk)
    except Mission.DoesNotExist:
        return Response({'error': 'Mission introuvable.'}, status=404)
    statut = request.data.get('statut')
    try:
        services.transitionner_mission(
            m, statut, acteur=request.user, motif_refus=request.data.get('motif_refus', ''),
        )
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_mission(m))
    return Response(_serialize_document(d))