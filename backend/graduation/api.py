"""API du lot L4 — Diplômation et documents officiels.

Pattern @api_view (cohérent avec jurys/api, equivalences/api, scolarite/api_views).
Permissions via ``graduation.permissions`` et ``authentication.role_groups``.
Lecture publique limitée au portail de vérification (AllowAny + token).
"""
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
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




# ── Contrats OpenAPI (diplômes, registres, modèles) ──────────────────


class GraduationErreurSerializer(serializers.Serializer):
    error = serializers.JSONField()


class DiplomeReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    etudiant_id = serializers.IntegerField()
    matricule = serializers.CharField()
    nom_complet = serializers.CharField()
    annee_academique_id = serializers.IntegerField()
    annee_academique = serializers.CharField()
    ref_formation_id = serializers.IntegerField()
    ref_formation = serializers.CharField()
    parcours_id = serializers.IntegerField(allow_null=True)
    parcours = serializers.CharField(allow_null=True)
    niveau_id = serializers.IntegerField()
    niveau = serializers.CharField()
    session_jury_id = serializers.IntegerField(allow_null=True)
    decision_jury_id = serializers.IntegerField(allow_null=True)
    numero_unique = serializers.CharField()
    mention = serializers.CharField()
    credits_acquis = serializers.IntegerField()
    statut = serializers.CharField()
    statut_display = serializers.CharField()
    empreinte_pdf = serializers.CharField()
    pdf_disponible = serializers.BooleanField()
    date_creation = serializers.CharField(allow_null=True)
    date_validation = serializers.CharField(allow_null=True)
    date_revocation = serializers.CharField(allow_null=True)
    cree_par = serializers.CharField(allow_null=True)
    valide_par = serializers.CharField(allow_null=True)
    reeditions_count = serializers.IntegerField()


class DiplomesListeSerializer(serializers.Serializer):
    results = DiplomeReponseSerializer(many=True)


class ReeditionReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    motif = serializers.CharField()
    empreinte_pdf = serializers.CharField()
    date = serializers.CharField()


class ModeleCreationReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.CharField()
    libelle = serializers.CharField()


@extend_schema(responses={200: DiplomesListeSerializer})
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


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: DiplomeReponseSerializer, 400: OpenApiTypes.OBJECT, 404: GraduationErreurSerializer})
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


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: DiplomeReponseSerializer, 400: GraduationErreurSerializer})
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


@extend_schema(request=None, responses={200: DiplomeReponseSerializer, 400: OpenApiTypes.OBJECT, 404: GraduationErreurSerializer})
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


@extend_schema(request=None, responses={200: DiplomeReponseSerializer, 400: OpenApiTypes.OBJECT, 404: GraduationErreurSerializer})
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


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: ReeditionReponseSerializer, 400: OpenApiTypes.OBJECT, 404: GraduationErreurSerializer})
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


@extend_schema(responses={(200, 'application/pdf'): OpenApiTypes.BINARY, 404: GraduationErreurSerializer})
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


@extend_schema(responses={200: OpenApiTypes.OBJECT})
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


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: GraduationErreurSerializer})
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


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def modeles_list_api(request):
    # `RefFormation` nomme son champ `intitule` (il n'a jamais eu de
    # `libelle`) : trier sur `formation__libelle` levait un FieldError → 500
    # sur la liste des modèles de documents.
    qs = ModeleDocument.objects.select_related('formation').order_by('type', 'formation__intitule')
    return Response({'results': [{
        'id': m.id, 'type': m.type, 'type_display': m.get_type_display(),
        'formation_id': m.formation_id, 'formation': str(m.formation) if m.formation_id else None,
        'libelle': m.libelle, 'actif': m.actif,
        'date_modification': m.date_modification.isoformat(),
    } for m in qs]})


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: ModeleCreationReponseSerializer, 400: GraduationErreurSerializer})
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


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([AllowAny])
def verifier_diplome_api(request, token):
    """Portail public de vérification (AllowAny — aucune donnée sensible).

    Accessible sans authentification via l'URL publique. Le token est l'UUID
    public (numero_unique) du diplôme. Ne renvoie jamais le matricule interne.
    """
    return Response(services.verifier_par_token(token))



# ---------- Panorama & éligibilité (hub Diplômation — tâche 34) ----------

@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def stats_api(request):
    """Indicateurs de diplômation (aucun diplôme d'exemple n'est validé)."""
    from django.db.models import Count

    from scolarite.models import InscriptionAdministrative

    eligibles = InscriptionAdministrative.objects.filter(
        statut=InscriptionAdministrative.Statut.VALIDEE,
        niveau__code__in=('L3', 'M2'),
    ).count()
    return Response({
        'diplomes': Diplome.objects.count(),
        'par_statut': dict(
            Diplome.objects.values_list('statut')
            .annotate(n=Count('id')).order_by()
        ),
        'reeditions': Reedition.objects.count(),
        'registres': RegistreDiplomes.objects.count(),
        'registres_clotures': RegistreDiplomes.objects.filter(cloture=True).count(),
        'modeles': ModeleDocument.objects.filter(actif=True).count(),
        'etudiants_fin_cycle': eligibles,
    })


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrAbove])
def eligibles_api(request):
    """Étudiants en fin de cycle et leur état d'éligibilité factuel.

    Ne décide rien : indique, pour chaque inscription validée de L3/M2, si
    une décision de jury existe et si un diplôme a été préparé/validé.
    """
    from scolarite.models import AnneeAcademique, InscriptionAdministrative

    annee_id = request.GET.get('annee_academique_id')
    qs = (
        InscriptionAdministrative.objects.select_related(
            'etudiant__participant', 'ref_formation', 'niveau',
        )
        .filter(
            statut=InscriptionAdministrative.Statut.VALIDEE,
            niveau__code__in=('L3', 'M2'),
        )
        .order_by('ref_formation__intitule', 'etudiant__participant__nom')
    )
    if annee_id:
        qs = qs.filter(annee_academique_id=annee_id)
    else:
        courante = AnneeAcademique.objects.filter(courante=True).first()
        if courante:
            qs = qs.filter(annee_academique=courante)
    diplomes = {
        (d.etudiant_id, d.ref_formation_id, d.niveau_id): d
        for d in Diplome.objects.filter(
            annee_academique_id__in=qs.values('annee_academique_id'),
        )
    }
    results = []
    for ia in qs:
        diplome = diplomes.get((ia.etudiant_id, ia.ref_formation_id, ia.niveau_id))
        decision_ok = bool(diplome and diplome.decision_jury_id)
        results.append({
            'id': ia.id,
            'etudiant_id': ia.etudiant_id,
            'matricule': ia.etudiant.participant.matricule,
            'nom_complet': ia.etudiant.nom_complet,
            'formation': ia.ref_formation.intitule,
            'niveau': ia.niveau.code,
            'decision_jury': decision_ok,
            'diplome_statut': diplome.statut if diplome else None,
            'diplome_statut_display': (
                diplome.get_statut_display() if diplome else None
            ),
            'etat': (
                'Diplôme validé' if diplome and diplome.statut == 'VALIDATED'
                else 'Diplôme préparé' if diplome
                else 'Décision de jury disponible' if decision_ok
                else 'En attente du jury'
            ),
        })
    return Response({'results': results})
