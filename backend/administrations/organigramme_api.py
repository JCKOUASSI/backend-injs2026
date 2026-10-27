"""Organigramme unifié — Directions / Départements / Services / Secrétariats.

Modèle fonctionnel de référence, MODULE 13 (§13.1-13.8) et §15 : « un secrétariat
est rattaché à une structure ». Cette API expose la structure hiérarchique de
l'établissement comme un seul objet lisible (arbre) et éditable unité par unité.

Principes (garde-fous du rapport de mise en œuvre) :

- **Additif** : les entités existantes (``administrations.Direction``,
  ``administrations.Departement``, ``ressources_humaines.Service``,
  ``formations.Secretariat``) sont enrichies, jamais remplacées ; la console
  d'habilitations (``/api/habilitations/…/organisation``) garde ses routes.
- **Suppression = désactivation** : ``DELETE`` bascule ``actif`` à ``False``
  (une unité disparaît des listes, l'historique reste intact ; la purge
  physique relève de l'administration Django).
- **Traçabilité** : chaque écriture est journalisée dans la chaîne immuable
  ``habilitations.services.journalisation.journaliser`` (mêmes actions
  ``ORGANISATION_*`` que la console CURP), avec motif éventuel.
- **Gating** : lecture = tout compte authentifié (l'organigramme est interne
  mais non confidentiel) ; écriture = direction/direction générale (``IsDFRC``).
"""
from django.db.models import Count, Prefetch, Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.models import User
from authentication.permissions import IsDFRC
from formations.models import RefTypeSecretariat, Secretariat
from habilitations.models import CompteUtilisateur
from habilitations.services.journalisation import journaliser

from .models import Departement, Direction
from ressources_humaines.models import Service

# Champs communs portés par chaque unité (modèle 13.3 : une unité = code,
# libellé, responsable, adjoint, contact, localisation, état).
_UNIT_FIELDS = ('telephone', 'email', 'localisation')


def _ser_user(pk):
    if not pk:
        return None
    u = User.objects.filter(pk=pk).first()
    return None if u is None else {'id': u.id, 'nom': u.get_full_name() or u.username}


def _valider_fk_utilisateur(data, champ):
    """Retourne (value, erreur). data[champ] = id utilisateur ou None."""
    brut = data.get(champ)
    if brut in (None, '', 0):
        return None, None
    try:
        pk = int(brut)
    except (TypeError, ValueError):
        return None, f'« {champ} » : identifiant de compte invalide.'
    if not User.objects.filter(pk=pk).exists():
        return None, f'« {champ} » : compte {pk} inexistant.'
    return pk, None


def _meta(request):
    return (request.META.get('REMOTE_ADDR', ''),
            request.META.get('HTTP_USER_AGENT', '')[:250])


def _journal(request, action, cible, ancienne, nouvelle, motif):
    ip, ua = _meta(request)
    journaliser(
        action, acteur=request.user, cible=cible,
        ancienne_valeur=ancienne, nouvelle_valeur=nouvelle,
        motif=motif or '', adresse_ip=ip, agent_utilisateur=ua,
    )


def _diff(obj, avant, champs):
    apres = {c: getattr(obj, c) for c in champs}
    return {c: (avant.get(c), apres[c]) for c in champs if avant.get(c) != apres[c]}


def _corps(request):
    data = dict(request.data) if hasattr(request.data, 'items') else dict(request.data or {})
    return data


# --------------------------------------------------------------------------
# Sérialisation lecture
# --------------------------------------------------------------------------

def _unit_payload(obj, *, code, libelle, extra=None):
    payload = {
        'id': obj.id,
        'code': code,
        'libelle': libelle,
        'description': obj.description,
        'responsable': _ser_user(obj.responsable_id),
        'adjoint': _ser_user(obj.adjoint_id),
        'telephone': obj.telephone,
        'email': obj.email,
        'localisation': obj.localisation,
        'actif': obj.actif,
    }
    if extra:
        payload.update(extra)
    return payload


def _effectif_comptes(unite):
    """Comptes CURP rattachés à l'unité (§13.8 « effectifs = comptes ayant accès »)."""
    if isinstance(unite, Direction):
        return CompteUtilisateur.objects.filter(departements__direction=unite).distinct().count()
    if isinstance(unite, Departement):
        return CompteUtilisateur.objects.filter(departements=unite).distinct().count()
    if isinstance(unite, Service):
        return CompteUtilisateur.objects.filter(services=unite).distinct().count()
    return User.objects.filter(secretariat=unite, is_active=True).count()


