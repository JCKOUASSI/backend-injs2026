"""API d'organisation administrative (LOT 3).

Directions, départements et services de l'établissement, leur cycle de
vie (création, modification, activation/désactivation), les rattachements
compte ↔ département/service, et la lecture des permissions effectives d'un
compte (rôles actifs + dérogations).

Toutes les routes sont gardées par :class:`ExigeDrapeauAdmin` (drapeau
``flag.curp_ui_admin`` OUVERT et trio d'administration). Chaque geste
mutant est journalisé (``ORGANISATION_MODIFIEE``) ; l'interface ne
confère aucun droit — l'autorisation reste l'apanage du moteur CURP.
"""
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from administrations.models import Departement, Direction
from habilitations.models import CompteUtilisateur
from habilitations.permissions import ExigeDrapeauAdmin
from habilitations.services import comptes_admin as service
from habilitations.services.journalisation import journaliser
from ressources_humaines.models import Service

GARDE = [ExigeDrapeauAdmin]

_CHAMP_COMMUNS = ('libelle', 'description', 'ordre', 'actif')


def _meta(request):
    return {
        'ip': request.META.get('REMOTE_ADDR', ''),
        'ua': request.META.get('HTTP_USER_AGENT', '')[:250],
    }


def _journaliser_orga(request, cible, motif, ancienne_valeur=None,
                      nouvelle_valeur=None):
    meta = _meta(request)
    journaliser(
        'ORGANISATION_MODIFIEE',
        acteur=request.user,
        cible=cible,
        ancienne_valeur=ancienne_valeur,
        nouvelle_valeur=nouvelle_valeur,
        motif=motif,
        adresse_ip=meta['ip'],
        agent_utilisateur=meta['ua'],
    )


# ---------------------------------------------------------------------------
# Sérialisation
# ---------------------------------------------------------------------------
def _ser_direction(direction):
    return {
        'id': direction.id,
        'code': direction.code,
        'libelle': direction.libelle,
        'description': direction.description,
        'ordre': direction.ordre,
        'actif': direction.actif,
        'responsable': (
            {'id': direction.responsable.id,
             'nom': direction.responsable.get_full_name() or direction.responsable.username}
            if direction.responsable_id else None
        ),
        'adjoint': (
            {'id': direction.adjoint.id,
             'nom': direction.adjoint.get_full_name() or direction.adjoint.username}
            if direction.adjoint_id else None
        ),
        'telephone': direction.telephone,
        'email': direction.email,
        'localisation': direction.localisation,
        'nb_departements': direction.departements.count(),
    }


def _ser_departement(departement):
    return {
        'id': departement.id,
        'code': departement.code,
        'libelle': departement.libelle,
        'description': departement.description,
        'direction_id': departement.direction_id,
        'direction': (
            {'id': departement.direction.id, 'libelle': departement.direction.libelle}
            if departement.direction else None
        ),
        'ordre': departement.ordre,
        'actif': departement.actif,
        'responsable': (
            {'id': departement.responsable.id,
             'nom': departement.responsable.get_full_name() or departement.responsable.username}
            if departement.responsable_id else None
        ),
        'adjoint': (
            {'id': departement.adjoint.id,
             'nom': departement.adjoint.get_full_name() or departement.adjoint.username}
            if departement.adjoint_id else None
        ),
        'telephone': departement.telephone,
        'email': departement.email,
        'localisation': departement.localisation,
        'nb_services': departement.services.count(),
        'nb_comptes': departement.comptes.count()
        if hasattr(departement, 'comptes') else 0,
    }


def _ser_service(service_):
    return {
        'id': service_.id,
        'nom': service_.nom,
        'description': service_.description,
        'departement_id': service_.departement_id,
        'departement': (
            {
                'id': service_.departement.id,
                'code': service_.departement.code,
                'libelle': service_.departement.libelle,
            }
            if service_.departement else None
        ),
        'actif': service_.actif,
        'responsable': (
            {'id': service_.responsable.id,
             'nom': service_.responsable.get_full_name() or service_.responsable.username}
            if service_.responsable_id else None
        ),
        'adjoint': (
            {'id': service_.adjoint.id,
             'nom': service_.adjoint.get_full_name() or service_.adjoint.username}
            if service_.adjoint_id else None
        ),
        'telephone': service_.telephone,
        'email': service_.email,
        'localisation': service_.localisation,
        'code': service_.code,
        'nb_comptes': service_.comptes.count()
        if hasattr(service_, 'comptes') else 0,
    }


