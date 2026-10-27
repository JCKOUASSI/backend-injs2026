"""API des dossiers étudiants et des inscriptions administratives."""

from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Prefetch
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from admissions.models import Admission, PieceCandidature
from authentication.permissions import IsSecretariatOrDFRC
from habilitations.permissions import ExigePermission

from . import inscription_services
from .models import (
    AffectationGroupe,
    DossierEtudiant,
    EvenementScolarite,
    InscriptionAdministrative,
    InscriptionPedagogique,
    JournalScolarite,
    journaliser,
)

INSCRIPTION_CHAMPS = [
    'annee_academique_id', 'ref_formation_id', 'parcours_id', 'niveau_id', 'vague_id',
    'categorie_id', 'grade_id', 'regime_id', 'statut_etudiant_id',
    'type_inscription', 'date_inscription', 'observations',
]


def _serialize_dossier(dossier, detail=False):
    data = {
        'id': dossier.id,
        'uuid': str(dossier.uuid),
        'participant_id': dossier.participant_id,
        'matricule': dossier.matricule,
        'nom': dossier.participant.nom,
        'prenom': dossier.participant.prenom,
        'nom_complet': dossier.nom_complet,
        'statut_id': dossier.statut_id,
        'statut': dossier.statut.libelle if dossier.statut else None,
        'date_premiere_inscription': dossier.date_premiere_inscription,
    }
    if detail:
        inscriptions = getattr(dossier, '_inscriptions_detail', None)
        if inscriptions is None:
            inscriptions = list(dossier.inscriptions.select_related(
                'annee_academique', 'ref_formation', 'niveau', 'valide_par',
            ))
        courante = next(
            (inscription for inscription in inscriptions
             if inscription.statut == InscriptionAdministrative.Statut.VALIDEE),
            None,
        )
        data.update({
            'observations': dossier.observations,
            'email': dossier.participant.email,
            'telephone': dossier.participant.telephone,
            'date_naissance': dossier.participant.date_naissance,
            'lieu_naissance': dossier.participant.lieu_naissance,
            'sexe': dossier.participant.sexe,
            'inscription_courante': _serialize_inscription(courante) if courante else None,
            'inscriptions': [
                _serialize_inscription(i)
                for i in inscriptions
            ],
            'admissions': _serialize_admissions(inscriptions),
            'parcours': _serialize_parcours(inscriptions),
            'affectations_groupes': _serialize_affectations(inscriptions),
            'inscriptions_pedagogiques': _serialize_pedagogie(inscriptions),
            'historique': _serialize_evenements(dossier),
            'ressources': {
                'evenements': f'/api/scolarite/etudiants/{dossier.pk}/evenements/',
                'inscriptions_pedagogiques': [
                    f'/api/scolarite/inscriptions/{inscription.pk}/pedagogie/'
                    for inscription in inscriptions
                ],
                'affectations_groupes': [
                    f'/api/scolarite/inscriptions/{inscription.pk}/affectations/'
                    for inscription in inscriptions
                ],
                'resultats_ecue': '/api/evaluations-academiques/resultats/ecue/',
                'resultats_ue': '/api/evaluations-academiques/resultats/ue/',
                'resultats_semestre': '/api/evaluations-academiques/resultats/semestre/',
                'edt_etudiants': '/api/scolarite/edt/etudiants/',
            },
        })
    return data


def _serialize_inscription(inscription, detail=False):
    data = {
        'id': inscription.id,
        'etudiant_id': inscription.etudiant_id,
        'matricule': inscription.etudiant.matricule,
        'etudiant': inscription.etudiant.nom_complet,
        'annee_academique_id': inscription.annee_academique_id,
        'annee_academique': inscription.annee_academique.libelle,
        'ref_formation_id': inscription.ref_formation_id,
        'ref_formation': inscription.ref_formation.intitule,
        'parcours_id': inscription.parcours_id,
        'parcours': inscription.parcours.intitule if inscription.parcours_id else None,
        'parcours_code': inscription.parcours.code if inscription.parcours_id else None,
        'niveau_id': inscription.niveau_id,
        'niveau': inscription.niveau.code,
        'cycle': inscription.niveau.get_cycle_display(),
        'vague_id': inscription.vague_id,
        'categorie_id': inscription.categorie_id,
        'grade_id': inscription.grade_id,
        'regime_id': inscription.regime_id,
        'type_inscription': inscription.type_inscription,
        'type_inscription_libelle': inscription.get_type_inscription_display(),
        'statut': inscription.statut,
        'statut_libelle': inscription.get_statut_display(),
        'date_inscription': inscription.date_inscription,
        'date_validation': inscription.date_validation,
        'admission_id': inscription.admission_id,
    }
    if detail:
        data.update({
            'observations': inscription.observations,
            'valide_par': inscription.valide_par.username if inscription.valide_par else None,
            'transitions_possibles': inscription_services.transitions_possibles(inscription),
        })
    return data