def ser_direction(d, **kw):
    return _unit_payload(d, code=d.code, libelle=d.libelle, extra={
        'ordre': d.ordre,
        'nb_departements': d.departements.count(),
        'nb_secretariats': d.secretariats.count(),
        'effectif': _effectif_comptes(d),
    }, **kw)


def ser_departement(d, **kw):
    return _unit_payload(d, code=d.code, libelle=d.libelle, extra={
        'ordre': d.ordre,
        'direction': d.direction_id,
        'direction_libelle': d.direction.libelle if d.direction_id else '',
        'nb_services': d.services.count(),
        'nb_secretariats': d.secretariats.count(),
        'effectif': _effectif_comptes(d),
    }, **kw)


def ser_service(s, **kw):
    return _unit_payload(s, code=s.code, libelle=s.nom, extra={
        'nom': s.nom,
        'departement': s.departement_id,
        'departement_libelle': s.departement.libelle if s.departement_id else '',
        'effectif': _effectif_comptes(s),
        # Modèle 13.4 : unité feuille typée et imbriquable (bureau/unité/cellule
        # rattachés à un service) — la hiérarchie n'est pas codée en dur.
        'type_unite': s.type_unite,
        'parent': s.parent_id,
        'parent_libelle': s.parent.nom if s.parent_id else '',
        'nb_sous_unites': s.sous_unites.count(),
    }, **kw)


def _valider_parent_service(parent_id, soi=None):
    """Existence du parent + refus de cycle (aucun niveau n'est figé : la
    validation borne la profondeur et garantit l'absence de boucle)."""
    if parent_id in (None, '', 0):
        return None, None
    vus = {soi} if soi else set()
    chaine = set()
    cur = parent_id
    for _ in range(30):
        if cur is None:
            return None, None
        if cur in vus:
            return None, 'Rattachement circulaire refusé : une unité ne peut pas se contenir elle-même.'
        vus.add(cur)
        if cur in chaine:
            return None, 'Rattachement circulaire refusé : une unité ne peut pas se contenir elle-même.'
        chaine.add(cur)
        if not Service.objects.filter(pk=cur).exists():
            return None, 'Unité parente inconnue.'
        cur = Service.objects.filter(pk=cur).values_list('parent_id', flat=True).first()
    return None, 'Chaîne de rattachement trop longue (30 niveaux maximum).'


def ser_secretariat(s, **kw):
    return {
        'id': s.id,
        'numero': s.numero,
        'nom': s.nom,
        'libelle': s.nom,
        'description': s.description,
        'type': s.type_id,
        'type_libelle': s.type.libelle if s.type_id else '',
        'responsable': _ser_user(s.responsable_id),
        'adjoint': _ser_user(s.adjoint_id),
        'telephone': s.telephone,
        'email': s.email,
        'localisation': s.localisation,
        'direction': s.direction_id,
        'direction_libelle': s.direction.libelle if s.direction_id else '',
        'departement': s.departement_id,
        'departement_libelle': s.departement.libelle if s.departement_id else '',
        'actif': s.actif,
        'nb_participants': s.nb_participants,
        'nb_modules': s.nb_modules,
    }


