"""GET-INJS — API d'import des inscrits et de génération annuelle.

Routes **ajoutées** (aucune route existante modifiée) :

* ``POST /api/edts/lmd/import/inscrits/analyser/``  — analyse d'un fichier, sans écriture ;
* ``POST /api/edts/lmd/import/inscrits/``           — import réel du fichier ;
* ``GET  /api/edts/lmd/import/inscrits/synthese/``  — effectifs importés par cohorte ;
* ``POST /api/edts/lmd/generate-annee/``            — génération des EDT de l'année ;
* ``GET  /api/edts/lmd/conception/``                — téléchargement de la conception.

Garde : les permissions existantes ``edts.permissions`` s'appliquent telles
quelles (lecture pour la synthèse et la conception, planification pour l'import
et la génération). Aucun second RBAC n'est créé.
"""

from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from edts.permissions import (
    IsEdtPlanification, IsEdtReadOnlyOrPlanification, IsEdtValidation,
)

#: Taille maximale acceptée pour un fichier d'inscrits (protection mémoire).
TAILLE_MAX_FICHIER = 20 * 1024 * 1024  # 20 Mo

#: Emplacement du document de conception, servi en téléchargement.
#: Le document **livré** est à la racine du dépôt (exigence de la mission) ;
#: ``docs/getinjs/Conception-GET-INJS.txt`` reste servi en repli pour ne pas
#: casser les liens existants.
RACINE_DEPOT = Path(settings.BASE_DIR).parent
CHEMIN_CONCEPTION = RACINE_DEPOT / 'Conception-GET-INJS.txt'
CHEMIN_CONCEPTION_REPLI = RACINE_DEPOT / 'docs' / 'getinjs' / 'Conception-GET-INJS.txt'