def _serialize_admissions(inscriptions):
    """Admission et pièces disponibles, sans exposer les fichiers eux-mêmes."""
    resultats = []
    vus = set()
    for inscription in inscriptions:
        admission = getattr(inscription, 'admission', None)
        if admission is None or admission.pk in vus:
            continue
        vus.add(admission.pk)
        candidature = getattr(admission, 'candidature', None)
        pieces = getattr(candidature, '_pieces_detail', []) if candidature else []
        resultats.append({
            'id': admission.id,
            'candidature_id': admission.candidature_id,
            'decision': admission.decision,
            'date_decision': admission.date_decision,
            'reference_decision': admission.reference_decision,
            'annee_academique_id': admission.annee_academique_id,
            'ref_formation_id': admission.ref_formation_id,
            'parcours_id': admission.parcours_id,
            'niveau_id': admission.niveau_id,
            'pieces': [
                {
                    'id': piece.id,
                    'type_piece_id': piece.type_piece_id,
                    'type_piece': piece.type_piece.libelle,
                    'obligatoire': piece.obligatoire,
                    'statut': piece.statut,
                    'date_delivrance': piece.date_delivrance,
                    'date_expiration': piece.date_expiration,
                    'a_fichier': bool(piece.fichier),
                    'verifie_par': piece.verifie_par.username if piece.verifie_par else None,
                    'verifie_le': piece.verifie_le,
                }
                for piece in pieces
            ],
            'pieces_endpoint': f'/api/admissions/candidatures/{admission.candidature_id}/pieces/',
        })
    return resultats


def _serialize_parcours(inscriptions):
    parcours = []
    vus = set()
    for inscription in inscriptions:
        if not inscription.parcours_id or inscription.parcours_id in vus:
            continue
        vus.add(inscription.parcours_id)
        parcours.append({
            'id': inscription.parcours_id,
            'code': inscription.parcours.code,
            'intitule': inscription.parcours.intitule,
            'ref_formation_id': inscription.parcours.ref_formation_id,
            'inscription_ids': [
                i.id for i in inscriptions if i.parcours_id == inscription.parcours_id
            ],
        })
    return parcours


def _serialize_affectations(inscriptions):
    resultats = []
    for inscription in inscriptions:
        for affectation in getattr(inscription, '_affectations_detail', []):
            resultats.append({
                'id': affectation.id,
                'inscription_id': inscription.id,
                'groupe_id': affectation.groupe_id,
                'groupe': affectation.groupe.nom,
                'annee_academique': affectation.groupe.annee_academique.libelle,
                'formation': affectation.groupe.ref_formation.intitule,
                'parcours': affectation.groupe.parcours.intitule
                if affectation.groupe.parcours_id else None,
                'niveau': affectation.groupe.niveau.code,
                'date_debut': affectation.date_debut,
                'date_fin': affectation.date_fin,
                'active': affectation.active,
                'motif': affectation.motif,
            })
    return resultats


def _serialize_pedagogie(inscriptions):
    resultats = []
    for inscription in inscriptions:
        for ligne in getattr(inscription, '_pedagogie_detail', []):
            resultats.append({
                'id': ligne.id,
                'inscription_id': inscription.id,
                'ecue_id': ligne.ecue_id,
                'ecue_code': ligne.ecue.code,
                'ecue_intitule': ligne.ecue.intitule,
                'ue_id': ligne.ecue.ue_id,
                'ue_code': ligne.ecue.ue.code,
                'semestre_id': ligne.semestre_id,
                'semestre': ligne.semestre.libelle,
                'groupe_id': ligne.groupe_id,
                'groupe': ligne.groupe.nom if ligne.groupe else None,
                'credits': ligne.credits,
                'volume_horaire': ligne.volume_horaire,
                'type_enseignement': ligne.type_enseignement,
                'statut': ligne.statut,
                'origine': ligne.origine,
            })
    return resultats


