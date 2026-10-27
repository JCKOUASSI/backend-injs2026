"""API des référentiels LMD et de la maquette pédagogique.

Suit les conventions du projet : vues fonctions ``@api_view``, routes ``path()``
explicites, filtrage manuel via ``request.query_params``.
"""

from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsDFRC, IsSecretariatOrDFRC

from .models import (
    AnneeAcademique,
    ECUE,
    Groupe,
    Maquette,
    MaquetteJournal,
    Niveau,
    Parcours,
    RegimeEtudes,
    Semestre,
    StatutEtudiant,
    TypeFormation,
    UE,
)
from formations.models import RefFormation, RefModule, RefSalle

# Champs exposés et acceptés en écriture pour chaque référentiel simple.
REFERENTIEL_FIELDS = {
    'annees': (AnneeAcademique, ['id', 'libelle', 'date_debut', 'date_fin', 'courante', 'actif']),
    'types-formation': (TypeFormation, ['id', 'code', 'libelle', 'actif']),
    'niveaux': (Niveau, ['id', 'code', 'libelle', 'cycle', 'ordre', 'credits_requis', 'actif']),
    'semestres': (Semestre, ['id', 'niveau_id', 'numero', 'libelle', 'actif']),
    'regimes': (RegimeEtudes, ['id', 'code', 'libelle', 'actif']),
    'statuts-etudiant': (StatutEtudiant, ['id', 'code', 'libelle', 'bloque_inscription', 'actif']),
    'parcours': (Parcours, ['id', 'ref_formation_id', 'type_formation_id', 'code', 'intitule', 'actif']),
    'groupes': (Groupe, [
        'id', 'annee_academique_id', 'ref_formation_id', 'parcours_id', 'niveau_id',
        'vague_id', 'site_id', 'nom', 'capacite_max', 'actif',
    ]),
    'formations': (RefFormation, ['id', 'code', 'intitule', 'type_diplome', 'domaine', 'mention', 'actif']),
    'salles': (RefSalle, ['id', 'site_id', 'nom', 'capacite', 'type_lieu', 'actif']),
}

# Filtres exacts autorisés par référentiel, pour éviter toute injection de lookup.
REFERENTIEL_FILTERS = {
    'semestres': ['niveau_id', 'actif'],
    'parcours': ['ref_formation_id', 'type_formation_id', 'actif'],
    'groupes': [
        'annee_academique_id', 'ref_formation_id', 'parcours_id', 'niveau_id',
        'vague_id', 'site_id', 'actif',
    ],
    'annees': ['courante', 'actif'],
    'niveaux': ['cycle', 'actif'],
    'types-formation': ['actif'],
    'regimes': ['actif'],
    'statuts-etudiant': ['actif'],
    'formations': ['actif'],
    'salles': ['actif'],
}

_BOOLEAN_TRUE = {'1', 'true', 'True', 'oui'}
_BOOLEAN_FALSE = {'0', 'false', 'False', 'non'}


def _coerce(value):
    """Convertit les valeurs de query string en type Python exploitable par l'ORM."""
    if value in _BOOLEAN_TRUE:
        return True
    if value in _BOOLEAN_FALSE:
        return False
    return value


def _apply_filters(queryset, ressource, query_params):
    for champ in REFERENTIEL_FILTERS.get(ressource, []):
        if champ in query_params:
            queryset = queryset.filter(**{champ: _coerce(query_params[champ])})
    return queryset


def _payload_for_write(fields, data):
    """Construit le dictionnaire d'attributs à écrire, en ignorant les champs absents."""
    valeurs = {}
    for champ in fields:
        if champ == 'id' or champ not in data:
            continue
        valeur = data[champ]
        valeurs[champ] = None if valeur == '' and champ.endswith('_id') else valeur
    return valeurs


def _valider(obj):
    """Valide l'objet et renvoie une réponse 400 exploitable par formatApiErrors côté frontend."""
    try:
        obj.full_clean()
    except ValidationError as erreur:
        return Response(erreur.message_dict, status=400)
    return None


def _referentiel_list(request, ressource):
    model, fields = REFERENTIEL_FIELDS[ressource]
    if request.method == 'GET':
        queryset = _apply_filters(model.objects.all(), ressource, request.query_params)
        return Response(list(queryset.values(*fields)))
    obj = model(**_payload_for_write(fields, request.data))
    erreur = _valider(obj)
    if erreur is not None:
        return erreur
    obj.save()
    return Response(model.objects.filter(pk=obj.pk).values(*fields).first(), status=201)


