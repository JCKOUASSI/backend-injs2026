"""Initialisation CONTRÔLÉE du socle RBAC — préparation, jamais d'à-peu-près.

Ce module **ne remplace pas** :func:`habilitations.management.commands.rattacher_comptes_legacy` :
il ajoute ce que la bascule supervisée exige et que la commande historique ne
fait pas — le respect des drapeaux, l'analyse des périmètres, le rapport
structuré et l'exclusion explicite des superutilisateurs. La commande
historique reste le chemin minimal ; celle-ci est le chemin supervisé.

Règles applicables à toute exécution (aucune n'est négociable) :

* **aucune écriture par défaut** : la construction du plan est pure,
  l'application exige ``--appliquer`` ET les deux drapeaux ;
* **aucune attribution automatique d'un rôle sensible ou administratif** :
  ces rôles sont proposés (``PROPOSEE``), jamais activés ;
* **aucun élargissement de périmètre** : le périmètre proposé est celui
  déclaré par le rôle, jamais plus ; un périmètre local
  (SECRETARIAT / FORMATION / PARCOURS / MODULE_ECUE) ne peut pas être inventé
  → l'attribution n'est pas créée et l'écart est signalé ;
* **les superutilisateurs existants sont intouchés** : ils sont exclus du
  plan, sauf demande explicite et, dans ce cas, sans aucune attribution ;
* **aucune suppression, révocation ou modification** d'un objet existant
  (ni compte, ni attribution, ni utilisateur Django) ;
* **authentification reste l'autorité** : ``authentication.User`` n'est
  jamais modifié — seul un profil ``CompteUtilisateur`` est ajouté.

Toute situation non tranchable est signalée (code d'anomalie) plutôt que
corrigée par supposition.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    Perimetre,
    RoleMetier,
)
from habilitations.referentiel.catalogue_matrice import CORRESPONDANCE_LEGACY
from habilitations.services.journalisation import journaliser
from parametres.flags import is_enabled

User = get_user_model()

#: Drapeau du socle de référentiels RBAC (catalogue rôles / permissions).
DRAPEAU_SOCLE = 'flag.lot01_socle_referentiels_rbac'
#: Drapeau du module Utilisateurs (comptes gouvernés).
DRAPEAU_MODULE_UTILISATEURS = 'flag.curp_module_utilisateurs'

#: Périmètres qu'une initialisation peut poser seule (aucun objet métier visé).
TYPES_PERIMETRE_AUTO = frozenset({
    Perimetre.Type.INJS_ENTIER,
    Perimetre.Type.PROPRE_COMPTE,
})
#: Périmètres exigeant la désignation d'un objet métier — jamais deviné.
TYPES_PERIMETRE_LOCAL = frozenset({
    Perimetre.Type.SECRETARIAT,
    Perimetre.Type.FORMATION,
    Perimetre.Type.PARCOURS,
    Perimetre.Type.MODULE_ECUE,
})

#: Ordre de largueur des périmètres, du plus étroit au plus large.
#: HYPOTHÈSE MÉTIER À VALIDER — le modèle ``Perimetre`` ne porte pas de
#: relation d'inclusion ; cet ordre ne sert qu'à détecter un périmètre déclaré
#: plus large que le plafond des permissions. Il n'est jamais utilisé pour
#: élargir une attribution.
ORDRE_PERIMETRE = {
    Perimetre.Type.PROPRE_COMPTE: 1,
    Perimetre.Type.ETUDIANT: 2,
    Perimetre.Type.MODULE_ECUE: 3,
    Perimetre.Type.GROUPE: 4,
    Perimetre.Type.NIVEAU: 5,
    Perimetre.Type.PARCOURS: 6,
    Perimetre.Type.FORMATION: 7,
    Perimetre.Type.SECRETARIAT: 8,
    Perimetre.Type.SERVICE: 9,
    Perimetre.Type.DEPARTEMENT: 10,
    Perimetre.Type.DIRECTION: 11,
    Perimetre.Type.SITE: 12,
    Perimetre.Type.INJS_ENTIER: 13,
}

MOTIF_PROFIL = (
    'Initialisation RBAC contrôlée — profil CURP créé sur un compte Django '
    'existant (additif, sans modification du compte).'
)
MOTIF_ATTRIBUTION = (
    'Initialisation RBAC contrôlée — attribution issue de la table A6 '
    '(rôle non sensible, périmètre déclaré par le rôle).'
)
MOTIF_PROPOSITION = (
    'Initialisation RBAC contrôlée — rôle sensible proposé, activation '
    'subordonnée à la seconde signature (aucune auto-élévation).'
)

# ── Codes d'anomalie ────────────────────────────────────────────────────────
A_ROLE_ABSENT_CATALOGUE = 'ROLE_A6_ABSENT_DU_CATALOGUE'
A_ROLE_INACTIF = 'ROLE_INACTIF'
A_AUCUNE_CORRESPONDANCE = 'ROLE_LEGACY_SANS_CORRESPONDANCE_A6'
A_PERIMETRE_LOCAL = 'PERIMETRE_LOCAL_A_RENSEIGNER'
A_PERIMETRE_PLUS_LARGE = 'PERIMETRE_DEFAUT_PLUS_LARGE_QUE_LES_PERMISSIONS'
A_MODULE_REQUIS_ABSENT = 'MODULE_REQUIS_ABSENT'
A_SUPERUTILISATEUR = 'SUPERUTILISATEUR_EXCLU'
A_ROLE_SENSIBLE = 'ROLE_SENSIBLE_PROPOSE'
A_ATTRIBUTIONS_UNIQUEMENT_LOCALES = 'AUCUNE_ATTRIBUTION_AUTO_SANS_PERIMETRE'
A_DRAPEAU_ABSENT = 'DRAPEAU_ABSENT'
A_DRAPEAU_INACTIF = 'DRAPEAU_INACTIF'


# =============================================================================
# Drapeaux
# =============================================================================
def etat_drapeaux() -> dict:
    """État des deux drapeaux : présents en base ? ouverts ?

    Un drapeau absent n'est jamais considéré ouvert (sémantique P00-08).
    """
    from parametres.models import Parametre

    connus = {p.cle for p in Parametre.objects.filter(cle__in=[
        DRAPEAU_SOCLE, DRAPEAU_MODULE_UTILISATEURS,
    ]).only('cle')}
    return {
        cle: {
            'present': cle in connus,
            'actif': bool(is_enabled(cle)),
        }
        for cle in (DRAPEAU_SOCLE, DRAPEAU_MODULE_UTILISATEURS)
    }


def ecriture_autorisee(*, ignorer_drapeaux: bool = False) -> tuple[bool, list[str]]:
    """L'écriture n'est autorisée que si les deux drapeaux sont ouverts.

    Renvoie ``(autorise, motifs)`` — les motifs sont toujours explicites, y
    compris quand l'écriture est autorisée.
    """
    etats = etat_drapeaux()
    motifs: list[str] = []
    for cle, etat in etats.items():
        if not etat['present']:
            motifs.append(f'{A_DRAPEAU_ABSENT} : {cle} n’existe pas dans les paramètres.')
        elif not etat['actif']:
            motifs.append(f'{A_DRAPEAU_INACTIF} : {cle} est fermé.')
    if ignorer_drapeaux:
        return True, [
            'Écriture autorisée avec contournement explicite des drapeaux '
            '(usage bac à sable / recette uniquement).'
        ] + motifs
    return (not motifs), motifs


# =============================================================================
# Analyse d'un rôle : périmètre déclaré vs plafond des permissions
# =============================================================================
@dataclass
class RolePrevus:
    """Rôle qu'une initialisation pourrait poser, avec son analyse de portée."""

    code: str
    libelle: str
    sensible: bool
    niveau: str
    perimetre_defaut: str
    plafonds_permissions: list[str]
    statut_prevu: str
    perimetre_posable: bool
    anomalies: list[str] = field(default_factory=list)

    @property
    def cle_statut(self) -> str:
        return 'PROPOSEE' if self.sensible else 'ACTIVE'


