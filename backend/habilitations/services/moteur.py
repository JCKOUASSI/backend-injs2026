"""Moteur d'autorisation CURP (unité U2) : ``est_autorise`` et ses dix
contrôles ordonnés.

Le moteur est **purement décisionnel** : il ne modifie aucune réponse HTTP,
n'écrit rien en base et ne connaît pas DRF. Il évalue une demande
(compte × permission canonique × canal × cible) et retourne une
:class:`DecisionAutorisation` motivée. La façon dont cette décision est
exploitée (abstention, observation, refus effectif) relève de
:mod:`habilitations.permissions` et :mod:`habilitations.services.observation`.

Ordre des contrôles (la numérotation fait partie du contrat d'API) :

1. session authentifiée ;
2. compte gouverné (profil ``CompteUtilisateur`` existant) — sinon ABSTENTION ;
3. statut du compte non bloquant ;
4. date d'expiration non atteinte ;
5. canal autorisé (profil, puis canal imposé par le rôle) ;
6. MFA lorsque la politique ou un rôle sensible l'exige ;
7. existence d'un octroi valide (rôle via matrice, dérogation OCTROI,
   délégation signée), avec contrôles de seconde signature, incompatibilités,
   module requis, niveau et durée de dérogation ;
8. priorité du RETRAIT explicite ;
9. couverture de la cible par les périmètres des octrois ;
10. validité résiduelle d'une délégation (titulaire toujours habilité).

Règle de sécurité : le moteur est fermé par défaut. Toute incertitude
(permission inconnue, aucun octroi valide, cible hors périmètre) produit un
refus motivé. L'ABSTENTION (compte non gouverné) n'est pas un refus : c'est
l'ancien dispositif qui reste seul décideur jusqu'à la migration U8.
"""
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone

from .resolveurs import couvert_par_ancetre

from ..models import (
    AttributionRole,
    CanalAcces,
    CompteUtilisateur,
    DelegationHabilitation,
    NiveauAcces,
    PermissionAttribuee,
    PermissionMetier,
    Perimetre,
)
from .codes import (
    LARGEUR_PERIMETRE,
    LIBELLES_MOTIFS,
    MODE_APPLICATION,
    MODE_OBSERVATION,
    MODE_OFF,
)

_ORDRE_NIVEAUX = {n: i for i, n in enumerate(NiveauAcces.values)}


@dataclass
class Octroi:
    """Un chemin qui accorde (ou pourrait accorder) la permission."""

    source: str  # 'ROLE' | 'DEROGATION_OCTROI' | 'DELEGATION'
    reference: str
    role_code: str = ''
    niveau: str = ''
    perimetres: list = field(default_factory=list)  # liste de dicts sérialisables
    detail: dict = field(default_factory=dict)

    def pour_api(self):
        return {
            'source': self.source,
            'reference': self.reference,
            'role': self.role_code,
            'niveau': self.niveau,
            'perimetres': self.perimetres,
            'detail': self.detail,
        }


@dataclass
class DecisionAutorisation:
    """Résultat déterministe d'une évaluation."""

    permission: str
    canal: str
    mode: str
    gouverne: bool = False
    autorise: bool = False
    motifs: list = field(default_factory=list)  # liste de codes
    octrois: list = field(default_factory=list)  # liste d'Octroi valides
    compte: object = None

    def ajouter_motif(self, code):
        if code not in self.motifs:
            self.motifs.append(code)
        return code

    def pour_api(self):
        return {
            'permission': self.permission,
            'canal': self.canal,
            'mode': self.mode,
            'gouverne': self.gouverne,
            'autorise': self.autorise,
            'motifs': [
                {'code': code, 'libelle': LIBELLES_MOTIFS.get(code, code)}
                for code in self.motifs
            ],
            'octrois': [o.pour_api() for o in self.octrois],
        }


def mode_moteur():
    """Lit les interrupteurs ``HABILITATIONS_*`` (OFF si tout est éteint)."""
    application = bool(getattr(settings, 'HABILITATIONS_APPLICATION', False))
    observation = bool(getattr(settings, 'HABILITATIONS_OBSERVATION', False))
    if application:
        return MODE_APPLICATION
    if observation:
        return MODE_OBSERVATION
    return MODE_OFF


def _decrire_perimetre(perimetre):
    # LOT 5 (L4-01) : ``content_type_id`` et ``id`` sont exposés pour que la
    # description sérialisée résolve aussi les cibles « objet métier » du
    # contrôle 9 (``has_object_permission``). Additif : les consommateurs
    # existants (dict du contrat d'API, affichages) sont inchangés.
    return {
        'type': perimetre.type,
        'reference': perimetre.reference_lisible,
        'object_id': perimetre.object_id,
        'global': perimetre.est_global,
        'content_type_id': getattr(perimetre, 'content_type_id', None),
        'id': getattr(perimetre, 'pk', None),
    }


