"""Versions, comparaison et restauration des rôles (Lot B, additif).

Même garde que la console CURP (:data:`GARDE` = drapeau
``flag.curp_ui_admin`` + trio d'administration de l'habilitation).
"""
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from habilitations.models import RoleMetier
from habilitations.permissions import ExigeDrapeauAdmin
from habilitations.services import versions_roles as svc

GARDE = [IsAuthenticated, ExigeDrapeauAdmin]


def _serialiser_version(version):
    """Forme JSON d'une version pour les écrans."""
    return {
        'numero': version.numero,
        'instant': version.instant.isoformat(),
        'auteur': (
            version.auteur.get_username() if version.auteur_id else ''
        ),
        'motif': version.motif,
        'source': version.source,
        'source_libelle': version.get_source_display(),
        'donnees': version.donnees,
    }


class RoleVersionsView(APIView):
    """GET/POST /api/habilitations/roles/<code>/versions/"""

    permission_classes = GARDE

    def get(self, request, code):
        role = RoleMetier.objects.filter(code=code).first()
        if role is None:
            return Response({'detail': 'Rôle introuvable.'}, status=404)
        versions = role.versions.order_by('-numero')
        return Response({
            'role': role.code,
            'total': versions.count(),
            'versions': [_serialiser_version(v) for v in versions],
        })

    def post(self, request, code):
        role = RoleMetier.objects.filter(code=code).first()
        if role is None:
            return Response({'detail': 'Rôle introuvable.'}, status=404)
        motif = (request.data or {}).get('motif', '').strip()
        if not motif:
            return Response(
                {'motif': 'Un motif est obligatoire pour capturer une version.'},
                status=400,
            )
        version = svc.capturer_version(
            role, auteur=request.user, motif=motif,
        )
        return Response(_serialiser_version(version), status=201)


class RoleVersionRestaurerView(APIView):
    """POST /api/habilitations/roles/<code>/versions/<numero>/restaurer/"""

    permission_classes = GARDE

    def post(self, request, code, numero):
        role = RoleMetier.objects.filter(code=code).first()
        if role is None:
            return Response({'detail': 'Rôle introuvable.'}, status=404)
        motif = (request.data or {}).get('motif', '').strip()
        if not motif:
            return Response(
                {'motif': 'Un motif est obligatoire pour restaurer une version.'},
                status=400,
            )
        version = svc.restaurer_version(
            role, numero, auteur=request.user, motif=motif,
        )
        return Response(_serialiser_version(version))


class RoleComparerView(APIView):
    """GET /api/habilitations/roles/<code>/comparer/

    Deux modes exclusifs :
    - ``?avec=<code>``  : comparaison de deux rôles du référentiel ;
    - ``?de=N&vers=M``  : comparaison de deux versions du même rôle.
    """

    permission_classes = GARDE

    def get(self, request, code):
        role = RoleMetier.objects.filter(code=code).first()
        if role is None:
            return Response({'detail': 'Rôle introuvable.'}, status=404)
        params = request.query_params
        avec = params.get('avec')
        de, vers = params.get('de'), params.get('vers')
        if avec:
            if RoleMetier.objects.filter(code=avec).count() == 0:
                return Response(
                    {'detail': 'Rôle comparé introuvable.'}, status=404,
                )
            return Response(svc.comparer_roles(code, avec))
        if de and vers:
            try:
                resultat = svc.comparer_versions(role, int(de), int(vers))
            except ValueError:
                return Response(
                    {'detail': 'Numéros de versions invalides.'}, status=400,
                )
            if resultat is None:
                return Response(
                    {'detail': 'Version introuvable.'}, status=404,
                )
            return Response(resultat)
        return Response(
            {'detail': "Fournir '?avec=<code>' ou '?de=N&vers=M'."},
            status=400,
        )