def _serialize_evenements(dossier):
    return [
        {
            'id': evenement.id,
            'inscription_id': evenement.inscription_id,
            'type_evenement': evenement.type_evenement,
            'type_libelle': evenement.get_type_evenement_display(),
            'date_evenement': evenement.date_evenement,
            'ancienne_valeur': evenement.ancienne_valeur,
            'nouvelle_valeur': evenement.nouvelle_valeur,
            'commentaire': evenement.commentaire,
            'enregistre_par': evenement.enregistre_par.username
            if evenement.enregistre_par else None,
        }
        for evenement in getattr(dossier, '_evenements_detail', [])
    ]


def _inscription_queryset():
    return InscriptionAdministrative.objects.select_related(
        'etudiant__participant', 'annee_academique', 'ref_formation', 'niveau', 'valide_par',
    )


# ── Dossiers étudiants ──────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def etudiant_list(request):
    queryset = DossierEtudiant.objects.select_related('participant', 'statut')
    recherche = request.query_params.get('q')
    if recherche:
        queryset = queryset.filter(
            Q(participant__matricule__icontains=recherche)
            | Q(participant__nom__icontains=recherche)
            | Q(participant__prenom__icontains=recherche)
        )
    for champ, filtre in (
        ('annee_academique_id', 'inscriptions__annee_academique_id'),
        ('niveau_id', 'inscriptions__niveau_id'),
        ('ref_formation_id', 'inscriptions__ref_formation_id'),
        ('parcours_id', 'inscriptions__parcours_id'),
        ('groupe_id', 'inscriptions__affectations__groupe_id'),
    ):
        if champ in request.query_params:
            queryset = queryset.filter(**{filtre: request.query_params[champ]})
    # Tri déterministe pour que deux pages successives ne se chevauchent pas
    # lorsque plusieurs dossiers ont le même nom ou prénom.
    queryset = queryset.distinct().order_by(
        'participant__nom', 'participant__prenom', 'participant__matricule', 'pk',
    )

    # Compatibilité : sans paramètres de pagination, le contrat historique
    # reste une liste JSON. Les écrans volumineux peuvent demander une page.
    if 'page' not in request.query_params and 'page_size' not in request.query_params:
        return Response([_serialize_dossier(d) for d in queryset[:500]])

    try:
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
    except (TypeError, ValueError):
        return Response({'error': 'Les paramètres page et page_size doivent être numériques.'}, status=400)
    if page < 1 or page_size < 1 or page_size > 100:
        return Response({'error': 'page doit être >= 1 et page_size compris entre 1 et 100.'}, status=400)

    total = queryset.count()
    start = (page - 1) * page_size
    resultats = queryset[start:start + page_size]
    return Response({
        'results': [_serialize_dossier(d) for d in resultats],
        'count': total,
        'total_pages': (total + page_size - 1) // page_size,
        'current_page': page,
    })


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def etudiant_detail(request, pk):
    pieces_detail = Prefetch(
        'inscriptions__admission__candidature__pieces',
        queryset=PieceCandidature.objects.select_related('type_piece', 'verifie_par'),
        to_attr='_pieces_detail',
    )
    affectations_detail = Prefetch(
        'inscriptions__affectations',
        queryset=AffectationGroupe.objects.select_related(
            'groupe__annee_academique', 'groupe__ref_formation',
            'groupe__parcours', 'groupe__niveau',
        ),
        to_attr='_affectations_detail',
    )
    pedagogie_detail = Prefetch(
        'inscriptions__inscriptions_pedagogiques',
        queryset=InscriptionPedagogique.objects.select_related(
            'ecue', 'ecue__ue', 'semestre', 'groupe',
        ),
        to_attr='_pedagogie_detail',
    )
    evenements_detail = Prefetch(
        'evenements',
        queryset=EvenementScolarite.objects.select_related('enregistre_par'),
        to_attr='_evenements_detail',
    )
    inscriptions_detail = Prefetch(
        'inscriptions',
        queryset=_inscription_queryset().select_related(
            'parcours', 'admission__candidature',
        ),
        to_attr='_inscriptions_detail',
    )
    dossier = DossierEtudiant.objects.select_related('participant', 'statut').prefetch_related(
        inscriptions_detail,
        pieces_detail,
        affectations_detail,
        pedagogie_detail,
        evenements_detail,
    ).filter(pk=pk).first()
    if dossier is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PATCH':
        # Le statut du dossier ne se modifie pas directement : il doit passer
        # par les workflows d'inscription/jury existants. Le matricule et
        # l'identité restent portés par Participant.
        if 'statut_id' in request.data:
            return Response(
                {'statut_id': ['Modification via le workflow de scolarité uniquement.']},
                status=400,
            )
        ancienne_observation = dossier.observations
        if 'observations' in request.data:
            dossier.observations = request.data['observations'] or ''
        try:
            dossier.full_clean()
        except ValidationError as erreur:
            return Response(erreur.message_dict, status=400)
        dossier.save()
        if dossier.observations != ancienne_observation:
            journaliser(
                JournalScolarite.Action.EVENEMENT_SCOLARITE,
                objet=dossier,
                acteur=request.user,
                ancienne_valeur=ancienne_observation,
                nouvelle_valeur=dossier.observations,
                commentaire='Mise à jour des observations du dossier étudiant.',
            )
    return Response(_serialize_dossier(dossier, detail=True))