# --------------------------------------------------------------------------
# Arbre complet (§13.4 : INJS → Directions → Départements → Services)
# --------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def arbre(request):
    """Arbre hiérarchique, ouverts incluant les unités désactivées si ``?inactifs=1``."""
    show_inactive = request.query_params.get('inactifs') == '1'
    etat = Q() if show_inactive else Q(actif=True)
    directions = list(Direction.objects.filter(etat)
                      .prefetch_related(
                          Prefetch('departements',
                                   queryset=Departement.objects.filter(etat)
                                   .prefetch_related('services', 'secretariats')),
                          'secretariats'))
    # Sous-unités (bureaux / unités / cellules) greffées récursivement sous leur
    # service parent ; seul un service sans parent chapeaute un département.
    pool = {s.id: s for s in Service.objects.filter(etat)}
    enfants = {}
    for s in pool.values():
        if s.parent_id in pool:
            enfants.setdefault(s.parent_id, []).append(s)

    def _noeud(s):
        return {**ser_service(s), 'sous_unites': [_noeud(e) for e in enfants.get(s.id, [])]}

    nodes = []
    seen_dep = set()
    for d in directions:
        dep_nodes = []
        for dep in d.departements.all():
            seen_dep.add(dep.id)
            dep_nodes.append({
                **ser_departement(dep),
                'services': [_noeud(s) for s in dep.services.filter(etat, parent__isnull=True)],
                'secretariats': [ser_secretariat(s) for s in dep.secretariats.all()
                                 if show_inactive or s.actif],
            })
        nodes.append({
            **ser_direction(d),
            'departements': dep_nodes,
            'secretariats': [ser_secretariat(s) for s in d.secretariats.all()
                             if show_inactive or s.actif],
        })
    orphelins = {
        'departements': [ser_departement(dep) for dep in
                         Departement.objects.filter(etat, direction__isnull=True)
                         if dep.id not in seen_dep],
        'services': [_noeud(s) for s in
                     Service.objects.filter(etat, departement__isnull=True,
                                            parent__isnull=True)],
        'secretariats': [ser_secretariat(s) for s in Secretariat.objects.all()
                         if (show_inactive or s.actif)
                         and s.direction_id is None and s.departement_id is None],
    }
    return Response({'directions': nodes, 'non_rattaches': orphelins})


# --------------------------------------------------------------------------
# Mécanique CRUD commune
# --------------------------------------------------------------------------

def _filtre_liste(request):
    qs = request.queryset_model.objects.all()
    if request.query_params.get('actif') in ('0', '1'):
        qs = qs.filter(actif=request.query_params['actif'] == '1')
    q = (request.query_params.get('q') or '').strip()
    if q:
        champs = getattr(request, 'search_fields', ('libelle', 'code'))
        cond = Q()
        for champ in champs:
            cond |= Q(**{f'{champ}__icontains': q})
        qs = qs.filter(cond)
    return qs


def _ecoute_bool(data, cle, defaut=True):
    brut = data.get(cle, defaut)
    if isinstance(brut, str):
        return brut.strip().lower() not in ('0', 'false', 'non', '')
    return bool(brut)


# ---- Directions -----------------------------------------------------------

def _direction_get(pk):
    return Direction.objects.filter(pk=pk).first()


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def directions(request):
    if request.method == 'GET':
        request.queryset_model = Direction
        request.search_fields = ('libelle', 'code', 'description')
        return Response([ser_direction(d) for d in _filtre_liste(request)])
    if not IsDFRC().has_permission(request, None):
        return Response({'detail': 'Seule la direction (DFRC) modifie l’organigramme.'}, status=403)
    data = _corps(request)
    code = (data.get('code') or '').strip()
    libelle = (data.get('libelle') or '').strip()
    if not code or not libelle:
        return Response({'detail': '« code » et « libellé » sont requis.'}, status=400)
    if Direction.objects.filter(code=code).exists():
        return Response({'detail': f'Le code « {code} » est déjà utilisé.'}, status=400)
    resp, err = _valider_fk_utilisateur(data, 'responsable_id')
    if err:
        return Response({'detail': err}, status=400)
    adj, err = _valider_fk_utilisateur(data, 'adjoint_id')
    if err:
        return Response({'detail': err}, status=400)
    obj = Direction.objects.create(
        code=code, libelle=libelle,
        description=data.get('description') or '',
        ordre=int(data.get('ordre') or 0),
        responsable_id=resp, adjoint_id=adj,
        telephone=(data.get('telephone') or '').strip()[:30],
        email=(data.get('email') or '').strip(),
        localisation=(data.get('localisation') or '').strip()[:150],
        actif=_ecoute_bool(data, 'actif'),
    )
    _journal(request, 'ORGANISATION_CREEE', obj, None, {'code': obj.code, 'libelle': obj.libelle},
             data.get('motif'))
    return Response(ser_direction(obj), status=201)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def direction_detail(request, pk):
    obj = _direction_get(pk)
    if obj is None:
        return Response({'detail': 'Direction introuvable.'}, status=404)
    if request.method == 'GET':
        return Response(ser_direction(obj))
    data = _corps(request)
    if request.method == 'DELETE':
        if obj.actif:
            obj.actif = False
            obj.save(update_fields=['actif', 'updated_at'])
            _journal(request, 'ORGANISATION_DESACTIVEE', obj, {'actif': True}, {'actif': False},
                     data.get('motif') or request.query_params.get('motif'))
        return Response(status=204)
    if not IsDFRC().has_permission(request, None):
        return Response({'detail': 'Seule la direction (DFRC) modifie l’organigramme.'}, status=403)
    avant = {c: getattr(obj, c) for c in
             ('code', 'libelle', 'description', 'ordre', 'actif', 'responsable_id', 'adjoint_id') + _UNIT_FIELDS}
    if 'code' in data:
        code = (data.get('code') or '').strip()
        if not code:
            return Response({'detail': '« code » ne peut pas être vide.'}, status=400)
        if Direction.objects.filter(code=code).exclude(pk=obj.pk).exists():
            return Response({'detail': f'Le code « {code} » est déjà utilisé.'}, status=400)
        obj.code = code
    if 'libelle' in data:
        lib = (data.get('libelle') or '').strip()
        if not lib:
            return Response({'detail': '« libellé » ne peut pas être vide.'}, status=400)
        obj.libelle = lib
    for champ in ('description',):
        if champ in data:
            setattr(obj, champ, data.get(champ) or '')
    if 'ordre' in data:
        obj.ordre = int(data.get('ordre') or 0)
    for champ, cible in (('responsable_id', 'responsable_id'), ('adjoint_id', 'adjoint_id')):
        if champ in data:
            val, err = _valider_fk_utilisateur(data, champ)
            if err:
                return Response({'detail': err}, status=400)
            setattr(obj, cible, val)
    for champ in _UNIT_FIELDS:
        if champ in data:
            setattr(obj, champ, (data.get(champ) or '').strip())
    if 'actif' in data:
        obj.actif = _ecoute_bool(data, 'actif')
    obj.save()
    _journal(request, 'ORGANISATION_MODIFIEE', obj, avant,
             _diff(obj, avant, tuple(avant)), data.get('motif'))
    return Response(ser_direction(obj))