def _resoudre_compte(utilisateur):
    """Accepte un User, un CompteUtilisateur ou None ; retourne (user, compte)."""
    if isinstance(utilisateur, CompteUtilisateur):
        return utilisateur.user, utilisateur
    user = utilisateur
    if user is None or not getattr(user, 'is_authenticated', False):
        return user, None
    compte = (
        CompteUtilisateur.objects.filter(user=user)
        .select_related('user')
        .first()
    )
    return user, compte


def _perimetres_attribution(attribution):
    return [_decrire_perimetre(p) for p in attribution.perimetres.all()]


def _attribution_est_saine(attribution, decision, date, canal):
    """Vérifie module, seconde signature, incompatibilités, périmètre, canal.

    Retourne ``True`` si l'attribution peut effectivement octroyer ses
    permissions. Les violations constatées sont versées à la décision.
    """
    role = attribution.role
    sain = True
    if not role.module_est_installe():
        decision.ajouter_motif('MODULE_REQUIS_ABSENT')
        sain = False
    if role.sensible and not attribution.valide_par_id:
        decision.ajouter_motif('ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE')
        sain = False
    incompatibles = set(role.incompatible_avec.values_list('pk', flat=True))
    if incompatibles:
        conflit = (
            attribution.compte.attributions.filter(
                statut=AttributionRole.Statut.ACTIVE,
                role__pk__in=incompatibles,
            )
            .exclude(pk=attribution.pk)
        )
        if any(a.est_active(date) for a in conflit):
            decision.ajouter_motif('ROLES_INCOMPATIBLES')
            sain = False
    if (
        role.perimetre_defaut == Perimetre.Type.SECRETARIAT
        and not attribution.perimetres.filter(
            type=Perimetre.Type.SECRETARIAT
        ).exists()
    ):
        decision.ajouter_motif('PERIMETRE_SECRETARIAT_MANQUANT')
        sain = False
    if role.canal_impose and canal and role.canal_impose != canal:
        decision.ajouter_motif('CANAL_IMPOSE_PAR_ROLE')
        sain = False
    return sain


def _octrois_par_role(compte, permission, decision, date, canal, contexte):
    """Contrôle 7, branche rôle : attributions actives et saines."""
    octrois = []
    attributions = (
        compte.attributions.filter(
            statut=AttributionRole.Statut.ACTIVE,
            role__actif=True,
            role__permissions=permission,
        )
        .distinct()
        .select_related('role')
        .prefetch_related('perimetres', 'role__incompatible_avec')
    )
    niveau_requis = contexte.get('niveau_minimum')
    for attribution in attributions:
        if not attribution.est_active(date):
            continue
        if not _attribution_est_saine(attribution, decision, date, canal):
            continue
        if (
            niveau_requis
            and _ORDRE_NIVEAUX.get(attribution.niveau_effectif, 0)
            < _ORDRE_NIVEAUX.get(niveau_requis, 0)
        ):
            decision.ajouter_motif('NIVEAU_INSUFFISANT')
            continue
        octrois.append(
            Octroi(
                source='ROLE',
                reference=f'attribution-{attribution.pk}',
                role_code=attribution.role.code,
                niveau=attribution.niveau_effectif,
                perimetres=_perimetres_attribution(attribution),
                detail={
                    'perimetre_defaut': attribution.role.perimetre_defaut,
                    'sensible': attribution.role.sensible,
                },
            )
        )
    return octrois


def _derogations_actives(compte, permission, sens, date):
    qs = compte.derogations.filter(
        statut=PermissionAttribuee.Statut.ACTIVE,
        sens=sens,
        permission=permission,
        date_debut__lte=date,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=date)
    ).select_related('perimetre')
    return list(qs)