def _referentiel_detail(request, ressource, pk):
    model, fields = REFERENTIEL_FIELDS[ressource]
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'DELETE':
        try:
            obj.delete()
        except ProtectedError:
            return Response(
                {'error': "Suppression impossible : cet élément est référencé ailleurs."},
                status=409,
            )
        return Response(status=204)
    for champ, valeur in _payload_for_write(fields, request.data).items():
        setattr(obj, champ, valeur)
    erreur = _valider(obj)
    if erreur is not None:
        return erreur
    obj.save()
    return Response(model.objects.filter(pk=obj.pk).values(*fields).first())


class LectureScolariteEcritureDFRC(BasePermission):
    """Lecture ouverte au personnel de scolarité, écriture réservée à l'administration.

    Les écrans de candidature et d'inscription ont besoin de lire niveaux,
    semestres et groupes ; les modifier reste un acte de paramétrage.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return IsSecretariatOrDFRC().has_permission(request, view)
        return IsDFRC().has_permission(request, view)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, LectureScolariteEcritureDFRC])
def referentiel_list(request, ressource):
    if ressource not in REFERENTIEL_FIELDS:
        return Response({'error': 'Référentiel inconnu'}, status=404)
    return _referentiel_list(request, ressource)


@api_view(['PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def referentiel_detail(request, ressource, pk):
    if ressource not in REFERENTIEL_FIELDS:
        return Response({'error': 'Référentiel inconnu'}, status=404)
    return _referentiel_detail(request, ressource, pk)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def annee_courante(request):
    """Année académique courante, utilisée comme valeur par défaut par le frontend."""
    annee = AnneeAcademique.courante_ou_none()
    if annee is None:
        return Response({'annee': None, 'id': None, 'libelle': None})
    data = {
        'id': annee.id,
        'libelle': annee.libelle,
        'date_debut': annee.date_debut,
        'date_fin': annee.date_fin,
    }
    return Response({
        **data,
        'annee': data,
    })


def _serialize_ecue(ecue):
    return {
        'id': ecue.id,
        'code': ecue.code,
        'intitule': ecue.intitule,
        'credits': ecue.credits,
        'coefficient': ecue.coefficient,
        'volume_cm': ecue.volume_cm,
        'volume_td': ecue.volume_td,
        'volume_tp': ecue.volume_tp,
        'volume_total': ecue.volume_total,
        'ref_module_id': ecue.ref_module_id,
        'ordre': ecue.ordre,
    }


def _serialize_ue(ue):
    return {
        'id': ue.id,
        'code': ue.code,
        'intitule': ue.intitule,
        'credits': ue.credits,
        'caractere': ue.caractere,
        'ordre': ue.ordre,
        'semestre': {
            'id': ue.semestre_id,
            'numero': ue.semestre.numero,
            'libelle': ue.semestre.libelle,
        },
        'ecues': [_serialize_ecue(ecue) for ecue in ue.ecues.all()],
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDFRC])
def maquette_list(request):
    """Liste des maquettes, avec le nombre d'UE et le total de crédits."""
    queryset = Maquette.objects.select_related(
        'annee_academique', 'ref_formation', 'parcours', 'niveau',
    ).annotate(
        nb_ue=Count('unites_enseignement', distinct=True),
        total_credits=Sum('unites_enseignement__credits'),
    )
    for champ in ('annee_academique_id', 'ref_formation_id', 'parcours_id', 'niveau_id', 'statut'):
        if champ in request.query_params:
            queryset = queryset.filter(**{champ: request.query_params[champ]})
    return Response([
        {
            'id': maquette.id,
            'libelle': str(maquette),
            'annee_academique_id': maquette.annee_academique_id,
            'annee_academique': maquette.annee_academique.libelle,
            'ref_formation_id': maquette.ref_formation_id,
            'ref_formation': maquette.ref_formation.intitule,
            'parcours_id': maquette.parcours_id,
            'parcours': maquette.parcours.intitule if maquette.parcours else None,
            'niveau_id': maquette.niveau_id,
            'niveau': maquette.niveau.code,
            'version': maquette.version,
            'statut': maquette.statut,
            'nb_ue': maquette.nb_ue,
            'total_credits': maquette.total_credits or 0,
        }
        for maquette in queryset
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDFRC])
def maquette_detail(request, pk):
    """Détail d'une maquette : UE groupées par semestre, avec leurs ECUE."""
    maquette = Maquette.objects.select_related(
        'annee_academique', 'ref_formation', 'parcours', 'niveau',
    ).filter(pk=pk).first()
    if maquette is None:
        return Response({'error': 'Introuvable'}, status=404)
    unites = (
        UE.objects.filter(maquette=maquette)
        .select_related('semestre')
        .prefetch_related('ecues')
    )
    return Response({
        'id': maquette.id,
        'libelle': str(maquette),
        'annee_academique': maquette.annee_academique.libelle,
        'ref_formation': maquette.ref_formation.intitule,
        'parcours': maquette.parcours.intitule if maquette.parcours else None,
        'niveau': maquette.niveau.code,
        'version': maquette.version,
        'statut': maquette.statut,
        'unites_enseignement': [_serialize_ue(ue) for ue in unites],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDFRC])