def portees_maximales(role: RoleMetier) -> list[str]:
    """Portées maximales distinctes des permissions actives du rôle (plafond)."""
    return sorted(set(
        role.permissions.filter(actif=True)
        .values_list('portee_maximale', flat=True)
    ))


def analyser_role(role: RoleMetier) -> RolePrevus:
    """Détermine ce qu'il est légitime de poser pour ``role``, sans élargir.

    Le périmètre **retenu est toujours celui déclaré par le rôle**, jamais
    davantage : un plafond de permission plus large (INJS_ENTIER) n'autorise
    pas à élargir une attribution déclarée au niveau d'un secrétariat. Le
    plafond ne sert qu'à détecter l'incohérence inverse — un périmètre déclaré
    plus large que ce que les permissions du rôle permettent d'exercer — auquel
    cas l'écart est signalé et le périmètre est ramené au plafond le plus étroit.
    """
    plafonds = portees_maximales(role)
    anomalies: list[str] = []

    if not role.actif:
        anomalies.append(A_ROLE_INACTIF)
    if role.module_requis and not role.module_est_installe():
        anomalies.append(A_MODULE_REQUIS_ABSENT)

    perimetre_retenu = role.perimetre_defaut
    if plafonds:
        plafond_etroit = min(plafonds, key=lambda p: ORDRE_PERIMETRE.get(p, 0))
        if ORDRE_PERIMETRE.get(perimetre_retenu, 0) > ORDRE_PERIMETRE.get(plafond_etroit, 0):
            anomalies.append(
                f'{A_PERIMETRE_PLUS_LARGE} : « {perimetre_retenu} » déclaré alors que '
                f'les permissions du rôle plafonnent à « {plafond_etroit} » — '
                'périmètre ramené au plafond.'
            )
            perimetre_retenu = plafond_etroit

    posable = perimetre_retenu in TYPES_PERIMETRE_AUTO
    if not posable:
        anomalies.append(
            f'{A_PERIMETRE_LOCAL} : « {perimetre_retenu} » exige la désignation '
            'd’un objet métier — attribution non créée automatiquement.'
        )
    if role.sensible:
        anomalies.append(A_ROLE_SENSIBLE)

    return RolePrevus(
        code=role.code,
        libelle=role.libelle,
        sensible=role.sensible,
        niveau=role.niveau_defaut,
        perimetre_defaut=role.perimetre_defaut,
        plafonds_permissions=plafonds,
        statut_prevu=AttributionRole.Statut.PROPOSEE if role.sensible
        else AttributionRole.Statut.ACTIVE,
        perimetre_posable=posable,
        anomalies=anomalies,
    )