def _octrois_par_derogation(compte, permission, decision, date, politique):
    """Contrôle 7, branche OCTROI dérogatoire ; retourne aussi les RETRAIT."""
    from .validations import controle_duree_derogation
    octrois, retraits = [], []
    for derog in _derogations_actives(
        compte, permission, PermissionAttribuee.Sens.OCTROI, date
    ):
        code = controle_duree_derogation(
            derog.date_debut, derog.date_fin, politique
        )
        if code:
            decision.ajouter_motif(code)
            continue
        if (
            permission.necessite_double_validation
            and not derog.valide_par_id
        ):
            decision.ajouter_motif('DEROGATION_SANS_SECONDE_SIGNATURE')
            continue
        if derog.perimetre_id:
            maxi = permission.portee_maximale
            if (
                LARGEUR_PERIMETRE.get(derog.perimetre.type, 0)
                > LARGEUR_PERIMETRE.get(maxi, 9)
            ):
                decision.ajouter_motif('DEROGATION_HORS_PORTEE_MAXIMALE')
                continue
        octrois.append(
            Octroi(
                source='DEROGATION_OCTROI',
                reference=f'derogation-{derog.pk}',
                perimetres=[_decrire_perimetre(derog.perimetre)]
                if derog.perimetre_id else [],
                detail={'date_fin': derog.date_fin.isoformat() if derog.date_fin else None,
                        'date_creation': derog.date_creation.isoformat()},
            )
        )
    for retrait in _derogations_actives(
        compte, permission, PermissionAttribuee.Sens.RETRAIT, date
    ):
        retraits.append(retrait)
    return octrois, retraits


def _octrois_par_delegation(compte, permission, decision, date, canal,
                            contexte, politique):
    """Contrôle 7/10 : délégations reçues, bornées, signées, titulaires."""
    octrois = []
    delegations = (
        compte.delegations_recues.filter(
            statut=DelegationHabilitation.Statut.ACTIVE
        )
        .prefetch_related('roles', 'roles__permissions', 'permissions',
                          'perimetres', 'delegant__attributions')
    )
    for delegation in delegations:
        if not delegation.est_active(date):
            continue  # est_active gère aussi les bornes ; pas de motif bruyant
        roles_porteurs = [
            role for role in delegation.roles.all()
            if permission in list(role.permissions.all())
        ]
        permission_directe = permission in list(delegation.permissions.all())
        if not roles_porteurs and not permission_directe:
            continue
        critique = (
            permission.necessite_double_validation
            or permission.criticite == PermissionMetier.Criticite.CRITIQUE
            or any(role.sensible for role in roles_porteurs)
        )
        if critique and not delegation.valide_par_id:
            decision.ajouter_motif('DELEGATION_NON_SIGNEE')
            continue
        # Le délégant doit toujours détenir DIRECTEMENT la permission (pas
        # de chaîne de délégation : profondeur 1, re-délégation interdite).
        titulaire = _evaluer_interne(
            delegation.delegant, permission, canal=canal,
            cible=None, contexte=contexte, date=date, politique=politique,
            avec_delegations=False,
        )
        titulaires_directs = [
            o for o in titulaire.octrois if o.source in ('ROLE', 'DEROGATION_OCTROI')
        ]
        if not titulaire.autorise or not titulaires_directs:
            decision.ajouter_motif('DELEGATION_SANS_TITULAIRE_VALIDE')
            continue
        perimetres = list(delegation.perimetres.all())
        decrits = [_decrire_perimetre(p) for p in perimetres]
        if not perimetres:
            # Une délégation sans périmètre explicite reprend les périmètres
            # valides des attributions directes du titulaire pour les rôles
            # délégués.
            for octroi in titulaires_directs:
                decrits.extend(octroi.perimetres)
        octrois.append(
            Octroi(
                source='DELEGATION',
                reference=f'delegation-{delegation.pk}',
                role_code=','.join(sorted(r.code for r in roles_porteurs)),
                perimetres=decrits,
                detail={'delegant_id': delegation.delegant_id,
                        'date_fin': delegation.date_fin.isoformat()},
            )
        )
    return octrois


def _appliquer_retraits(octrois, retraits, decision, cible, contexte, date):
    """Contrôle 8 : le RETRAIT explicite l'emporte, sauf OCTROI postérieur.

    * un RETRAIT sans périmètre est global : il neutralise tous les octrois,
      sauf un OCTROI dérogatoire postérieur et doublement signé (le contrôle
      de signature est fait à l'étape 7) ;
    * un RETRAIT ciblé ne vaut que pour une cible nommée située dans son
      périmètre ; sans cible dans la demande, il est sans effet.
    """
    if not retraits:
        return octrois
    octrois_derog = [o for o in octrois if o.source == 'DEROGATION_OCTROI']
    leves = []  # octrois dérogatoirs qui lèvent explicitement un retrait
    for retrait in retraits:
        if retrait.perimetre_id is None:
            leves_retrait = [
                o for o in octrois_derog if _octroi_postérieur(o, retrait)
            ]
            if leves_retrait:
                leves.extend(leves_retrait)
                continue
            decision.ajouter_motif('PERMISSION_RETIREE')
            return leves_retrait
        if cible is None:
            continue  # retrait ciblé sans effet sur une permission fonctionnelle
        if not _cible_couverte(retrait.perimetre, cible, contexte):
            continue
        leves_retrait = [
            o for o in octrois_derog
            if _octroi_postérieur(o, retrait)
            and any(
                _cible_couverte(_normalise_perimetre(p), cible, contexte)
                for p in o.perimetres
            )
        ]
        if leves_retrait:
            leves.extend(leves_retrait)
        else:
            decision.ajouter_motif('PERMISSION_RETIREE')
    if 'PERMISSION_RETIREE' not in decision.motifs:
        return octrois
    # Retrait ciblé non levé sur cette cible : seules les levées explicites
    # survivent ; les autres octrois ne peuvent plus couvrir la cible.
    leves_uniques = {id(o): o for o in leves}
    return list(leves_uniques.values())