# ---- Départements ----------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def departements(request):
    if request.method == 'GET':
        request.queryset_model = Departement
        request.search_fields = ('libelle', 'code', 'description')
        return Response([ser_departement(d) for d in _filtre_liste(request)])
    if not IsDFRC().has_permission(request, None):
        return Response({'detail': 'Seule la direction (DFRC) modifie l’organigramme.'}, status=403)
    data = _corps(request)
    code = (data.get('code') or '').strip()
    libelle = (data.get('libelle') or '').strip()
    if not code or not libelle:
        return Response({'detail': '« code » et « libellé » sont requis.'}, status=400)
    if Departement.objects.filter(code=code).exists():
        return Response({'detail': f'Le code « {code} » est déjà utilisé.'}, status=400)
    direction_id = data.get('direction') or None
    resp, err = _valider_fk_utilisateur(data, 'responsable_id')
    if err:
        return Response({'detail': err}, status=400)
    adj, err = _valider_fk_utilisateur(data, 'adjoint_id')
    if err:
        return Response({'detail': err}, status=400)
    obj = Departement.objects.create(
        code=code, libelle=libelle,
        description=data.get('description') or '',
        direction_id=direction_id, ordre=int(data.get('ordre') or 0),
        responsable_id=resp, adjoint_id=adj,
        telephone=(data.get('telephone') or '').strip()[:30],
        email=(data.get('email') or '').strip(),
        localisation=(data.get('localisation') or '').strip()[:150],
        actif=_ecoute_bool(data, 'actif'),
    )
    _journal(request, 'ORGANISATION_CREEE', obj, None, {'code': obj.code, 'libelle': obj.libelle},
             data.get('motif'))
    return Response(ser_departement(obj), status=201)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def departement_detail(request, pk):
    obj = Departement.objects.filter(pk=pk).first()
    if obj is None:
        return Response({'detail': 'Département introuvable.'}, status=404)
    if request.method == 'GET':
        return Response(ser_departement(obj))
    data = _corps(request)
    if request.method == 'DELETE':
        if obj.actif:
            obj.actif = False
            obj.save(update_fields=['actif', 'updated_at'])
            _journal(request, 'ORGANISATION_DESACTIVEE', obj, {'actif': True}, {'actif': False},
                     data.get('motif') or request.query_params.get('motif'))
        return Response(status=204)
    if not IsDFRC().has_permission(request, None):
        return Response({'detail': 'Seule la direction (DFRC) modifie l’organigramme.'}, status=403)
    avant = {c: getattr(obj, c) for c in
             ('code', 'libelle', 'description', 'ordre', 'actif', 'direction_id',
              'responsable_id', 'adjoint_id') + _UNIT_FIELDS}
    if 'code' in data:
        code = (data.get('code') or '').strip()
        if not code:
            return Response({'detail': '« code » ne peut pas être vide.'}, status=400)
        if Departement.objects.filter(code=code).exclude(pk=obj.pk).exists():
            return Response({'detail': f'Le code « {code} » est déjà utilisé.'}, status=400)
        obj.code = code
    if 'libelle' in data:
        lib = (data.get('libelle') or '').strip()
        if not lib:
            return Response({'detail': '« libellé » ne peut pas être vide.'}, status=400)
        obj.libelle = lib
    if 'direction' in data:
        val = data.get('direction')
        if val in (None, '', 0):
            obj.direction = None
        else:
            if not Direction.objects.filter(pk=val).exists():
                return Response({'detail': 'Direction de rattachement inconnue.'}, status=400)
            obj.direction_id = int(val)
    for champ in ('description',):
        if champ in data:
            setattr(obj, champ, data.get(champ) or '')
    if 'ordre' in data:
        obj.ordre = int(data.get('ordre') or 0)
    for champ in ('responsable_id', 'adjoint_id'):
        if champ in data:
            val, err = _valider_fk_utilisateur(data, champ)
            if err:
                return Response({'detail': err}, status=400)
            setattr(obj, champ, val)
    for champ in _UNIT_FIELDS:
        if champ in data:
            setattr(obj, champ, (data.get(champ) or '').strip())
    if 'actif' in data:
        obj.actif = _ecoute_bool(data, 'actif')
    obj.save()
    _journal(request, 'ORGANISATION_MODIFIEE', obj, avant,
             _diff(obj, avant, tuple(avant)), data.get('motif'))
    return Response(ser_departement(obj))