def maquette_ecues_semestre(request, pk, semestre_id):
    """ECUE d'un semestre donné d'une maquette.

    Sert de source à la génération automatique des inscriptions pédagogiques (lot 5).
    """
    if not Maquette.objects.filter(pk=pk).exists():
        return Response({'error': 'Maquette introuvable'}, status=404)
    if not Semestre.objects.filter(pk=semestre_id).exists():
        return Response({'error': 'Semestre introuvable'}, status=404)
    ecues = (
        ECUE.objects.filter(ue__maquette_id=pk, ue__semestre_id=semestre_id)
        .select_related('ue')
        .order_by('ue__ordre', 'ordre')
    )
    return Response([
        {**_serialize_ecue(ecue), 'ue_id': ecue.ue_id, 'ue_code': ecue.ue.code}
        for ecue in ecues
    ])


# ── Lot L1 — écriture et workflow des maquettes (garde-fou R4) ────────────────


def _journaliser_maquette(maquette, action, utilisateur, detail=None):
    MaquetteJournal.objects.create(
        maquette=maquette, action=action, utilisateur=utilisateur, detail=detail,
    )


def _serializer_maquette(maquette):
    return {
        'id': maquette.id,
        'libelle': str(maquette),
        'annee_academique_id': maquette.annee_academique_id,
        'ref_formation_id': maquette.ref_formation_id,
        'parcours_id': maquette.parcours_id,
        'niveau_id': maquette.niveau_id,
        'version': maquette.version,
        'statut': maquette.statut,
        'validee_par': maquette.validee_par_id,
        'validee_le': maquette.validee_le,
        'activee_par': maquette.activee_par_id,
        'activee_le': maquette.activee_le,
        'commentaire_validation': maquette.commentaire_validation,
        'credits_total': maquette.credits_total,
        'volume_horaire_total': str(maquette.volume_horaire_total),
        'problemes_coherence': maquette.verifier_coherence(),
    }