def _octroi_postérieur(octroi, retrait):
    """Vrai si l'OCTROI dérogatoire a été créé après le RETRAIT (levée explicite)."""
    try:
        date_octroi = octroi.detail.get('date_creation', '')
        return bool(date_octroi) and date_octroi >= retrait.date_creation.isoformat()
    except Exception:
        return False


class _PerimetreDict:
    """Adaptateur minimal d'un périmètre décrit sous forme de dict."""

    def __init__(self, donnees):
        self.type = donnees.get('type')
        self.object_id = donnees.get('object_id')
        self.est_global = donnees.get('global', False)
        self.content_type_id = donnees.get('content_type_id')
        self._id = donnees.get('id')

    @property
    def pk(self):
        return self._id


def _normalise_perimetre(perimetre):
    """Un périmètre ORM reste tel quel ; un dict sérialisé devient adaptateur."""
    return perimetre if hasattr(perimetre, 'type') else _PerimetreDict(perimetre)


def _cible_couverte(perimetre, cible, contexte):
    """Contrôle 9 : une cible tombe-t-elle dans un périmètre donné ?"""
    couverture = contexte.get('couverture')
    if couverture is not None:
        try:
            return bool(couverture(perimetre, cible))
        except TypeError:
            return False
    if getattr(perimetre, 'type', None) == Perimetre.Type.INJS_ENTIER:
        return True
    # Cible décrite en dict ou objet modèle.
    cible_type = cible.get('type') if isinstance(cible, dict) else None
    cible_id = str(cible.get('object_id', '')) if isinstance(cible, dict) \
        else str(getattr(cible, 'pk', ''))
    if isinstance(cible, dict):
        if perimetre.type == cible_type and str(perimetre.object_id or '') == cible_id:
            return True
    else:
        try:
            ct = ContentType.objects.get_for_model(cible.__class__)
            if (
                perimetre.content_type_id == ct.pk
                and str(perimetre.object_id or '') == cible_id
            ):
                return True
        except Exception:
            pass
        # Règle générique SECRETARIAT : la cible porte un secretariat_id.
        if perimetre.type == Perimetre.Type.SECRETARIAT:
            sid = getattr(cible, 'secretariat_id', None)
            if sid is not None and str(sid) == str(perimetre.object_id or ''):
                return True
        # LOT 5 (J2-4) : résolveur hiérarchique — un périmètre couvre aussi
        # les objets rattachés (Direction ⊃ Département, Formation ⊃
        # Parcours ⊃ Groupe/Niveau, ECUE ⊃ sa formation…). Additif : seule
        # une paire auparavant refusée peut basculer vers « couvert ».
        if couvert_par_ancetre(perimetre, cible):
            return True
    return False


