"""API du lot L4 — Diplômation et documents officiels.

Pattern @api_view (cohérent avec jurys/api, equivalences/api, scolarite/api_views).
Permissions via ``graduation.permissions`` et ``authentication.role_groups``.
Lecture publique limitée au portail de vérification (AllowAny + token).
"""
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Diplome, ModeleDocument, RegistreDiplomes, Reedition
from .permissions import IsDirectionOrAdmin, IsSecretariatOrAbove, IsSecretariatOrReadOnly
from . import services


def _serialize_diplome(diplome):
    """Sérialisation REST (lecture gestion — pas le portail public)."""
    return {
        'id': diplome.id,
        'etudiant_id': diplome.etudiant_id,
        'matricule': diplome.etudiant.matricule,
        'nom_complet': diplome.etudiant.nom_complet,
        'annee_academique_id': diplome.annee_academique_id,
        'annee_academique': str(diplome.annee_academique),
        'ref_formation_id': diplome.ref_formation_id,
        'ref_formation': str(diplome.ref_formation),
        'parcours_id': diplome.parcours_id,
        'parcours': str(diplome.parcours) if diplome.parcours_id else None,
        'niveau_id': diplome.niveau_id,
        'niveau': str(diplome.niveau),
        'session_jury_id': diplome.session_jury_id,
        'decision_jury_id': diplome.decision_jury_id,
        'numero_unique': str(diplome.numero_unique),
        'mention': diplome.mention,
        'credits_acquis': diplome.credits_acquis,
        'statut': diplome.statut,
        'statut_display': diplome.get_statut_display(),
        'empreinte_pdf': diplome.empreinte_pdf,
        'pdf_disponible': bool(diplome.pdf_fichier),
        'date_creation': diplome.date_creation.isoformat() if diplome.date_creation else None,
        'date_validation': (
            diplome.date_validation.isoformat() if diplome.date_validation else None
        ),
        'date_revocation': (
            diplome.date_revocation.isoformat() if diplome.date_revocation else None
        ),
        'cree_par': str(diplome.cree_par) if diplome.cree_par_id else None,
        'valide_par': str(diplome.valide_par) if diplome.valide_par_id else None,
        'reeditions_count': diplome.reeditions.count(),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def diplomes_list_api(request):
    """Liste filtrée des diplômes (filtres : annee, formation, statut)."""
    qs = Diplome.objects.select_related(
        'etudiant__participant', 'ref_formation', 'niveau', 'parcours',
        'annee_academique', 'session_jury', 'decision_jury',
    ).order_by('-date_creation')
    annee = request.GET.get('annee_academique_id')
    if annee:
        qs = qs.filter(annee_academique_id=annee)
    formation = request.GET.get('ref_formation_id')
    if formation:
        qs = qs.filter(ref_formation_id=formation)
    statut = request.GET.get('statut')
    if statut:
        qs = qs.filter(statut=statut)
    return Response({'results': [_serialize_diplome(d) for d in qs]})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrReadOnly])