# ---- Services ---------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def services(request):
    if request.method == 'GET':
        request.queryset_model = Service
        request.search_fields = ('nom', 'code', 'description')
        return Response([ser_service(s) for s in _filtre_liste(request)])
    if not IsDFRC().has_permission(request, None):
        return Response({'detail': 'Seule la direction (DFRC) modifie l’organigramme.'}, status=403)
    data = _corps(request)
    nom = (data.get('nom') or data.get('libelle') or '').strip()
    if not nom:
        return Response({'detail': '« nom » est requis.'}, status=400)
    if Service.objects.filter(nom=nom).exists():
        return Response({'detail': f'Le service « {nom} » existe déjà.'}, status=400)
    resp, err = _valider_fk_utilisateur(data, 'responsable_id')
    if err:
        return Response({'detail': err}, status=400)
    adj, err = _valider_fk_utilisateur(data, 'adjoint_id')
    if err:
        return Response({'detail': err}, status=400)
    type_unite = (data.get('type_unite') or 'SERVICE').upper()
    if type_unite not in Service.TypeUnite.values:
        return Response({'detail': 'Type d’unité inconnu (SERVICE, BUREAU, UNITE, CELLULE, AUTRE).'}, status=400)
    _, err = _valider_parent_service(data.get('parent'))
    if err:
        return Response({'detail': err}, status=400)
    obj = Service.objects.create(
        nom=nom, code=(data.get('code') or '').strip()[:30],
        description=data.get('description') or '',
        departement_id=data.get('departement') or None,
        type_unite=type_unite, parent_id=data.get('parent') or None,
        responsable_id=resp, adjoint_id=adj,
        telephone=(data.get('telephone') or '').strip()[:30],
        email=(data.get('email') or '').strip(),
        localisation=(data.get('localisation') or '').strip()[:150],
        actif=_ecoute_bool(data, 'actif'),
    )
    _journal(request, 'ORGANISATION_CREEE', obj, None, {'code': obj.code, 'libelle': obj.nom},
             data.get('motif'))
    return Response(ser_service(obj), status=201)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def service_detail(request, pk):
    obj = Service.objects.filter(pk=pk).first()
    if obj is None:
        return Response({'detail': 'Service introuvable.'}, status=404)
    if request.method == 'GET':
        return Response(ser_service(obj))
    data = _corps(request)
    if request.method == 'DELETE':
        if obj.actif:
            obj.actif = False
            obj.save(update_fields=['actif'])
            _journal(request, 'ORGANISATION_DESACTIVEE', obj, {'actif': True}, {'actif': False},
                     data.get('motif') or request.query_params.get('motif'))
        return Response(status=204)
    if not IsDFRC().has_permission(request, None):
        return Response({'detail': 'Seule la direction (DFRC) modifie l’organigramme.'}, status=403)
    avant = {c: getattr(obj, c) for c in
             ('nom', 'code', 'description', 'actif', 'departement_id',
              'type_unite', 'parent_id', 'responsable_id', 'adjoint_id') + _UNIT_FIELDS}
    if 'nom' in data or 'libelle' in data:
        nom = (data.get('nom') or data.get('libelle') or '').strip()
        if not nom:
            return Response({'detail': '« nom » ne peut pas être vide.'}, status=400)
        if Service.objects.filter(nom=nom).exclude(pk=obj.pk).exists():
            return Response({'detail': f'Le service « {nom} » existe déjà.'}, status=400)
        obj.nom = nom
    if 'type_unite' in data:
        t = (data.get('type_unite') or 'SERVICE').upper()
        if t not in Service.TypeUnite.values:
            return Response({'detail': 'Type d’unité inconnu (SERVICE, BUREAU, UNITE, CELLULE, AUTRE).'}, status=400)
        obj.type_unite = t
    if 'parent' in data:
        pid = data.get('parent') or None
        _, err = _valider_parent_service(pid, soi=obj.pk)
        if err:
            return Response({'detail': err}, status=400)
        obj.parent_id = pid
    for champ in ('description',):
        if champ in data:
            setattr(obj, champ, data.get(champ) or '')
    if 'code' in data:
        obj.code = (data.get('code') or '').strip()[:30]
    if 'departement' in data:
        val = data.get('departement')
        if val in (None, '', 0):
            obj.departement = None
        else:
            if not Departement.objects.filter(pk=val).exists():
                return Response({'detail': 'Département de rattachement inconnu.'}, status=400)
            obj.departement_id = int(val)
    for champ in ('responsable_id', 'adjoint_id'):
        if champ in data:
            val, err = _valider_fk_utilisateur(data, champ)
            if err:
                return Response({'detail': err}, status=400)
            setattr(obj, champ, val)
    for champ in _UNIT_FIELDS:
        if champ in data:
            setattr(obj, champ, (data.get(champ) or '').strip())
    if 'actif' in data:
        obj.actif = _ecoute_bool(data, 'actif')
    obj.save()
    _journal(request, 'ORGANISATION_MODIFIEE', obj, avant,
             _diff(obj, avant, tuple(avant)), data.get('motif'))
    return Response(ser_service(obj))


