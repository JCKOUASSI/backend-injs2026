"""Export, import et retrait par lot des référentiels du registre.

Ces quatre routes complètent le ViewSet générique : elles ne créent aucune
liste parallèle, le modèle, les permissions et les filtres restent ceux du
registre.

* **Export** (CSV, XLSX, DOCX, PDF) — une ligne par valeur, colonnes dérivées
  du modèle ; les clés étrangères sortent en clair (code ou libellé) ;
  les valeurs texte sont neutralisées contre l'injection de formules.
* **Modèle d'import** — en-têtes exacts + un exemple, pour que l'utilisateur
  n'ait jamais à deviner la structure.
* **Import** en deux temps — `mode=apercu` n'écrit rien, `mode=importer`
  applique le plan dans une transaction unique. Les clés étrangères sont
  résolues par identifiant, code ou libellé.
* **Retrait** par lot — le socle interdit la suppression physique : le lot
  archive (ou désactive) les valeurs et renvoie un bilan par identifiant.

Rien n'est jamais appliqué silencieusement : un fichier portant une erreur est
refusé en bloc, une valeur déjà retirée est signalée, et un référentiel géré
par un écran dédié (`editable=False`) est refusé en écriture.
"""

from __future__ import annotations

import logging

from django.http import Http404, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view, parser_classes, permission_classes,
)
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from scolarite import referentiels_export, referentiels_import, tableaux_export

from .permissions import ReferentielPermission
from .registre import REGISTRE, modele_de

logger = logging.getLogger(__name__)

#: Champs techniques jamais exportés ni importés.
CHAMPS_TECHNIQUES = frozenset({
    'id', 'cree_le', 'modifie_le', 'cree_par', 'modifie_par',
    'archive', 'archive_le', 'archive_par', 'archive_motif',
})


class ErreurGestionSerializer(serializers.Serializer):
    """Erreur des routes d'export/import/retrait des référentiels."""

    error = serializers.CharField()


# ── Registre ────────────────────────────────────────────────────────────────
def _entree(slug, ecriture=False):
    """Entrée du registre, ou 404 (écriture refusée hors écran générique)."""
    entree = REGISTRE.get(slug)
    if entree is None or (ecriture and not entree['editable']):
        raise Http404('Référentiel inconnu ou géré par un écran dédié.')
    return entree


def champs_du_modele(modele):
    """Colonnes métier d'un modèle (clés étrangères incluses, audit exclu).

    Les clés étrangères sont désignées par leur attribut ``*_id`` : c'est la
    forme que l'import sait résoudre (identifiant, code ou libellé) et que
    l'export sait rendre lisible.
    """
    champs = []
    for champ in modele._meta.concrete_fields:
        nom = champ.attname if champ.is_relation else champ.name
        if nom in CHAMPS_TECHNIQUES or nom in champs:
            continue
        champs.append(nom)
    return champs


def _perimetre(modele, request):
    """Queryset filtré comme la liste de l'écran (valeurs retirées masquées)."""
    queryset = modele._default_manager.all()
    if 'archive' in {champ.name for champ in modele._meta.concrete_fields}:
        if request.query_params.get('archives') not in ('1', 'true', 'oui'):
            queryset = queryset.filter(archive=False)
    actif = (request.query_params.get('actif') or '').strip().lower()
    if actif in ('1', 'true', 'oui'):
        queryset = queryset.filter(actif=True)
    elif actif in ('0', 'false', 'non'):
        queryset = queryset.filter(actif=False)
    return queryset


def _ids(request):
    brut = (request.query_params.get('ids') or '').strip()
    if not brut:
        return [], None
    morceaux = [morceau.strip() for morceau in brut.split(',') if morceau.strip()]
    for morceau in morceaux:
        if not morceau.isdigit():
            return None, f'Identifiant non numérique : {morceau}.'
    return [int(morceau) for morceau in morceaux], None


def _nom_fichier(slug, fmt):
    from datetime import date

    return f'referentiel-{slug}_{date.today().isoformat()}.{tableaux_export.EXTENSIONS[fmt]}'


# ── Export ──────────────────────────────────────────────────────────────────
@extend_schema(
    parameters=[
        OpenApiParameter('ids', OpenApiTypes.STR, description='Identifiants sélectionnés, séparés par des virgules.'),
        OpenApiParameter('actif', OpenApiTypes.BOOL, description='Filtre actif / inactif.'),
        OpenApiParameter('archives', OpenApiTypes.BOOL, description='Inclure les valeurs archivées.'),
    ],
    responses={200: OpenApiTypes.BINARY, 400: ErreurGestionSerializer},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, ReferentielPermission])