def _evaluer_interne(compte, code_permission, *, canal, cible, contexte,
                     date, politique, avec_delegations):
    """Cœur des contrôles 3 à 10 (hors authentification/gouvernance)."""
    decision = DecisionAutorisation(
        permission=code_permission,
        canal=canal or CanalAcces.WEB,
        mode=mode_moteur(),
        gouverne=True,
        compte=compte,
    )
    # Contrôle 3 — statut.
    codes_statut = {
        CompteUtilisateur.Statut.INVITE: 'COMPTE_INVITE',
        CompteUtilisateur.Statut.SUSPENDU: 'COMPTE_SUSPENDU',
        CompteUtilisateur.Statut.DESACTIVE: 'COMPTE_DESACTIVE',
        CompteUtilisateur.Statut.VERROUILLE: 'COMPTE_VERROUILLE',
        CompteUtilisateur.Statut.EXPIRE: 'COMPTE_EXPIRE',
    }
    if compte.statut in codes_statut:
        decision.ajouter_motif(codes_statut[compte.statut])
    # Contrôle 4 — expiration de compte.
    if not compte.est_en_cours_validite():
        decision.ajouter_motif('COMPTE_EXPIRATION_ATTEINTE')
    # Contrôle 5 — canal du profil.
    if canal and not compte.peut_acceder_au_canal(canal):
        decision.ajouter_motif('CANAL_NON_AUTORISE')

    # Contrôle 7 — résolution de la permission et des octrois.
    permission = PermissionMetier.objects.filter(
        code=code_permission, actif=True
    ).first()
    if permission is None:
        decision.ajouter_motif('PERMISSION_INCONNUE')
        return _finaliser(decision, cible, contexte)
    octrois = _octrois_par_role(compte, permission, decision, date, canal, contexte)
    octrois_derog, retraits = _octrois_par_derogation(
        compte, permission, decision, date, politique
    )
    octrois.extend(octrois_derog)
    if avec_delegations:
        octrois.extend(
            _octrois_par_delegation(
                compte, permission, decision, date, canal, contexte, politique
            )
        )
    if not octrois:
        decision.ajouter_motif('AUCUNE_ATTRIBUTION_PERMETTANTE')
    # Contrôle 6 — MFA : exigé par la politique ou un rôle sensible octroyant.
    roles_exigeant_mfa = set(politique.roles_mfa_obligatoire or [])
    mfa_exige = any(
        o.role_code in roles_exigeant_mfa or o.detail.get('sensible')
        for o in octrois
    )
    if mfa_exige and not compte.mfa_actif:
        decision.ajouter_motif('MFA_REQUIS_NON_ACTIF')
    # Contrôle 8 — retraits.
    octrois = _appliquer_retraits(octrois, retraits, decision, cible, contexte, date)
    # Contrôle 9 — couverture de cible.
    if octrois and cible is not None:
        couvrants = []
        for octroi in octrois:
            if not octroi.perimetres:
                # Aucun périmètre néo-matérialisé : un octroi de rôle sans
                # périmètre explicite ne couvre pas une cible nommée (sauf si
                # le rôle est global par défaut).
                if (
                    octroi.source == 'ROLE'
                    and octroi.detail.get('perimetre_defaut')
                    == Perimetre.Type.INJS_ENTIER
                ):
                    couvrants.append(octroi)
                continue
            for p in octroi.perimetres:
                per = _normalise_perimetre(p)
                if per.type == Perimetre.Type.INJS_ENTIER or _cible_couverte(per, cible, contexte):
                    couvrants.append(octroi)
                    break
        if not couvrants:
            decision.ajouter_motif('CIBLE_HORS_PERIMETRE')
        octrois = couvrants
    decision.octrois = octrois
    return _finaliser(decision, cible, contexte)


def _finaliser(decision, cible, contexte):
    bloquants = [m for m in decision.motifs if m != 'CANAL_IMPOSE_PAR_ROLE']
    decision.autorise = (
        not bloquants
        and bool(decision.octrois)
        and 'PERMISSION_INCONNUE' not in decision.motifs
    )
    return decision


def est_autorise(utilisateur, code_permission, *, canal=None, cible=None,
                 contexte=None, date=None, politique=None):
    """Évalue une demande d'accès. Voir :mod:`habilitations.services.moteur`.

    ``utilisateur`` peut être un ``authentication.User`` ou un
    ``CompteUtilisateur``. ``cible`` est un objet métier, un dict
    ``{'type', 'object_id'}`` ou ``None`` (permission fonctionnelle sans
    ressource nommée). ``contexte`` accepte ``couverture`` (callable de
    périmètre), ``niveau_minimum``.
    """
    contexte = contexte or {}
    canal = canal or CanalAcces.WEB
    date = date or timezone.localdate()
    from ..models.politique import PolitiqueSecurite
    politique = politique or PolitiqueSecurite.objet()
    user, compte = _resoudre_compte(utilisateur)
    # Contrôle 1 — authentification.
    if user is None or not getattr(user, 'is_authenticated', False):
        decision = DecisionAutorisation(
            permission=code_permission, canal=canal, mode=mode_moteur(),
        )
        decision.ajouter_motif('NON_AUTHENTIFIE')
        return decision
    # Contrôle 2 — gouvernance : l'ABSTENTION n'est pas un refus.
    if compte is None:
        return DecisionAutorisation(
            permission=code_permission, canal=canal, mode=mode_moteur(),
            gouverne=False, autorise=False,
        )
    return _evaluer_interne(
        compte, code_permission, canal=canal, cible=cible, contexte=contexte,
        date=date, politique=politique, avec_delegations=True,
    )