# ---- Secrétariats (rattachés à la structure — §15) -------------------------

def _valider_rattachement(data, obj=None):
    """Au plus un rattachement structure parmi direction/département."""
    direction = data.get('direction') or None
    departement = data.get('departement') or None
    if direction and departement:
        return None, None, 'Rattachement « au plus un » : un secrétariat est adossé à une direction OU un département, pas aux deux.'
    if direction and not Direction.objects.filter(pk=direction).exists():
        return None, None, 'Direction de rattachement inconnue.'
    if departement and not Departement.objects.filter(pk=departement).exists():
        return None, None, 'Département de rattachement inconnu.'
    return direction, departement, None


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def secretariats(request):
    if request.method == 'GET':
        qs = Secretariat.objects.select_related('type', 'direction', 'departement')
        if request.query_params.get('actif') in ('0', '1'):
            qs = qs.filter(actif=request.query_params['actif'] == '1')
        q = (request.query_params.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(numero__icontains=q) | Q(description__icontains=q))
        return Response([ser_secretariat(s) for s in qs])
    if not IsDFRC().has_permission(request, None):
        return Response({'detail': 'Seule la direction (DFRC) modifie l’organigramme.'}, status=403)
    data = _corps(request)
    nom = (data.get('nom') or '').strip()
    if not nom:
        return Response({'detail': '« nom » est requis.'}, status=400)
    direction, departement, err = _valider_rattachement(data)
    if err:
        return Response({'detail': err}, status=400)
    resp, err = _valider_fk_utilisateur(data, 'responsable_id')
    if err:
        return Response({'detail': err}, status=400)
    adj, err = _valider_fk_utilisateur(data, 'adjoint_id')
    if err:
        return Response({'detail': err}, status=400)
    type_id = data.get('type') or None
    if type_id and not RefTypeSecretariat.objects.filter(pk=type_id).exists():
        return Response({'detail': 'Type de secrétariat inconnu.'}, status=400)
    obj = Secretariat.objects.create(
        nom=nom, type_id=type_id,
        description=data.get('description') or '',
        responsable_id=resp, adjoint_id=adj,
        telephone=(data.get('telephone') or '').strip()[:30],
        email=(data.get('email') or '').strip(),
        localisation=(data.get('localisation') or '').strip()[:150],
        direction_id=direction, departement_id=departement,
        actif=_ecoute_bool(data, 'actif'),
    )
    _journal(request, 'ORGANISATION_CREEE', obj, None, {'libelle': obj.nom}, data.get('motif'))
    return Response(ser_secretariat(obj), status=201)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def secretariat_detail(request, pk):
    obj = Secretariat.objects.select_related('type', 'direction', 'departement').filter(pk=pk).first()
    if obj is None:
        return Response({'detail': 'Secrétariat introuvable.'}, status=404)
    if request.method == 'GET':
        return Response(ser_secretariat(obj))
    data = _corps(request)
    if request.method == 'DELETE':
        if obj.actif:
            obj.actif = False
            obj.save(update_fields=['actif'])
            _journal(request, 'ORGANISATION_DESACTIVEE', obj, {'actif': True}, {'actif': False},
                     data.get('motif') or request.query_params.get('motif'))
        return Response(status=204)
    if not IsDFRC().has_permission(request, None):
        return Response({'detail': 'Seule la direction (DFRC) modifie l’organigramme.'}, status=403)
    avant = {c: getattr(obj, c) for c in
             ('nom', 'description', 'actif', 'type_id', 'direction_id', 'departement_id',
              'responsable_id', 'adjoint_id') + _UNIT_FIELDS}
    if 'nom' in data:
        nom = (data.get('nom') or '').strip()
        if not nom:
            return Response({'detail': '« nom » ne peut pas être vide.'}, status=400)
        obj.nom = nom
    for champ in ('description',):
        if champ in data:
            setattr(obj, champ, data.get(champ) or '')
    if 'type' in data:
        val = data.get('type')
        if val in (None, '', 0):
            obj.type = None
        else:
            if not RefTypeSecretariat.objects.filter(pk=val).exists():
                return Response({'detail': 'Type de secrétariat inconnu.'}, status=400)
            obj.type_id = int(val)
    if 'direction' in data or 'departement' in data:
        # Règle « au plus un » : renseigner l'un des deux clears l'autre.
        direction, departement, err = _valider_rattachement(
            {'direction': data.get('direction') or None,
             'departement': data.get('departement') or None})
        if err:
            return Response({'detail': err}, status=400)
        obj.direction_id = direction
        obj.departement_id = departement
    for champ in ('responsable_id', 'adjoint_id'):
        if champ in data:
            val, err = _valider_fk_utilisateur(data, champ)
            if err:
                return Response({'detail': err}, status=400)
            setattr(obj, champ, val)
    for champ in _UNIT_FIELDS:
        if champ in data:
            setattr(obj, champ, (data.get(champ) or '').strip())
    if 'actif' in data:
        obj.actif = _ecoute_bool(data, 'actif')
    obj.save()
    _journal(request, 'ORGANISATION_MODIFIEE', obj, avant,
             _diff(obj, avant, tuple(avant)), data.get('motif'))
    return Response(ser_secretariat(obj))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def responsables(request):
    """Comptes pouvant piloter une unité (tous comptes actifs hors auditeurs/formateurs)."""
    qs = (User.objects.filter(is_active=True)
          .exclude(role__in=('AUDITEUR', 'FORMATEUR'))
          .order_by('username')[:400])
    return Response([
        {'id': u.id, 'nom': u.get_full_name() or u.username, 'role': u.role}
        for u in qs
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def types_secretariat(request):
    """Référentiel des types de secrétariat (écran de rattachement)."""
    qs = RefTypeSecretariat.objects.filter(actif=True)
    return Response([{'id': t.id, 'libelle': t.libelle} for t in qs])