# =============================================================================
# Plan d'initialisation
# =============================================================================
@dataclass
class LigneCompte:
    """Ce qui est prévu pour un utilisateur Django."""

    username: str
    role_legacy: str
    est_superutilisateur: bool
    compte_existant: bool
    roles: list[RolePrevus] = field(default_factory=list)
    roles_absents: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    applique: bool = False
    detail: str = ''

    @property
    def a_creer_compte(self) -> bool:
        return not self.compte_existant

    @property
    def roles_attribuables(self) -> list[RolePrevus]:
        """Rôles posables par l'initialisation (périmètre global, non sensible)."""
        return [r for r in self.roles if r.perimetre_posable and not r.sensible]

    @property
    def roles_proposables(self) -> list[RolePrevus]:
        """Rôles sensibles : proposés, jamais activés."""
        return [r for r in self.roles if r.perimetre_posable and r.sensible]

    @property
    def roles_bloques(self) -> list[RolePrevus]:
        return [r for r in self.roles if not r.perimetre_posable]


@dataclass
class Plan:
    """Rapport complet, produit avant toute écriture."""

    lignes: list[LigneCompte] = field(default_factory=list)
    drapeaux: dict = field(default_factory=dict)
    anomalies_globales: list[str] = field(default_factory=list)
    ecriture_autorisee: bool = False
    motifs_ecriture: list[str] = field(default_factory=list)
    horodatage: str = ''

    # ── Totaux ──────────────────────────────────────────────────────────────
    @property
    def comptes_a_creer(self) -> int:
        return sum(1 for l in self.lignes if l.a_creer_compte)

    @property
    def attributions_prevues(self) -> int:
        return sum(len(l.roles_attribuables) for l in self.lignes)

    @property
    def propositions_prevues(self) -> int:
        return sum(len(l.roles_proposables) for l in self.lignes)

    @property
    def roles_bloques(self) -> int:
        return sum(len(l.roles_bloques) for l in self.lignes)

    def vers_dict(self) -> dict:
        return {
            'horodatage': self.horodatage,
            'drapeaux': self.drapeaux,
            'ecriture_autorisee': self.ecriture_autorisee,
            'motifs_ecriture': self.motifs_ecriture,
            'anomalies_globales': self.anomalies_globales,
            'totaux': {
                'utilisateurs_analyses': len(self.lignes),
                'comptes_a_creer': self.comptes_a_creer,
                'attributions_prevues': self.attributions_prevues,
                'propositions_sensibles_prevues': self.propositions_prevues,
                'roles_bloques_perimetre_local': self.roles_bloques,
            },
            'lignes': [
                {
                    'username': l.username,
                    'role_legacy': l.role_legacy,
                    'est_superutilisateur': l.est_superutilisateur,
                    'compte_existant': l.compte_existant,
                    'applique': l.applique,
                    'detail': l.detail,
                    'anomalies': l.anomalies,
                    'roles_absents_catalogue': l.roles_absents,
                    'roles': [
                        {
                            'code': r.code,
                            'sensible': r.sensible,
                            'niveau': r.niveau,
                            'perimetre_defaut': r.perimetre_defaut,
                            'plafonds_permissions': r.plafonds_permissions,
                            'statut_prevu': r.statut_prevu,
                            'posable': r.perimetre_posable,
                            'anomalies': r.anomalies,
                        }
                        for r in l.roles
                    ],
                }
                for l in self.lignes
            ],
        }