def _get_maquette(pk):
    return Maquette.objects.filter(pk=pk).first()


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def maquette_create(request):
    """Création d'une maquette BROUILLON (v1, ou version suivante si existante)."""
    annee_id = request.data.get('annee_academique_id')
    formation_id = request.data.get('ref_formation_id')
    niveau_id = request.data.get('niveau_id')
    if not (annee_id and formation_id and niveau_id):
        return Response(
            {'error': 'annee_academique_id, ref_formation_id et niveau_id sont requis.'},
            status=400,
        )
    filtre = {
        'annee_academique_id': annee_id,
        'ref_formation_id': formation_id,
        'parcours_id': request.data.get('parcours_id'),
        'niveau_id': niveau_id,
    }
    derniere = (
        Maquette.objects.filter(**filtre)
        .order_by('-version').values_list('version', flat=True).first() or 0
    )
    maquette = Maquette(
        **filtre, version=derniere + 1, libelle=request.data.get('libelle', ''),
    )
    try:
        maquette.full_clean(exclude=['libelle'])
        maquette.save()
    except ValidationError as exc:
        return Response(exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}, status=400)
    _journaliser_maquette(maquette, MaquetteJournal.Action.CREATION, request.user)
    return Response(_serializer_maquette(maquette), status=201)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def maquette_update(request, pk):
    """Édition des champs de tête — maquette BROUILLON uniquement (R4)."""
    maquette = _get_maquette(pk)
    if maquette is None:
        return Response({'error': 'Introuvable'}, status=404)
    if maquette.statut != Maquette.Statut.BROUILLON:
        return Response(
            {'error': f'Maquette {maquette.statut.lower()} immuable : créez une nouvelle version (clonage).'},
            status=400,
        )
    for champ in ('libelle', 'commentaire_validation', 'parcours_id'):
        if champ in request.data:
            setattr(maquette, champ, request.data[champ])
    try:
        maquette.full_clean(exclude=['libelle'])
        maquette.save()
    except ValidationError as exc:
        return Response(exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}, status=400)
    _journaliser_maquette(maquette, MaquetteJournal.Action.MODIFICATION, request.user)
    return Response(_serializer_maquette(maquette))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def maquette_valider(request, pk):
    """BROUILLON → VALIDEE : exige une maquette complète et cohérente."""
    maquette = _get_maquette(pk)
    if maquette is None:
        return Response({'error': 'Introuvable'}, status=404)
    if maquette.statut != Maquette.Statut.BROUILLON:
        return Response({'error': f'Validation impossible : statut {maquette.statut}.'}, status=400)
    problemes = maquette.verifier_coherence()
    if problemes:
        return Response({'error': 'Maquette incomplète ou incohérente.', 'problemes': problemes}, status=400)
    maquette.statut = Maquette.Statut.VALIDEE
    maquette.validee_par = request.user
    maquette.validee_le = timezone.now()
    maquette.commentaire_validation = request.data.get('commentaire', '')
    maquette.save()
    _journaliser_maquette(
        maquette, MaquetteJournal.Action.VALIDATION, request.user,
        {'commentaire': maquette.commentaire_validation},
    )
    return Response(_serializer_maquette(maquette))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def maquette_activer(request, pk):
    """VALIDEE → ACTIVE — réservé DFRC ; la cohérence est revérifiée."""
    maquette = _get_maquette(pk)
    if maquette is None:
        return Response({'error': 'Introuvable'}, status=404)
    if maquette.statut != Maquette.Statut.VALIDEE:
        return Response({'error': f'Activation impossible : statut {maquette.statut} (attendu VALIDEE).'}, status=400)
    problemes = maquette.verifier_coherence()
    if problemes:
        return Response({'error': 'Maquette incohérente.', 'problemes': problemes}, status=400)
    maquette.statut = Maquette.Statut.ACTIVE
    maquette.activee_par = request.user
    maquette.activee_le = timezone.now()
    maquette.save()
    _journaliser_maquette(maquette, MaquetteJournal.Action.ACTIVATION, request.user)
    return Response(_serializer_maquette(maquette))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def maquette_archiver(request, pk):
    """ACTIVE → ARCHIVEE : la version reste consultable, plus modifiable."""
    maquette = _get_maquette(pk)
    if maquette is None:
        return Response({'error': 'Introuvable'}, status=404)
    if maquette.statut != Maquette.Statut.ACTIVE:
        return Response({'error': f'Archivage impossible : statut {maquette.statut} (attendu ACTIVE).'}, status=400)
    maquette.statut = Maquette.Statut.ARCHIVEE
    maquette.save()
    _journaliser_maquette(maquette, MaquetteJournal.Action.ARCHIVAGE, request.user)
    return Response(_serializer_maquette(maquette))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def maquette_cloner(request, pk):
    """Crée une nouvelle version BROUILLON copiée de la maquette (R4)."""
    maquette = _get_maquette(pk)
    if maquette is None:
        return Response({'error': 'Introuvable'}, status=404)
    if maquette.statut == Maquette.Statut.BROUILLON:
        return Response({'error': 'Un clonage se fait depuis une version aboutie (VALIDEE/ACTIVE/ARCHIVEE).'}, status=400)
    clone = maquette.cloner(request.user)
    return Response(_serializer_maquette(clone), status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDFRC])