def diplome_detail_api(request, pk):
    """Détail d'un diplôme + conditions (GET) ; édition limitée à BROUILLON (PATCH)."""
    try:
        diplome = Diplome.objects.get(pk=pk)
    except Diplome.DoesNotExist:
        return Response({'error': 'Diplôme introuvable.'}, status=404)
    if request.method == 'GET':
        ok, raisons = diplome.verifier_conditions_validation()
        data = _serialize_diplome(diplome)
        data['conditions'] = {'conditions_ok': ok, 'raisons': raisons}
        return Response(data)
    if diplome.statut not in (Diplome.Statut.BROUILLON, Diplome.Statut.VALIDATION_PENDING):
        return Response(
            {'error': f"Diplôme {diplome.statut} non éditable (utilisez valider/revoquer)."},
            status=400,
        )
    for champ in ('mention', 'credits_acquis', 'decision_jury_id', 'session_jury_id'):
        if champ in request.data:
            setattr(diplome, champ, request.data[champ])
    diplome.save()
    return Response(_serialize_diplome(diplome))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def diplome_creer_api(request):
    """Crée un diplôme en BROUILLON (conditions vérifiées à la validation)."""
    champs_obligatoires = (
        'etudiant_id', 'annee_academique_id', 'ref_formation_id', 'niveau_id',
    )
    for ch in champs_obligatoires:
        if not request.data.get(ch):
            return Response({'error': f"Champ obligatoire manquant : {ch}."}, status=400)
    diplome = Diplome(
        etudiant_id=request.data['etudiant_id'],
        annee_academique_id=request.data['annee_academique_id'],
        ref_formation_id=request.data['ref_formation_id'],
        niveau_id=request.data['niveau_id'],
        parcours_id=request.data.get('parcours_id') or None,
        session_jury_id=request.data.get('session_jury_id') or None,
        decision_jury_id=request.data.get('decision_jury_id') or None,
        mention=request.data.get('mention', ''),
        credits_acquis=int(request.data.get('credits_acquis') or 0),
        cree_par=request.user,
        statut=Diplome.Statut.BROUILLON,
    )
    try:
        diplome.save()
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_diplome(diplome), status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDirectionOrAdmin])
def diplome_valider_api(request, pk):
    """Valide un diplôme (DIRECTION/DFRC/ADMIN) — PDF généré + inscription au registre."""
    try:
        diplome = Diplome.objects.get(pk=pk)
    except Diplome.DoesNotExist:
        return Response({'error': 'Diplôme introuvable.'}, status=404)
    try:
        services.valider_diplome(diplome, request.user)
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_diplome(diplome))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDirectionOrAdmin])
def diplome_revoquer_api(request, pk):
    """Révoque un diplôme VALIDATED (motif obligatoire, DIRECTION/DFRC/ADMIN)."""
    try:
        diplome = Diplome.objects.get(pk=pk)
    except Diplome.DoesNotExist:
        return Response({'error': 'Diplôme introuvable.'}, status=404)
    motif = request.data.get('motif', '').strip()
    try:
        services.revoquer_diplome(diplome, request.user, motif)
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_diplome(diplome))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDirectionOrAdmin])
def diplome_reedition_api(request, pk):
    """Crée une Réédition (append-only) du diplôme (motif obligatoire)."""
    try:
        diplome = Diplome.objects.get(pk=pk)
    except Diplome.DoesNotExist:
        return Response({'error': 'Diplôme introuvable.'}, status=404)
    motif = request.data.get('motif', '').strip()
    try:
        reedition = services.reediter_diplome(diplome, request.user, motif)
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({
        'id': reedition.id, 'motif': reedition.motif,
        'empreinte_pdf': reedition.empreinte_pdf,
        'date': reedition.date.isoformat(),
    }, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def diplome_pdf_api(request, pk):
    """Télécharge le PDF original (VALIDATED) ou de la dernière réédition."""
    try:
        diplome = Diplome.objects.get(pk=pk)
    except Diplome.DoesNotExist:
        return Response({'error': 'Diplôme introuvable.'}, status=404)
    pdf = diplome.pdf_fichier
    if not pdf:
        return Response({'error': 'Aucun PDF disponible.'}, status=404)
    with pdf.open('rb') as f:
        contenu = f.read()
    reponse = HttpResponse(contenu, content_type='application/pdf')
    reponse['Content-Disposition'] = f'attachment; filename="diplome-{diplome.pk}.pdf"'
    return reponse


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def registres_list_api(request):
    qs = RegistreDiplomes.objects.select_related('annee_academique').order_by(
        '-annee_academique__libelle'
    )
    return Response({'results': [{
        'id': r.id, 'annee_academique': str(r.annee_academique),
        'cloture': r.cloture, 'date_cloture': (
            r.date_cloture.isoformat() if r.date_cloture else None
        ),
        'diplomes_count': r.diplomes.count(),
    } for r in qs]})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def registre_detail_api(request, pk):
    try:
        r = RegistreDiplomes.objects.get(pk=pk)
    except RegistreDiplomes.DoesNotExist:
        return Response({'error': 'Registre introuvable.'}, status=404)
    if request.method == 'GET':
        return Response({
            'id': r.id, 'annee_academique': str(r.annee_academique),
            'cloture': r.cloture, 'date_cloture': (
                r.date_cloture.isoformat() if r.date_cloture else None
            ),
            'diplomes': [_serialize_diplome(d) for d in r.diplomes.all()],
        })
    # POST : clôturer le registre (action irréversible)
    r.clôturer(user=request.user)
    return Response({'id': r.id, 'cloture': r.cloture})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def modeles_list_api(request):
    qs = ModeleDocument.objects.select_related('formation').order_by('type', 'formation__libelle')
    return Response({'results': [{
        'id': m.id, 'type': m.type, 'type_display': m.get_type_display(),
        'formation_id': m.formation_id, 'formation': str(m.formation) if m.formation_id else None,
        'libelle': m.libelle, 'actif': m.actif,
        'date_modification': m.date_modification.isoformat(),
    } for m in qs]})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def modele_creer_api(request):
    for ch in ('type', 'libelle'):
        if not request.data.get(ch):
            return Response({'error': f"Champ obligatoire manquant : {ch}."}, status=400)
    if request.data['type'] not in dict(ModeleDocument.Type.choices):
        return Response({'error': "Type de document invalide."}, status=400)
    try:
        m = ModeleDocument.objects.create(
            type=request.data['type'],
            libelle=request.data['libelle'],
            formation_id=request.data.get('formation_id') or None,
            actif=bool(request.data.get('actif', True)),
            modifie_par=request.user,
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({'id': m.id, 'type': m.type, 'libelle': m.libelle}, status=201)


@api_view(['GET'])
@permission_classes([AllowAny])
def verifier_diplome_api(request, token):
    """Portail public de vérification (AllowAny — aucune donnée sensible).

    Accessible sans authentification via l'URL publique. Le token est l'UUID
    public (numero_unique) du diplôme. Ne renvoie jamais le matricule interne.
    """
    return Response(services.verifier_par_token(token))