def utilisateurs_a_traiter(*, inclure_superutilisateurs: bool = False,
                           filtre_username: str = '') -> Iterable[User]:
    """Utilisateurs Django sans profil CURP (les profils existants sont intouchés)."""
    qs = User.objects.filter(profil_habilitation__isnull=True).order_by('role', 'username')
    if not inclure_superutilisateurs:
        qs = qs.filter(is_superuser=False)
    if filtre_username:
        qs = qs.filter(username__iexact=filtre_username.strip())
    return qs


def construire_plan(*, inclure_superutilisateurs: bool = False,
                    filtre_username: str = '',
                    ignorer_drapeaux: bool = False) -> Plan:
    """Construit le rapport **sans rien écrire** (fonction pure en base)."""
    autorise, motifs = ecriture_autorisee(ignorer_drapeaux=ignorer_drapeaux)
    plan = Plan(
        drapeaux=etat_drapeaux(),
        ecriture_autorisee=autorise,
        motifs_ecriture=motifs,
        horodatage=timezone.now().isoformat(timespec='seconds'),
    )

    roles_par_code = {r.code: r for r in RoleMetier.objects.all()}
    if not roles_par_code:
        plan.anomalies_globales.append(
            'Catalogue de rôles vide : lancer le chargement du référentiel '
            'avant toute initialisation.'
        )

    # Contrôle transverse : les plafonds de permissions bornent-ils vraiment ?
    from habilitations.models import PermissionMetier
    plafonds_distincts = set(
        PermissionMetier.objects.filter(actif=True)
        .values_list('portee_maximale', flat=True)
        .distinct()
    )
    if plafonds_distincts == {Perimetre.Type.INJS_ENTIER}:
        plan.anomalies_globales.append(
            'Toutes les permissions actives ont pour portée maximale '
            'INJS_ENTIER : le plafond des permissions ne restreint donc aucun '
            'rôle — la seule borne effective est le périmètre de l’attribution. '
            'À faire arbitrer avant toute initialisation en production.'
        )

    for user in utilisateurs_a_traiter(
        inclure_superutilisateurs=inclure_superutilisateurs,
        filtre_username=filtre_username,
    ).iterator():
        ligne = LigneCompte(
            username=user.get_username(),
            role_legacy=getattr(user, 'role', '') or '',
            est_superutilisateur=bool(user.is_superuser),
            compte_existant=False,
        )
        codes = CORRESPONDANCE_LEGACY.get(ligne.role_legacy)
        if not codes:
            ligne.anomalies.append(
                f'{A_AUCUNE_CORRESPONDANCE} : « {ligne.role_legacy} » — compte '
                'laissé non gouverné.'
            )
            plan.lignes.append(ligne)
            continue

        for code in codes:
            role = roles_par_code.get(code)
            if role is None:
                ligne.roles_absents.append(code)
                ligne.anomalies.append(f'{A_ROLE_ABSENT_CATALOGUE} : {code}.')
                continue
            ligne.roles.append(analyser_role(role))

        if user.is_superuser:
            ligne.anomalies.append(
                f'{A_SUPERUTILISATEUR} : compte préservé, aucune attribution '
                'automatique (décision explicite requise).'
            )
        if ligne.roles and not ligne.roles_attribuables and not ligne.roles_proposables:
            ligne.anomalies.append(
                f'{A_ATTRIBUTIONS_UNIQUEMENT_LOCALES} : tous les rôles A6 '
                'exigent un périmètre local — à créer dans la console.'
            )
        plan.lignes.append(ligne)

    return plan