def maquette_journal(request, pk):
    """Historique des validations et changements d'état (règle métier)."""
    maquette = _get_maquette(pk)
    if maquette is None:
        return Response({'error': 'Introuvable'}, status=404)
    return Response([
        {
            'action': entree.action,
            'utilisateur': entree.utilisateur.username if entree.utilisateur else None,
            'horodatage': entree.horodatage,
            'detail': entree.detail,
        }
        for entree in maquette.journal.select_related('utilisateur')
    ])


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def maquette_ue_create(request, pk):
    """Ajout d'une UE — maquette BROUILLON uniquement."""
    maquette = _get_maquette(pk)
    if maquette is None:
        return Response({'error': 'Introuvable'}, status=404)
    if maquette.statut != Maquette.Statut.BROUILLON:
        return Response({'error': f'Maquette {maquette.statut.lower()} immuable.'}, status=400)
    semestre_id = request.data.get('semestre_id')
    code = (request.data.get('code') or '').strip()
    if not (semestre_id and code):
        return Response({'error': 'semestre_id et code sont requis.'}, status=400)
    if not Semestre.objects.filter(pk=semestre_id).exists():
        return Response({'error': 'Semestre introuvable'}, status=400)
    try:
        ue = UE.objects.create(
            maquette=maquette,
            semestre_id=semestre_id,
            code=code,
            intitule=request.data.get('intitule', ''),
            credits=int(request.data.get('credits', 0) or 0),
            caractere=request.data.get('caractere', UE.Caractere.OBLIGATOIRE),
            ordre=int(request.data.get('ordre', maquette.unites_enseignement.count() + 1) or 1),
        )
    except ValidationError as exc:
        return Response({'error': exc.messages}, status=400)
    _journaliser_maquette(maquette, MaquetteJournal.Action.MODIFICATION, request.user,
                          {'ajout_ue': ue.code})
    return Response({'id': ue.id, 'code': ue.code}, status=201)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def ue_detail(request, pk):
    """Édition / suppression d'une UE — maquette BROUILLON uniquement."""
    ue = UE.objects.filter(pk=pk).first()
    if ue is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        if request.method == 'DELETE':
            code = ue.code
            ue.delete()
            _journaliser_maquette(ue.maquette, MaquetteJournal.Action.MODIFICATION,
                                  request.user, {'suppression_ue': code})
            return Response(status=204)
        for champ in ('intitule', 'credits', 'caractere', 'ordre', 'semestre_id'):
            if champ in request.data:
                setattr(ue, champ, request.data[champ])
        ue.save()
    except ValidationError as exc:
        return Response({'error': exc.messages}, status=400)
    return Response({'id': ue.id, 'code': ue.code, 'credits': ue.credits})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def ue_ecue_create(request, pk):
    """Ajout d'une ECUE sous une UE — maquette BROUILLON uniquement."""
    ue = UE.objects.select_related('maquette').filter(pk=pk).first()
    if ue is None:
        return Response({'error': 'Introuvable'}, status=404)
    if ue.maquette.statut != Maquette.Statut.BROUILLON:
        return Response({'error': f'Maquette {ue.maquette.statut.lower()} immuable.'}, status=400)
    code = (request.data.get('code') or '').strip()
    if not code:
        return Response({'error': 'code requis.'}, status=400)
    ref_module = None
    if request.data.get('ref_module_id'):
        ref_module = RefModule.objects.filter(pk=request.data['ref_module_id']).first()
        if ref_module is None:
            return Response({'error': 'RefModule introuvable'}, status=400)
    try:
        ecue = ECUE.objects.create(
            ue=ue,
            code=code,
            intitule=request.data.get('intitule', ''),
            credits=int(request.data.get('credits', 0) or 0),
            coefficient=request.data.get('coefficient', 1),
            volume_cm=request.data.get('volume_cm', 0),
            volume_td=request.data.get('volume_td', 0),
            volume_tp=request.data.get('volume_tp', 0),
            ref_module=ref_module,
            ordre=int(request.data.get('ordre', ue.ecues.count() + 1) or 1),
        )
    except ValidationError as exc:
        return Response({'error': exc.messages}, status=400)
    return Response({'id': ecue.id, 'code': ecue.code}, status=201)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def ecue_detail(request, pk):
    """Édition / suppression / archivage d'une ECUE — maquette BROUILLON uniquement.

    DELETE ?mode=archive : archivage soft (l'ECUE archivée ne peut plus entrer
    dans une nouvelle maquette — contrôle de cohérence et clonage).
    """
    ecue = ECUE.objects.select_related('ue__maquette').filter(pk=pk).first()
    if ecue is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        if request.method == 'DELETE':
            if request.query_params.get('mode') == 'archive':
                ecue.archive = True
                ecue.save()
                return Response({'detail': 'ECUE archivée.', 'archive': True})
            ecue.delete()
            return Response(status=204)
        for champ in ('intitule', 'credits', 'coefficient', 'volume_cm', 'volume_td', 'volume_tp', 'ordre'):
            if champ in request.data:
                setattr(ecue, champ, request.data[champ])
        if 'archive' in request.data:
            ecue.archive = bool(request.data['archive'])
        if 'ref_module_id' in request.data:
            ecue.ref_module_id = request.data['ref_module_id'] or None
        ecue.save()
    except ValidationError as exc:
        return Response({'error': exc.messages}, status=400)
    return Response({'id': ecue.id, 'code': ecue.code, 'credits': ecue.credits, 'archive': ecue.archive})