def _ser_compte_bref(compte):
    return {
        'id': compte.id,
        'username': compte.user.username if compte.user else None,
        'personne': (
            f'{compte.personne.prenoms} {compte.personne.nom}'
            if compte.personne else None
        ),
        'statut': compte.statut,
    }


# ---------------------------------------------------------------------------
# Directions
# ---------------------------------------------------------------------------
class DirectionListCreateView(APIView):
    permission_classes = GARDE

    def get(self, request):
        items = Direction.objects.all()
        return Response({'results': [_ser_direction(d) for d in items]})

    @transaction.atomic
    def post(self, request):
        data = request.data
        manquants = [c for c in ('code', 'libelle') if not data.get(c)]
        if manquants:
            return Response(
                {'detail': f'Champs obligatoires manquants : {", ".join(manquants)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        direction = Direction(
            code=str(data['code']).strip(),
            libelle=str(data['libelle']).strip(),
            description=str(data.get('description', '') or ''),
            ordre=int(data.get('ordre', 0) or 0),
            actif=bool(data.get('actif', True)),
        )
        try:
            direction.save()
        except IntegrityError:
            return Response(
                {'detail': f"Le code « {direction.code} » existe déjà."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _journaliser_orga(
            request, direction,
            f"Création de la direction {direction.libelle} ({direction.code}).",
            nouvelle_valeur='créée',
        )
        return Response(_ser_direction(direction), status=status.HTTP_201_CREATED)


class DirectionDetailView(APIView):
    permission_classes = GARDE

    def _get(self, request, pk):
        return Direction.objects.filter(pk=pk).first()

    def get(self, request, pk):
        direction = self._get(request, pk)
        if direction is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({
            **_ser_direction(direction),
            'departements': [
                _ser_departement(d) for d in direction.departements.all()
            ],
        })

    @transaction.atomic
    def patch(self, request, pk):
        direction = self._get(request, pk)
        if direction is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        anciennes, nouvelles = {}, {}
        for champ in _CHAMP_COMMUNS:
            if champ in request.data:
                anciennes[champ] = getattr(direction, champ)
                if champ == 'ordre':
                    direction.ordre = int(request.data[champ] or 0)
                elif champ == 'actif':
                    direction.actif = bool(request.data[champ])
                else:
                    setattr(direction, champ, str(request.data[champ] or ''))
                nouvelles[champ] = getattr(direction, champ)
        if not nouvelles:
            return Response(
                {'detail': 'Aucun champ modifiable fourni.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        direction.save()
        _journaliser_orga(
            request, direction,
            f"Modification de la direction {direction.libelle}.",
            ancienne_valeur=anciennes,
            nouvelle_valeur=nouvelles,
        )
        return Response(_ser_direction(direction))


# ---------------------------------------------------------------------------
# Départements
# ---------------------------------------------------------------------------
class DepartementListCreateView(APIView):
    permission_classes = GARDE

    def get(self, request):
        qs = Departement.objects.select_related('direction').all()
        direction_id = request.query_params.get('direction')
        if direction_id:
            qs = qs.filter(direction_id=direction_id)
        return Response({'results': [_ser_departement(d) for d in qs]})

    @transaction.atomic
    def post(self, request):
        data = request.data
        manquants = [c for c in ('code', 'libelle') if not data.get(c)]
        if manquants:
            return Response(
                {'detail': f'Champs obligatoires manquants : {", ".join(manquants)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        direction_id = data.get('direction')
        direction = None
        if direction_id:
            direction = Direction.objects.filter(pk=direction_id).first()
            if direction is None:
                return Response(
                    {'detail': f"Direction inconnue (id={direction_id})."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        departement = Departement(
            code=str(data['code']).strip(),
            libelle=str(data['libelle']).strip(),
            description=str(data.get('description', '') or ''),
            direction=direction,
            ordre=int(data.get('ordre', 0) or 0),
            actif=bool(data.get('actif', True)),
        )
        try:
            departement.save()
        except IntegrityError:
            return Response(
                {'detail': f"Le code « {departement.code} » existe déjà."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _journaliser_orga(
            request, departement,
            f"Création du département {departement.libelle} ({departement.code}).",
            nouvelle_valeur='créé',
        )
        return Response(_ser_departement(departement), status=status.HTTP_201_CREATED)


class DepartementDetailView(APIView):
    permission_classes = GARDE

    def _get(self, request, pk):
        return Departement.objects.select_related('direction').filter(pk=pk).first()

    def get(self, request, pk):
        departement = self._get(request, pk)
        if departement is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({
            **_ser_departement(departement),
            'services': [
                _ser_service(s) for s in departement.services.all()
            ],
            'comptes': [
                _ser_compte_bref(c)
                for c in CompteUtilisateur.objects.filter(
                    departements=departement
                ).select_related('user', 'personne')
            ],
        })

    @transaction.atomic
    def patch(self, request, pk):
        departement = self._get(request, pk)
        if departement is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        anciennes, nouvelles = {}, {}
        for champ in _CHAMP_COMMUNS:
            if champ in request.data:
                anciennes[champ] = getattr(departement, champ)
                if champ == 'ordre':
                    departement.ordre = int(request.data[champ] or 0)
                elif champ == 'actif':
                    departement.actif = bool(request.data[champ])
                else:
                    setattr(departement, champ, str(request.data[champ] or ''))
                nouvelles[champ] = getattr(departement, champ)
        if 'direction' in request.data:
            direction_id = request.data['direction']
            anciennes['direction'] = departement.direction_id
            if direction_id:
                direction = Direction.objects.filter(pk=direction_id).first()
                if direction is None:
                    return Response(
                        {'detail': f"Direction inconnue (id={direction_id})."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                departement.direction = direction
            else:
                departement.direction = None
            nouvelles['direction'] = departement.direction_id
        if not nouvelles:
            return Response(
                {'detail': 'Aucun champ modifiable fourni.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            departement.save()
        except IntegrityError:
            return Response(
                {'detail': f"Le code « {departement.code} » existe déjà."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _journaliser_orga(
            request, departement,
            f"Modification du département {departement.libelle}.",
            ancienne_valeur=anciennes,
            nouvelle_valeur=nouvelles,
        )
        return Response(_ser_departement(departement))


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
class ServiceListCreateView(APIView):
    permission_classes = GARDE

    def get(self, request):
        qs = Service.objects.select_related('departement').all()
        departement_id = request.query_params.get('departement')
        if departement_id:
            qs = qs.filter(departement_id=departement_id)
        q = request.query_params.get('q')
        if q:
            qs = qs.filter(nom__icontains=q)
        return Response({'results': [_ser_service(s) for s in qs]})

    @transaction.atomic
    def post(self, request):
        data = request.data
        nom = str(data.get('nom', '') or '').strip()
        if not nom:
            return Response(
                {'detail': 'Champ obligatoire manquant : nom.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        departement_id = data.get('departement')
        departement = None
        if departement_id:
            departement = Departement.objects.filter(pk=departement_id).first()
            if departement is None:
                return Response(
                    {'detail': f"Département inconnu (id={departement_id})."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        service_ = Service(
            nom=nom,
            description=str(data.get('description', '') or ''),
            departement=departement,
            actif=bool(data.get('actif', True)),
        )
        try:
            service_.save()
        except IntegrityError:
            return Response(
                {'detail': f"Le service « {nom} » existe déjà."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _journaliser_orga(
            request, service_,
            f"Création du service {nom}.",
            nouvelle_valeur='créé',
        )
        return Response(_ser_service(service_), status=status.HTTP_201_CREATED)


class ServiceDetailView(APIView):
    permission_classes = GARDE

    def _get(self, request, pk):
        return Service.objects.select_related('departement').filter(pk=pk).first()

    def get(self, request, pk):
        service_ = self._get(request, pk)
        if service_ is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({
            **_ser_service(service_),
            'comptes': [
                _ser_compte_bref(c)
                for c in CompteUtilisateur.objects.filter(
                    services=service_
                ).select_related('user', 'personne')
            ],
        })

    @transaction.atomic
    def patch(self, request, pk):
        service_ = self._get(request, pk)
        if service_ is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        anciennes, nouvelles = {}, {}
        for champ in ('nom', 'description', 'actif'):
            if champ in request.data:
                anciennes[champ] = getattr(service_, champ)
                if champ == 'actif':
                    service_.actif = bool(request.data[champ])
                else:
                    setattr(service_, champ, str(request.data[champ] or ''))
                nouvelles[champ] = getattr(service_, champ)
        if 'departement' in request.data:
            departement_id = request.data['departement']
            anciennes['departement'] = service_.departement_id
            if departement_id:
                departement = Departement.objects.filter(pk=departement_id).first()
                if departement is None:
                    return Response(
                        {'detail': f"Département inconnu (id={departement_id})."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                service_.departement = departement
            else:
                service_.departement = None
            nouvelles['departement'] = service_.departement_id
        if not nouvelles:
            return Response(
                {'detail': 'Aucun champ modifiable fourni.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            service_.save()
        except IntegrityError:
            return Response(
                {'detail': f"Le service « {service_.nom} » existe déjà."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _journaliser_orga(
            request, service_,
            f"Modification du service {service_.nom}.",
            ancienne_valeur=anciennes,
            nouvelle_valeur=nouvelles,
        )
        return Response(_ser_service(service_))


# ---------------------------------------------------------------------------
# Rattachements compte ↔ département / service
# ---------------------------------------------------------------------------
class DepartementComptesView(APIView):
    """Rattache ou détache des comptes d'un département (M2M du compte)."""

    permission_classes = GARDE

    def _get(self, request, pk):
        return Departement.objects.filter(pk=pk).first()

    def _rattacher(self, request, pk, retirer):
        departement = self._get(request, pk)
        if departement is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        compte_id = request.data.get('compte_id')
        if not compte_id:
            return Response(
                {'detail': 'Champ obligatoire manquant : compte_id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        compte = CompteUtilisateur.objects.filter(pk=compte_id).first()
        if compte is None:
            return Response(
                {'detail': f"Compte inconnu (id={compte_id})."},
                status=status.HTTP_404_NOT_FOUND,
            )
        motif = (
            f"Rattachement du compte {compte.user.username if compte.user else compte.pk} "
            f"au département {departement.libelle}."
            if not retirer
            else f"Détachement du compte {compte.user.username if compte.user else compte.pk} "
                 f"du département {departement.libelle}."
        )
        if retirer:
            compte.departements.remove(departement)
        else:
            compte.departements.add(departement)
        _journaliser_orga(request, departement, motif)
        return Response({
            'detail': 'OK',
            'compte_id': compte.id,
            'departement_id': departement.id,
            'comptes': [
                _ser_compte_bref(c)
                for c in CompteUtilisateur.objects.filter(
                    departements=departement
                ).select_related('user', 'personne')
            ],
        })

    def post(self, request, pk):
        return self._rattacher(request, pk, retirer=False)

    def delete(self, request, pk):
        return self._rattacher(request, pk, retirer=True)


class ServiceComptesView(APIView):
    """Rattache ou détache des comptes d'un service (M2M du compte)."""

    permission_classes = GARDE

    def _get(self, request, pk):
        return Service.objects.filter(pk=pk).first()

    def _rattacher(self, request, pk, retirer):
        service_ = self._get(request, pk)
        if service_ is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        compte_id = request.data.get('compte_id')
        if not compte_id:
            return Response(
                {'detail': 'Champ obligatoire manquant : compte_id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        compte = CompteUtilisateur.objects.filter(pk=compte_id).first()
        if compte is None:
            return Response(
                {'detail': f"Compte inconnu (id={compte_id})."},
                status=status.HTTP_404_NOT_FOUND,
            )
        libelle = compte.user.username if compte.user else compte.pk
        motif = (
            f"Rattachement du compte {libelle} au service {service_.nom}."
            if not retirer
            else f"Détachement du compte {libelle} du service {service_.nom}."
        )
        if retirer:
            compte.services.remove(service_)
        else:
            compte.services.add(service_)
        _journaliser_orga(request, service_, motif)
        return Response({
            'detail': 'OK',
            'compte_id': compte.id,
            'service_id': service_.id,
            'comptes': [
                _ser_compte_bref(c)
                for c in CompteUtilisateur.objects.filter(
                    services=service_
                ).select_related('user', 'personne')
            ],
        })

    def post(self, request, pk):
        return self._rattacher(request, pk, retirer=False)

    def delete(self, request, pk):
        return self._rattacher(request, pk, retirer=True)


# ---------------------------------------------------------------------------
# Permissions effectives d'un compte
# ---------------------------------------------------------------------------
class ComptePermissionsEffectivesView(APIView):
    """Codes de permissions effectivement détenus par un compte.

    Combine les rôles actifs (selon les périmètres et échéances) et les
    dérogations actives (OCTROIS ajoutés, RETRAITS soustraits), conformément
    au service ``habilitations.services.comptes_admin.permissions_effectives``.
    Lecture seule ; ne modifie aucun droit.
    """

    permission_classes = GARDE

    def get(self, request, pk):
        compte = (
            CompteUtilisateur.objects
            .select_related('user', 'personne')
            .filter(pk=pk)
            .first()
        )
        if compte is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        codes = service.permissions_effectives(compte)
        return Response({
            'compte_id': compte.id,
            'username': compte.user.username if compte.user else None,
            'codes': sorted(codes),
            'count': len(codes),
        })