# =============================================================================
# Application (idempotente)
# =============================================================================
def _perimetre_global(type_perimetre: str) -> Perimetre:
    return Perimetre.obtenir_ou_creer_global(type_perimetre)


def _attribution_existante(compte: CompteUtilisateur, role: RoleMetier,
                           statuts: tuple[str, ...]) -> AttributionRole | None:
    return compte.attributions.filter(role=role, statut__in=statuts).first()


def _appliquer_ligne(ligne: LigneCompte, *, acteur, adresse_ip: str,
                     agent: str) -> LigneCompte:
    """Applique une ligne dans sa propre transaction. Ne révoque ni ne modifie."""
    user = User.objects.filter(**{User.USERNAME_FIELD: ligne.username}).first()
    if user is None:
        ligne.detail = 'utilisateur introuvable — rien de fait.'
        return ligne
    if user.is_superuser and (ligne.roles_attribuables or ligne.roles_proposables):
        # Un superutilisateur existant ne reçoit aucune attribution — ni active
        # ni proposée : toute élévation doit résulter d'une décision explicite.
        with transaction.atomic():
            compte, cree = CompteUtilisateur.objects.get_or_create(
                user=user,
                defaults={
                    'statut': (CompteUtilisateur.Statut.ACTIF if user.is_active
                               else CompteUtilisateur.Statut.DESACTIVE),
                    'canal': CompteUtilisateur._meta.get_field('canal').default,
                    'motif_statut': MOTIF_PROFIL,
                },
            )
        ligne.compte_existant = not cree
        ligne.applique = True
        ligne.detail = (
            f'profil {"créé" if cree else "déjà présent"} ; superutilisateur — '
            'aucune attribution posée (ni active, ni proposée).'
        )
        return ligne

    with transaction.atomic():
        compte, cree = CompteUtilisateur.objects.get_or_create(
            user=user,
            defaults={
                'statut': (CompteUtilisateur.Statut.ACTIF if user.is_active
                           else CompteUtilisateur.Statut.DESACTIVE),
                'canal': CompteUtilisateur._meta.get_field('canal').default,
                'motif_statut': MOTIF_PROFIL,
            },
        )
        ligne.compte_existant = not cree
        if cree:
            journaliser(
                JournalHabilitation.TypeEvenement.COMPTE_CREE,
                acteur=acteur, compte=compte,
                nouvelle_valeur={
                    'username': user.get_username(),
                    'role_legacy': ligne.role_legacy,
                    'origine': 'INITIALISATION_RBAC',
                },
                motif=MOTIF_PROFIL, adresse_ip=adresse_ip, agent_utilisateur=agent,
            )

        poses, propositions = 0, 0
        for prevu in ligne.roles_attribuables + ligne.roles_proposables:
            role = RoleMetier.objects.filter(code=prevu.code).first()
            if role is None:
                continue
            statut = prevu.statut_prevu
            if _attribution_existante(compte, role, (AttributionRole.Statut.ACTIVE,
                                                    AttributionRole.Statut.PROPOSEE)):
                continue  # idempotence : rien à refaire
            if compte.attributions.filter(role=role,
                                          statut=AttributionRole.Statut.REVOQUEE).exists():
                ligne.anomalies.append(
                    f'ATTRIBUTION_REVOQUEE_EXISTANTE : {role.code} — non réactivée.'
                )
                continue
            sensible = bool(role.sensible)
            attribution = AttributionRole.objects.create(
                compte=compte,
                role=role,
                niveau_effectif=role.niveau_defaut,
                statut=AttributionRole.Statut.PROPOSEE if sensible
                else AttributionRole.Statut.ACTIVE,
                motif=MOTIF_PROPOSITION if sensible else MOTIF_ATTRIBUTION,
                attribue_par=acteur,
                # Jamais de seconde signature posée par l'initialisation :
                # la séparation demandeur / validateur doit être respectée.
                valide_par=None,
                date_validation=None,
            )
            perimetre = _perimetre_global(
                prevu.perimetre_defaut if prevu.perimetre_defaut in TYPES_PERIMETRE_AUTO
                else (prevu.plafonds_permissions[0] if prevu.plafonds_permissions
                      else Perimetre.Type.PROPRE_COMPTE)
            )
            attribution.perimetres.set([perimetre])
            journaliser(
                (JournalHabilitation.TypeEvenement.PROPOSITION_DEPOSEE if sensible
                 else JournalHabilitation.TypeEvenement.ROLE_ATTRIBUE),
                acteur=acteur, compte=compte, cible=attribution,
                nouvelle_valeur={
                    'role': role.code,
                    'statut': attribution.statut,
                    'perimetre': perimetre.type,
                    'origine': 'INITIALISATION_RBAC',
                },
                motif=attribution.motif, adresse_ip=adresse_ip, agent_utilisateur=agent,
            )
            propositions += 1 if sensible else 0
            poses += 0 if sensible else 1

        ligne.applique = True
        ligne.detail = (
            f'profil {"créé" if cree else "déjà présent"} ; '
            f'{poses} attribution(s) active(s), {propositions} proposition(s) sensible(s)'
            + (f' ; {len(ligne.roles_bloques)} rôle(s) à périmètre local laissés à la console'
               if ligne.roles_bloques else '')
        )
        return ligne


def appliquer_plan(plan: Plan, *, acteur=None, adresse_ip: str = '',
                   agent: str = '') -> Plan:
    """Applique le plan. Idempotent : un second passage ne change rien.

    Ne touche jamais à ``authentication.User`` et ne supprime, ne révoque ni
    ne modifie aucun objet existant.
    """
    for ligne in plan.lignes:
        if ligne.est_superutilisateur or not (ligne.roles_attribuables or ligne.roles_proposables):
            if not ligne.roles_attribuables and not ligne.roles_proposables:
                ligne.detail = ligne.detail or 'aucune attribution automatique — rien à écrire.'
                continue
        _appliquer_ligne(ligne, acteur=acteur, adresse_ip=adresse_ip, agent=agent)
    return plan