def referentiel_export(request, slug, fmt):
    """Exporte le référentiel courant (périmètre = sélection ou liste filtrée)."""
    if fmt not in referentiels_export.FORMATS:
        return Response(
            {'error': f'Format inconnu : {fmt}.', 'formats': list(referentiels_export.FORMATS)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    entree = _entree(slug)
    modele = modele_de(entree)
    champs = champs_du_modele(modele)

    identifiants, erreur = _ids(request)
    if erreur:
        return Response({'error': erreur}, status=status.HTTP_400_BAD_REQUEST)
    queryset = _perimetre(modele, request)
    if identifiants:
        connus = set(queryset.filter(pk__in=identifiants).values_list('pk', flat=True))
        inconnus = [identifiant for identifiant in identifiants if identifiant not in connus]
        if inconnus:
            return Response(
                {'error': 'Valeur(s) introuvable(s) : ' + ', '.join(map(str, inconnus)) + '.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        queryset = queryset.filter(pk__in=identifiants)

    logger.info(
        'Export référentiel %s (%s, %s ligne(s)) par %s',
        slug, fmt, queryset.count(), request.user,
    )
    return referentiels_export.reponse_export(
        queryset.order_by('pk'), champs, fmt, slug, modele=modele,
        filtres=_description_perimetre(request),
    )


def _description_perimetre(request):
    morceaux = []
    for cle, etiquette in (('actif', 'actif'), ('archives', 'archives incluses'),
                           ('ids', 'sélection')):
        valeur = (request.query_params.get(cle) or '').strip()
        if valeur:
            morceaux.append(f'{etiquette} = {valeur}')
    return ', '.join(morceaux)


@extend_schema(responses={200: OpenApiTypes.BINARY, 400: ErreurGestionSerializer, 404: None})
@api_view(['GET'])
@permission_classes([IsAuthenticated, ReferentielPermission])
def referentiel_modele_import(request, slug, fmt):
    """Fichier modèle d'import (CSV ou XLSX) du référentiel courant."""
    if fmt not in ('csv', 'xlsx'):
        return Response(
            {'error': 'Le modèle n’existe qu’en CSV ou XLSX.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    entree = _entree(slug, ecriture=True)
    modele = modele_de(entree)
    contenu = referentiels_import.modele(slug, champs_du_modele(modele), fmt)
    reponse = HttpResponse(contenu, content_type=tableaux_export.CONTENT_TYPES[fmt])
    reponse['Content-Disposition'] = f'attachment; filename="modele-import-{slug}.{fmt}"'
    reponse['Cache-Control'] = 'private, no-store'
    return reponse


# ── Import ──────────────────────────────────────────────────────────────────
@extend_schema(
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: None},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, ReferentielPermission])
@parser_classes([MultiPartParser, FormParser])
def referentiel_import(request, slug):
    """Import en deux temps : ``mode=apercu`` (défaut) puis ``mode=importer``."""
    entree = _entree(slug, ecriture=True)
    modele = modele_de(entree)
    champs = champs_du_modele(modele)

    if 'fichier' not in request.FILES:
        return Response(
            {'error': 'Aucun fichier reçu (champ « fichier »).'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    fichier = request.FILES['fichier']
    mode = (request.data.get('mode') or 'apercu').strip().lower()
    if mode not in ('apercu', 'importer'):
        return Response(
            {'error': 'Mode inconnu : utilisez « apercu » ou « importer ».'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        lignes, inconnues = referentiels_import.lire(slug, champs, fichier.name, fichier.read())
    except referentiels_import.FichierInvalide as erreur:
        return Response({'error': str(erreur)}, status=status.HTTP_400_BAD_REQUEST)

    analyse = referentiels_import.analyser(slug, modele, champs, lignes, inconnues)
    if mode == 'apercu':
        return Response(referentiels_import.rapport(analyse, nom_fichier=fichier.name))

    if not analyse['importable']:
        donnees = referentiels_import.rapport(analyse, nom_fichier=fichier.name)
        donnees['error'] = (
            f'Import refusé : {analyse["resume"]["rejets"]} ligne(s) invalide(s). '
            'Corrigez le fichier puis relancez l’import.'
        )
        return Response(donnees, status=status.HTTP_400_BAD_REQUEST)

    try:
        ecrits = referentiels_import.appliquer(analyse['plan'])
    except referentiels_import.PlanInvalide as erreur:
        return Response({'error': str(erreur)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as erreur:  # pragma: no cover - contrainte inattendue
        logger.exception('Import référentiel %s échoué', slug)
        return Response(
            {'error': f'Import annulé, aucune ligne enregistrée : {erreur}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    logger.info(
        'Import référentiel %s : %s création(s), %s mise(s) à jour par %s',
        slug, analyse['resume']['creations'], analyse['resume']['mises_a_jour'], request.user,
    )
    donnees = referentiels_import.rapport(analyse, ecrits=ecrits, nom_fichier=fichier.name)
    donnees['message'] = (
        f"{analyse['resume']['creations']} création(s) et "
        f"{analyse['resume']['mises_a_jour']} mise(s) à jour appliquée(s)."
    )
    return Response(donnees)


# ── Retrait par lot ─────────────────────────────────────────────────────────
@extend_schema(
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, ReferentielPermission])
def referentiel_supprimer(request, slug):
    """Retire plusieurs valeurs : archivage si possible, sinon désactivation.

    La suppression physique est interdite par le socle (règle 2) : la valeur
    quitte les listes actives mais reste consultable et réactivable. Le bilan
    indique, pour chaque identifiant, le mode appliqué ou le motif du refus.
    """
    entree = _entree(slug, ecriture=True)
    modele = modele_de(entree)
    concrets = {champ.name for champ in modele._meta.concrete_fields}

    ids = request.data.get('ids')
    if isinstance(ids, str):
        ids = [morceau for morceau in ids.split(',') if morceau.strip()]
    if not isinstance(ids, (list, tuple)) or not ids:
        return Response(
            {'error': 'Fournir une liste « ids » non vide.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        ids = sorted({int(identifiant) for identifiant in ids})
    except (TypeError, ValueError):
        return Response(
            {'error': 'Les identifiants doivent être numériques.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    objets = {obj.pk: obj for obj in modele._default_manager.filter(pk__in=ids)}
    introuvables = [identifiant for identifiant in ids if identifiant not in objets]
    supprimees, bloquees = [], []

    for identifiant in ids:
        obj = objets.get(identifiant)
        if obj is None:
            continue
        libelle = str(obj)
        if 'archive' in concrets:
            if obj.archive:
                bloquees.append({
                    'id': identifiant, 'libelle': libelle,
                    'motif': 'déjà retirée (archivée) : aucune action nécessaire.',
                })
                continue
            obj.archiver(request.user, motif='retrait par lot depuis la liste')
            mode_retrait = 'archivage'
        elif 'actif' in concrets:
            if not obj.actif:
                bloquees.append({
                    'id': identifiant, 'libelle': libelle,
                    'motif': 'déjà désactivée : aucune action nécessaire.',
                })
                continue
            obj.actif = False
            obj.save(update_fields=['actif'])
            mode_retrait = 'désactivation'
        else:
            bloquees.append({
                'id': identifiant, 'libelle': libelle,
                'motif': 'ce référentiel ne porte ni archivage ni activation.',
            })
            continue
        supprimees.append({'id': identifiant, 'libelle': libelle, 'mode': mode_retrait})

    if supprimees:
        logger.info(
            'Retrait référentiel %s par %s : %s',
            slug, request.user, ', '.join(str(element['id']) for element in supprimees),
        )

    bilan = {
        'ressource': slug,
        'mode': supprimees[0]['mode'] if supprimees else None,
        'supprimees': supprimees,
        'bloquees': bloquees,
        'introuvables': introuvables,
        'resume': {
            'demandees': len(ids),
            'supprimees': len(supprimees),
            'bloquees': len(bloquees),
            'introuvables': len(introuvables),
        },
    }
    if supprimees:
        return Response(bilan)
    bilan['error'] = (
        'Aucune valeur retirée : '
        + ('valeur(s) introuvable(s).' if not bloquees else 'les valeurs sélectionnées étaient déjà retirées.')
    )
    return Response(bilan, status=status.HTTP_409_CONFLICT)


__all__ = [
    'champs_du_modele', 'referentiel_export', 'referentiel_import',
    'referentiel_modele_import', 'referentiel_supprimer',
]