def _int(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def _booleen(valeur):
    return str(valeur).lower() in ('1', 'true', 'oui', 'yes')


def _fichier_de_requete(request):
    """Extrait (nom, contenu) du fichier transmis — ``None`` si absent."""
    fichier = request.FILES.get('fichier') or request.FILES.get('file')
    if fichier is not None:
        if fichier.size > TAILLE_MAX_FICHIER:
            return None, None, {
                'motif_echec': 'FICHIER_TROP_VOLUMINEUX',
                'detail': {
                    'explication': (
                        f'Le fichier dépasse la limite de '
                        f'{TAILLE_MAX_FICHIER // (1024 * 1024)} Mo.'
                    ),
                    'taille_recue': fichier.size,
                },
            }
        return fichier.name, fichier.read(), None
    # Repli texte : contenu CSV transmis directement dans le corps.
    contenu = request.data.get('contenu')
    if contenu:
        return request.data.get('nom_fichier') or 'inscrits.csv', contenu, None
    return None, None, None


def _annee_de_requete(request):
    annee_id = _int(request.data.get('annee_academique_id') or request.query_params.get('annee'))
    if annee_id is None:
        return None, Response({
            'status': 'BLOCKING',
            'motif_echec': 'ANNEE_ACADEMIQUE_REQUISE',
            'detail': {
                'explication': (
                    'annee_academique_id est requis : un import et une génération '
                    'portent toujours sur une année académique précise.'
                ),
                'action_recommandee': 'Transmettre l’identifiant de l’année.',
            },
        }, status=status.HTTP_400_BAD_REQUEST)

    from scolarite.models import AnneeAcademique

    if not AnneeAcademique.objects.filter(pk=annee_id).exists():
        return None, Response({
            'status': 'BLOCKING',
            'motif_echec': 'ANNEE_ACADEMIQUE_INTROUVABLE',
            'detail': {
                'explication': f'L’année académique #{annee_id} est introuvable.',
                'action_recommandee': 'Vérifier l’identifiant transmis.',
            },
        }, status=status.HTTP_404_NOT_FOUND)
    return annee_id, None


def _executer_import(request, *, appliquer):
    """Tronc commun de l'analyse et de l'import réel."""
    from edts.moteur.import_inscrits import importer_inscrits

    annee_id, erreur = _annee_de_requete(request)
    if erreur is not None:
        return erreur

    nom_fichier, contenu, erreur_fichier = _fichier_de_requete(request)
    if erreur_fichier is not None:
        return Response({'status': 'BLOCKING', **erreur_fichier},
                        status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if contenu is None:
        return Response({
            'status': 'BLOCKING',
            'motif_echec': 'FICHIER_REQUIS',
            'detail': {
                'explication': (
                    'Aucun fichier reçu. Formats acceptés : CSV (séparateur « ; » '
                    'ou « , ») et Excel (.xlsx).'
                ),
                'action_recommandee': (
                    'Joindre le fichier dans le champ multipart « fichier ».'
                ),
            },
        }, status=status.HTTP_400_BAD_REQUEST)

    rapport = importer_inscrits(
        annee_academique_id=annee_id,
        nom_fichier=nom_fichier,
        contenu=contenu,
        appliquer=appliquer,
        acteur=request.user if request.user.is_authenticated else None,
    )
    donnees = rapport.as_dict()

    # Ordre volontaire : « aucune ligne exploitable » est une erreur de
    # CONTENU (422), avant les échecs de format/données référentielles (409).
    if not rapport.lignes_valides:
        return Response(donnees, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if rapport.motif_echec is not None:
        return Response(donnees, status=status.HTTP_409_CONFLICT)
    return Response(donnees, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def analyser_import_api(request):
    """POST /api/edts/lmd/import/inscrits/analyser/ — analyse SANS écriture.

    Le rapport est identique à celui de l'import réel (lignes lues, valides,
    rejetées avec motif, cohortes, effectifs) : il permet de valider un fichier
    client avant de l'intégrer, sans créer de groupes ni d'inscriptions.
    """
    return _executer_import(request, appliquer=False)


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def importer_inscrits_api(request):
    """POST /api/edts/lmd/import/inscrits/ — import réel, idempotent.

    Idempotence : la clé est le couple (année académique, matricule) ; réimporter
    le même fichier met à jour les lignes existantes sans en créer de nouvelles.
    L'écriture est transactionnelle : si aucune ligne n'est exploitable, aucune
    cohorte partielle n'est laissée en base.
    """
    return _executer_import(request, appliquer=True)


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def synthese_import_api(request):
    """GET /api/edts/lmd/import/inscrits/synthese/ — effectifs importés.

    Retourne le dénombrement **réel** des inscriptions importées, par filière,
    formation, parcours, niveau, groupe et vague — c'est l'effectif utilisé
    comme contrainte de capacité lors de la génération.
    """
    from edts.moteur.annee import effectif_importe, repartition_importee

    annee_id, erreur = _annee_de_requete(request)
    if erreur is not None:
        return erreur

    repartition = repartition_importee(annee_id)
    return Response({
        'annee_academique_id': annee_id,
        'effectif_total': effectif_importe(annee_id),
        'cohortes': repartition,
        'nb_cohortes': len(repartition),
    })


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def generate_annee_api(request):
    """POST /api/edts/lmd/generate-annee/ — EDT de TOUS les groupes de l'année.

    Paramètres : ``annee_academique_id`` (requis), ``semaines`` (optionnelles),
    ``persister`` (bool, défaut faux = prévisualisation), ``remplacer`` (défaut
    vrai — idempotence), ``inclure_maquette`` (défaut vrai : complète les
    cohortes sans affectation pédagogique à partir de la maquette active).

    Une année incomplète n'est **jamais** présentée comme réussie : le bilan
    expose par groupe le statut, les séances attendues/placées/non placées et le
    motif d'échec éventuel. Aucune publication n'est effectuée ici.
    """
    from edts.moteur.annee import ANNEE_IMPOSSIBLE, generer_annee

    annee_id, erreur = _annee_de_requete(request)
    if erreur is not None:
        return erreur

    semaines = request.data.get('semaines')
    if isinstance(semaines, str):
        semaines = [s for s in semaines.replace(' ', '').split(',') if s]
    semaines = [int(s) for s in semaines if str(s).isdigit()] if semaines else None

    bilan = generer_annee(
        annee_id,
        semaines=semaines,
        persister=_booleen(request.data.get('persister')),
        remplacer=_booleen(request.data.get('remplacer', True)),
        inclure_maquette=_booleen(request.data.get('inclure_maquette', True)),
    )

    if bilan['status_global'] == ANNEE_IMPOSSIBLE:
        return Response(bilan, status=status.HTTP_409_CONFLICT)
    persiste = bilan.get('persistence_demandee')
    complet = bilan['status_global'] == 'COMPLETE'
    return Response(
        bilan,
        status=status.HTTP_201_CREATED if (complet and persiste) else status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def conception_api(request):
    """GET /api/edts/lmd/conception/ — télécharge ``Conception-GET-INJS.txt``.

    Le document de conception est **le fichier du dépôt**
    (``docs/getinjs/Conception-GET-INJS.txt``) : il n'existe pas de copie en
    base qui pourrait diverger. S'il est absent, la réponse le dit
    explicitement (404 motivé) au lieu de servir un contenu vide.
    """
    chemin = CHEMIN_CONCEPTION if CHEMIN_CONCEPTION.is_file() else CHEMIN_CONCEPTION_REPLI
    if not chemin.is_file():
        return Response({
            'status': 'BLOCKING',
            'motif_echec': 'CONCEPTION_INTROUVABLE',
            'detail': {
                'explication': 'Le document de conception est absent du dépôt.',
                'chemins_attendus': [str(CHEMIN_CONCEPTION), str(CHEMIN_CONCEPTION_REPLI)],
            },
        }, status=status.HTTP_404_NOT_FOUND)

    reponse = FileResponse(
        chemin.open('rb'),
        as_attachment=True,
        filename='Conception-GET-INJS.txt',
        content_type='text/plain; charset=utf-8',
    )
    return reponse


# ══════════════════════════════════════════════════════════════════════════════
# LOT 2 — CAMPAGNES DE GÉNÉRATION
# ══════════════════════════════════════════════════════════════════════════════
#
# Routes AJOUTÉES sous ``campagnes/`` : aucune route existante n'est renommée ni
# supprimée. Les permissions existantes (``edts.permissions``) restent seules
# juges : planification pour créer/lancer, validation pour valider/publier,
# lecture pour consulter.

def _refus(exc):
    """Traduit un refus métier en réponse HTTP structurée (jamais un 500)."""
    statuts_http = {
        'CAMPAGNE_INTROUVABLE': status.HTTP_404_NOT_FOUND,
        'ANNEE_ACADEMIQUE_INTROUVABLE': status.HTTP_404_NOT_FOUND,
        'CAMPAGNE_DEJA_EN_COURS': status.HTTP_409_CONFLICT,
        'CAMPAGNE_DEJA_EXISTANTE': status.HTTP_409_CONFLICT,
        'TRANSITION_REFUSEE': status.HTTP_409_CONFLICT,
        'VALIDATION_BLOQUANTE': status.HTTP_409_CONFLICT,
        'PUBLICATION_INCOMPLETE': status.HTTP_409_CONFLICT,
        'PUBLICATION_ECHOUEE': status.HTTP_409_CONFLICT,
        'AUCUN_EDT_A_VALIDER': status.HTTP_409_CONFLICT,
        'AUCUN_EDT_A_PUBLIER': status.HTTP_409_CONFLICT,
    }
    return Response(
        {'status': 'BLOCKING', 'motif_echec': exc.motif, 'detail': exc.detail},
        status=statuts_http.get(exc.motif, status.HTTP_400_BAD_REQUEST),
    )


@api_view(['GET', 'POST'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def campagnes_api(request):
    """GET liste / POST crée une campagne de génération.

    GET : ``?annee=<id>`` filtre par année académique.
    POST : ``annee_academique_id`` et ``libelle`` requis ; ``semaines``,
    ``perimetre`` et ``parametres`` optionnels.
    """
    from edts.moteur.campagnes import (
        TransitionRefusee, campagne_en_dict, creer_campagne,
    )
    from edts.models import CampagneGeneration

    if request.method == 'GET':
        qs = CampagneGeneration.objects.select_related('annee_academique', 'cree_par')
        annee_id = _int(request.query_params.get('annee'))
        if annee_id:
            qs = qs.filter(annee_academique_id=annee_id)
        donnees = [campagne_en_dict(c) for c in qs[:200]]
        return Response({'count': qs.count(), 'results': donnees})

    annee_id = _int(request.data.get('annee_academique_id'))
    libelle = (request.data.get('libelle') or '').strip()
    if annee_id is None or not libelle:
        return Response({
            'status': 'BLOCKING',
            'motif_echec': 'PARAMETRES_INCOMPLETS',
            'detail': {
                'explication': 'annee_academique_id et libelle sont requis.',
                'champs_attendus': ['annee_academique_id', 'libelle'],
            },
        }, status=status.HTTP_400_BAD_REQUEST)

    semaines = request.data.get('semaines') or []
    if isinstance(semaines, str):
        semaines = [s for s in semaines.replace(' ', '').split(',') if s]
    perimetre = request.data.get('perimetre') or {}
    parametres = request.data.get('parametres') or {}
    try:
        campagne = creer_campagne(
            annee_academique_id=annee_id,
            libelle=libelle,
            user=request.user,
            semaines=semaines,
            perimetre=perimetre if isinstance(perimetre, dict) else {},
            parametres=parametres if isinstance(parametres, dict) else {},
        )
    except TransitionRefusee as exc:
        return _refus(exc)
    return Response(campagne_en_dict(campagne), status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def campagne_detail_api(request, pk):
    """GET /api/edts/campagnes/<pk>/ — fiche de la campagne."""
    from edts.moteur.campagnes import TransitionRefusee, campagne_en_dict, _charger

    try:
        campagne = _charger(pk)
    except TransitionRefusee as exc:
        return _refus(exc)
    return Response(campagne_en_dict(campagne))


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def campagne_demarrer_api(request, pk):
    """POST /api/edts/campagnes/<pk>/demarrer/ — lance une exécution.

    ``asynchrone`` (défaut vrai) : la génération tourne en arrière-plan et
    l'API répond immédiatement avec l'identifiant d'exécution ; l'avancement
    s'observe sur ``/statut/``. ``asynchrone=false`` exécute dans la requête
    (utile aux petits périmètres et aux tests).
    """
    from edts.moteur.campagnes import TransitionRefusee, demarrer_campagne

    asynchrone = str(request.data.get('asynchrone', 'true')).lower() not in ('false', '0', 'non')
    try:
        resultat = demarrer_campagne(pk, user=request.user, asynchrone=asynchrone)
    except TransitionRefusee as exc:
        return _refus(exc)
    return Response(resultat, status=status.HTTP_202_ACCEPTED if asynchrone else status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def campagne_statut_api(request, pk):
    """GET /api/edts/campagnes/<pk>/statut/ — interrogation périodique."""
    from edts.moteur.campagnes import TransitionRefusee, statut_campagne

    try:
        return Response(statut_campagne(pk))
    except TransitionRefusee as exc:
        return _refus(exc)


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def campagne_resultat_api(request, pk):
    """GET /api/edts/campagnes/<pk>/resultat/ — bilan par groupe + historique."""
    from edts.moteur.campagnes import TransitionRefusee, resultat_campagne

    try:
        return Response(resultat_campagne(pk))
    except TransitionRefusee as exc:
        return _refus(exc)


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def campagne_donnees_pretes_api(request, pk):
    """POST /api/edts/campagnes/<pk>/donnees-pretes/ — ``BROUILLON`` → ``PRET``."""
    from edts.moteur.campagnes import TransitionRefusee, marquer_pret

    try:
        return Response(marquer_pret(pk, user=request.user))
    except TransitionRefusee as exc:
        return _refus(exc)


@api_view(['POST'])
@permission_classes([IsEdtValidation])
def campagne_valider_api(request, pk):
    """POST /api/edts/campagnes/<pk>/valider/ — contrôle et validation.

    Réservé à la Direction / Admin, comme la validation d'un EDT unitaire.
    """
    from edts.moteur.campagnes import TransitionRefusee, valider_campagne

    try:
        return Response(valider_campagne(pk, user=request.user))
    except TransitionRefusee as exc:
        return _refus(exc)


@api_view(['POST'])
@permission_classes([IsEdtValidation])
def campagne_publier_api(request, pk):
    """POST /api/edts/campagnes/<pk>/publier/ — publication atomique du périmètre."""
    from edts.moteur.campagnes import TransitionRefusee, publier_campagne

    try:
        return Response(publier_campagne(
            pk, user=request.user, motif=(request.data.get('motif') or '').strip(),
        ))
    except TransitionRefusee as exc:
        return _refus(exc)