# ── Inscriptions administratives ────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC,
                     ExigePermission.pour('scolarite.inscription_administrative.consulter')])
def inscription_list(request):
    if request.method == 'POST':
        return _inscription_creer(request)
    queryset = _inscription_queryset()
    for champ in (
        'statut', 'type_inscription', 'annee_academique_id',
        'ref_formation_id', 'niveau_id', 'etudiant_id', 'vague_id',
    ):
        if champ in request.query_params:
            queryset = queryset.filter(**{champ: request.query_params[champ]})
    recherche = request.query_params.get('q')
    if recherche:
        queryset = queryset.filter(
            Q(etudiant__participant__matricule__icontains=recherche)
            | Q(etudiant__participant__nom__icontains=recherche)
            | Q(etudiant__participant__prenom__icontains=recherche)
        )
    return Response([_serialize_inscription(i) for i in queryset[:500]])


def _inscription_creer(request):
    """Crée une inscription administrative manuellement."""
    etudiant_id = request.data.get('etudiant_id')
    if not etudiant_id:
        return Response({'etudiant_id': ['Champ obligatoire.']}, status=400)
    etudiant = DossierEtudiant.objects.filter(pk=etudiant_id).first()
    if etudiant is None:
        return Response({'etudiant_id': ['Étudiant introuvable.']}, status=400)
    inscription = InscriptionAdministrative(etudiant=etudiant)
    for champ in INSCRIPTION_CHAMPS:
        if champ in request.data:
            valeur = request.data[champ]
            setattr(inscription, champ, valeur if valeur != '' else None)
    if not inscription.type_inscription:
        inscription.type_inscription = InscriptionAdministrative.Type.PREMIERE
    if not inscription.statut:
        inscription.statut = InscriptionAdministrative.Statut.BROUILLON
    if not inscription.date_inscription:
        from django.utils import timezone
        inscription.date_inscription = timezone.localdate()
    try:
        inscription.full_clean()
    except ValidationError as erreur:
        return Response(erreur.message_dict, status=400)
    inscription.save()
    return Response(_serialize_inscription(inscription, detail=True), status=201)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_detail(request, pk):
    inscription = _inscription_queryset().filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PATCH':
        # Le statut ne se modifie que par l'endpoint de transition.
        # Lot L1/L3 : un changement de parcours passe par le service dédié
        # (historisation JournalScolarite + EvenementScolarite REORIENTATION).
        nouveau_parcours_id = request.data.get('parcours_id')
        changement_parcours = (
            nouveau_parcours_id
            and nouveau_parcours_id != inscription.parcours_id
        )
        for champ in INSCRIPTION_CHAMPS:
            if champ in request.data and champ != 'parcours_id':
                valeur = request.data[champ]
                setattr(inscription, champ, valeur if valeur != '' else None)
        if changement_parcours:
            from .models import Parcours
            nouveau_parcours = Parcours.objects.filter(pk=nouveau_parcours_id).first()
            if nouveau_parcours is None:
                return Response({'parcours_id': ['Parcours introuvable.']}, status=400)
            inscription_services.changer_parcours(
                inscription, nouveau_parcours, acteur=request.user,
                motif=request.data.get('motif_parcours', ''),
            )
        try:
            inscription.full_clean(exclude=['date_validation'])
        except ValidationError as erreur:
            return Response(erreur.message_dict, status=400)
        inscription.save()
    if request.method == 'DELETE':
        if inscription.statut == InscriptionAdministrative.Statut.VALIDEE:
            return Response(
                {'error': 'Une inscription validée ne peut pas être supprimée.'},
                status=409,
            )
        inscription.delete()
        return Response(status=204)
    return Response(_serialize_inscription(inscription, detail=True))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_transition(request, pk):
    inscription = _inscription_queryset().filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)
    statut = request.data.get('statut')
    if statut not in InscriptionAdministrative.Statut.values:
        return Response({'statut': ['Statut inconnu.']}, status=400)
    try:
        inscription_services.appliquer_transition(
            inscription, statut, acteur=request.user,
            commentaire=request.data.get('commentaire', ''),
        )
    except inscription_services.InscriptionImpossible as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    return Response(_serialize_inscription(inscription, detail=True))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscrire_depuis_admission(request):
    """Convertit une admission en inscription administrative, en une transaction."""
    admission = Admission.objects.select_related(
        'candidature', 'candidat', 'annee_academique', 'ref_formation', 'niveau',
    ).filter(pk=request.data.get('admission_id')).first()
    if admission is None:
        return Response({'admission_id': ['Admission introuvable.']}, status=400)

    surcharges = {
        champ: request.data[champ]
        for champ in INSCRIPTION_CHAMPS
        if request.data.get(champ) not in (None, '')
    }
    try:
        inscription = inscription_services.convertir_admission_en_inscription(
            admission,
            acteur=request.user,
            matricule=request.data.get('matricule') or None,
            valider=bool(request.data.get('valider')),
            **surcharges,
        )
    except inscription_services.InscriptionImpossible as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response(_serialize_inscription(inscription, detail=True), status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_stats(request):
    """Effectifs inscrits, par statut puis par niveau, formation, vague et catégorie."""
    queryset = InscriptionAdministrative.objects.all()
    if 'annee_academique_id' in request.query_params:
        queryset = queryset.filter(annee_academique_id=request.query_params['annee_academique_id'])

    validees = queryset.filter(statut=InscriptionAdministrative.Statut.VALIDEE)

    def repartition(champ, libelle):
        return {
            (ligne[libelle] or 'Non renseigné'): ligne['total']
            for ligne in validees.values(libelle).annotate(total=Count('id')).order_by()
        }

    return Response({
        'total': queryset.count(),
        'par_statut': {
            ligne['statut']: ligne['total']
            for ligne in queryset.values('statut').annotate(total=Count('id'))
        },
        'inscrits': validees.count(),
        'par_niveau': repartition('niveau', 'niveau__code'),
        'par_formation': repartition('ref_formation', 'ref_formation__intitule'),
        'par_vague': repartition('vague', 'vague__libelle'),
        'par_categorie': repartition('categorie', 'categorie__libelle'),
    })


# ── Lot L1/L3 — radiation, changement de parcours, clôture d'année ───────────


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_radier(request, pk):
    """Radie une inscription VALIDEE : statut SUSPENDUE + événement RADIATION.

    Aucune donnée n'est supprimée (dossier, notes, historique intacts).
    """
    inscription = _inscription_queryset().filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        inscription_services.radier_inscription(
            inscription, acteur=request.user,
            motif=request.data.get('motif', ''),
        )
    except inscription_services.InscriptionImpossible as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response(_serialize_inscription(inscription, detail=True))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_changer_parcours(request, pk):
    """Changement de parcours — historisé (JournalScolarite + REORIENTATION)."""
    inscription = _inscription_queryset().filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)
    from .models import Parcours
    nouveau_parcours = Parcours.objects.filter(pk=request.data.get('parcours_id')).first()
    if nouveau_parcours is None:
        return Response({'error': 'Parcours introuvable.'}, status=400)
    try:
        inscription_services.changer_parcours(
            inscription, nouveau_parcours, acteur=request.user,
            motif=request.data.get('motif', ''),
        )
    except inscription_services.InscriptionImpossible as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response(_serialize_inscription(inscription, detail=True))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def annee_cloturer(request, pk):
    """Clôture une année académique (plus aucune nouvelle inscription)."""
    from .models import AnneeAcademique
    from . import annee_services
    annee = AnneeAcademique.objects.filter(pk=pk).first()
    if annee is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        annee_services.cloturer_annee(annee, acteur=request.user,
                                      commentaire=request.data.get('commentaire', ''))
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response({
        'id': annee.id, 'libelle': annee.libelle,
        'cloturee': annee.cloturee, 'date_cloture': annee.date_cloture,
        'courante': annee.courante,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def annee_rouvrir(request, pk):
    """Réouvre une année clôturée : elle redevient l'année courante."""
    from .models import AnneeAcademique
    from . import annee_services
    annee = AnneeAcademique.objects.filter(pk=pk).first()
    if annee is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        annee_services.rouvrir_annee(annee, acteur=request.user,
                                     commentaire=request.data.get('commentaire', ''))
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response({
        'id': annee.id, 'libelle': annee.libelle,
        'cloturee': annee.cloturee, 'courante': annee.courante,
    })
