"""Initialisation CONTRÔLÉE du socle RBAC — préparation, jamais d'à-peu-près.

Deux règles nouvelles, issues de la revue du comité :

* **aucun rôle n'est déduit du champ historique ``User.role``** : la table A6
  (``CORRESPONDANCE_LEGACY``) n'est plus utilisée ici pour proposer des
  attributions. L'initialisation crée des **comptes**, jamais des droits ;
* **le catalogue de rôles n'est jamais réimporté** : les 81 rôles en base
  (35 annexe A1 + 46 cibles J2) sont la référence, le fichier
  ``referentiel/catalogue_roles.py`` en est la source — ils concordent
  (cf. ``docs/curp/08-reconciliation-catalogue-roles.md``).

Garanties de toute exécution :

* **aucune écriture par défaut** : le rapport est pur, ``--apply`` est requis
  **et** les deux drapeaux doivent être ouverts ;
* **aucune attribution de rôle automatique**, sensible ou non ;
* **aucune modification d'un utilisateur Django**, d'un compte existant ou
  d'une attribution existante ;
* **aucun élargissement de périmètre** et **aucune réinitialisation de
  catalogue** ;
* **les superutilisateurs sont préservés** (exclus du plan par défaut) ;
* **aucune suppression** : aucune commande ne supprime quoi que ce soit.

Le rapport distingue systématiquement **utilisateur Django** (authentification),
**compte RBAC** (habilitation) et **attribution de rôle** (droit effectif).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    Perimetre,
    PermissionMetier,
    RoleMetier,
)
from habilitations.services.journalisation import journaliser
from parametres.flags import is_enabled

User = get_user_model()

#: Drapeau du socle de référentiels RBAC (catalogue rôles / permissions).
DRAPEAU_SOCLE = 'flag.lot01_socle_referentiels_rbac'
#: Drapeau du module Utilisateurs (comptes gouvernés).
DRAPEAU_MODULE_UTILISATEURS = 'flag.curp_module_utilisateurs'

#: Périmètres posables sans désigner d'objet métier.
TYPES_PERIMETRE_AUTO = frozenset({
    Perimetre.Type.INJS_ENTIER,
    Perimetre.Type.PROPRE_COMPTE,
})

#: Ordre de largueur des périmètres (du plus étroit au plus large).
#: HYPOTHÈSE MÉTIER À VALIDER — le modèle ne porte pas de relation
#: d'inclusion ; cet ordre sert uniquement à détecter un périmètre déclaré
#: plus large que le plafond des permissions. Jamais utilisé pour élargir.
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

MOTIF_COMPTE = (
    'Initialisation RBAC contrôlée — profil CURP créé sur un compte Django '
    'existant (additif, sans attribution de rôle).'
)

A_DRAPEAU_ABSENT = 'DRAPEAU_ABSENT'
A_DRAPEAU_INACTIF = 'DRAPEAU_INACTIF'
A_COMPTE_DESYNCHRONISE = 'COMPTE_DESYNCHRONISE'
A_ATTRIBUTION_SUR_COMPTE_INACTIF = 'ATTRIBUTION_SUR_COMPTE_INACTIF'
A_SENSIBLE_SANS_SECONDE_SIGNATURE = 'ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE'
A_PERIMETRE_PLUS_LARGE = 'PERIMETRE_DEFAUT_PLUS_LARGE_QUE_LES_PERMISSIONS'
A_PERIMETRE_LOCAL = 'PERIMETRE_LOCAL_NON_AUTO_POSABLE'
A_ROLE_MODULE_ABSENT = 'MODULE_REQUIS_ABSENT'
A_PERSONNES_DOUBLONS = 'PERSONNES_EN_DOUBLON_PROBABLE'


# =============================================================================
# Drapeaux
# =============================================================================
def etat_drapeaux() -> dict:
    """État des deux drapeaux : présents en base ? ouverts ?

    Un drapeau absent n'est jamais considéré ouvert (sémantique P00-08).
    """
    from parametres.models import Parametre

    connus = {p.cle for p in Parametre.objects.filter(
        cle__in=[DRAPEAU_SOCLE, DRAPEAU_MODULE_UTILISATEURS]).only('cle')}
    return {
        cle: {'present': cle in connus, 'actif': bool(is_enabled(cle))}
        for cle in (DRAPEAU_SOCLE, DRAPEAU_MODULE_UTILISATEURS)
    }


def ecriture_autorisee(*, ignorer_drapeaux: bool = False) -> tuple[bool, list[str]]:
    """L'écriture exige les deux drapeaux ou un contournement explicite."""
    motifs: list[str] = []
    for cle, etat in etat_drapeaux().items():
        if not etat['present']:
            motifs.append(f'{A_DRAPEAU_ABSENT} : {cle} n’existe pas dans les paramètres.')
        elif not etat['actif']:
            motifs.append(f'{A_DRAPEAU_INACTIF} : {cle} est fermé.')
    if ignorer_drapeaux:
        return True, [
            'Contournement explicite des drapeaux (recette / bac à sable).'
        ] + motifs
    return (not motifs), motifs


# =============================================================================
# Analyse du catalogue (lecture seule)
# =============================================================================
def portees_maximales(role: RoleMetier) -> list[str]:
    """Plafonds (``portee_maximale``) distincts des permissions actives du rôle."""
    return sorted(set(
        role.permissions.filter(actif=True).values_list('portee_maximale', flat=True)))


def analyser_role(role: RoleMetier) -> dict:
    """Analyse de cohérence d'un rôle du catalogue (aucune modification)."""
    plafonds = portees_maximales(role)
    anomalies: list[str] = []
    if role.module_requis and not role.module_est_installe():
        anomalies.append(f'{A_ROLE_MODULE_ABSENT} : {role.module_requis}.')
    if plafonds:
        plafond_etroit = min(plafonds, key=lambda p: ORDRE_PERIMETRE.get(p, 0))
        if ORDRE_PERIMETRE.get(role.perimetre_defaut, 0) > ORDRE_PERIMETRE.get(plafond_etroit, 0):
            anomalies.append(
                f'{A_PERIMETRE_PLUS_LARGE} : « {role.perimetre_defaut} » déclaré, '
                f'plafond « {plafond_etroit} ».')
    if role.perimetre_defaut not in TYPES_PERIMETRE_AUTO:
        anomalies.append(
            f'{A_PERIMETRE_LOCAL} : « {role.perimetre_defaut} » exige un objet métier.')
    return {
        'code': role.code,
        'libelle': role.libelle,
        'sensible': role.sensible,
        'niveau_defaut': role.niveau_defaut,
        'perimetre_defaut': role.perimetre_defaut,
        'plafonds_permissions': plafonds,
        'actif': role.actif,
        'anomalies': anomalies,
    }


def comparer_catalogue_fichier() -> dict:
    """Compare la base au fichier ``referentiel/catalogue_roles.py`` (lecture)."""
    from habilitations.referentiel.catalogue_roles import ROLES

    fichier = {}
    for entree in ROLES:
        code, libelle, _domaine, niveau, perimetre, module, sensible = entree[:7]
        fichier[code] = {
            'niveau': niveau, 'perimetre': perimetre, 'module': module,
            'sensible': sensible,
        }
    base = {r.code: r for r in RoleMetier.objects.all()}
    return {
        'roles_fichier': len(fichier),
        'roles_base': len(base),
        'sensibles_fichier': sum(1 for v in fichier.values() if v['sensible']),
        'sensibles_base': sum(1 for r in base.values() if r.sensible),
        'codes_absents_de_la_base': sorted(set(fichier) - set(base)),
        'codes_absents_du_fichier': sorted(set(base) - set(fichier)),
        'attributs_divergents': [
            {'code': code, 'champ': champ, 'fichier': attendu, 'base': reel}
            for code, v in fichier.items()
            if code in base
            for champ, attendu, reel in (
                ('sensible', v['sensible'], base[code].sensible),
                ('niveau_defaut', v['niveau'], base[code].niveau_defaut),
                ('perimetre_defaut', v['perimetre'], base[code].perimetre_defaut),
                ('module_requis', v['module'], base[code].module_requis),
            )
            if str(attendu) != str(reel)
        ],
    }


# =============================================================================
# Rapport d'initialisation
# =============================================================================
@dataclass
class Rapport:
    """Rapport complet, produit **avant** toute écriture."""

    horodatage: str = ''
    base: str = ''
    drapeaux: dict = field(default_factory=dict)
    ecriture_autorisee: bool = False
    motifs_ecriture: list[str] = field(default_factory=list)
    utilisateurs: dict = field(default_factory=dict)
    comptes: dict = field(default_factory=dict)
    attributions: dict = field(default_factory=dict)
    roles: dict = field(default_factory=dict)
    coherence: list[str] = field(default_factory=list)
    doublons: list[str] = field(default_factory=list)
    anomalies_perimetre: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    realise: list[str] = field(default_factory=list)

    def vers_dict(self) -> dict:
        return {
            'horodatage': self.horodatage,
            'base': self.base,
            'drapeaux': self.drapeaux,
            'ecriture_autorisee': self.ecriture_autorisee,
            'motifs_ecriture': self.motifs_ecriture,
            'utilisateurs': self.utilisateurs,
            'comptes': self.comptes,
            'attributions': self.attributions,
            'roles': self.roles,
            'coherence': self.coherence,
            'doublons': self.doublons,
            'anomalies_perimetre': self.anomalies_perimetre,
            'operations': self.operations,
            'realise': self.realise,
        }


def construire_rapport(*, inclure_superutilisateurs: bool = False,
                       filtre_username: str = '',
                       ignorer_drapeaux: bool = False) -> Rapport:
    """Construit le rapport **sans rien écrire**."""
    from django.db import connection
    from django.utils import timezone

    autorise, motifs = ecriture_autorisee(ignorer_drapeaux=ignorer_drapeaux)
    rapport = Rapport(
        horodatage=timezone.now().isoformat(timespec='seconds'),
        base=str(connection.settings_dict.get('NAME', '')),
        drapeaux=etat_drapeaux(),
        ecriture_autorisee=autorise,
        motifs_ecriture=motifs,
    )

    # ── Utilisateurs (authentification) ─────────────────────────────────────
    tous = User.objects.all()
    superusers = list(tous.filter(is_superuser=True)
                      .values_list(User.USERNAME_FIELD, flat=True))
    inactifs = list(tous.filter(is_active=False)
                    .values_list(User.USERNAME_FIELD, flat=True))
    rapport.utilisateurs = {
        'total': tous.count(),
        'actifs': tous.filter(is_active=True).count(),
        'inactifs': inactifs,
        'superutilisateurs': superusers,
    }

    # ── Comptes RBAC (habilitation) ─────────────────────────────────────────
    manquants_qs = User.objects.filter(profil_habilitation__isnull=True)
    if not inclure_superutilisateurs:
        manquants_qs = manquants_qs.filter(is_superuser=False)
    if filtre_username:
        manquants_qs = manquants_qs.filter(
            **{f'{User.USERNAME_FIELD}__iexact': filtre_username.strip()})
    a_creer = list(manquants_qs.order_by(User.USERNAME_FIELD)
                   .values_list(User.USERNAME_FIELD, flat=True))
    rapport.comptes = {
        'existants': CompteUtilisateur.objects.count(),
        'manquants': len(a_creer),
        'a_creer': a_creer,
        'superutilisateurs_exclus': (not inclure_superutilisateurs),
    }

    # ── Cohérence utilisateur ↔ compte ──────────────────────────────────────
    for compte in CompteUtilisateur.objects.select_related('user'):
        user = compte.user
        if user.is_active and compte.statut in (
            CompteUtilisateur.Statut.DESACTIVE, CompteUtilisateur.Statut.SUSPENDU,
        ):
            rapport.coherence.append(
                f'{A_COMPTE_DESYNCHRONISE} : {user.get_username()} actif mais '
                f'compte « {compte.statut} ».')
        if not user.is_active and compte.statut == CompteUtilisateur.Statut.ACTIF:
            rapport.coherence.append(
                f'{A_COMPTE_DESYNCHRONISE} : {user.get_username()} inactif mais '
                'compte ACTIF.')
        if compte.statut in (CompteUtilisateur.Statut.DESACTIVE,
                             CompteUtilisateur.Statut.SUSPENDU):
            actives = compte.attributions.filter(
                statut=AttributionRole.Statut.ACTIVE).count()
            if actives:
                rapport.coherence.append(
                    f'{A_ATTRIBUTION_SUR_COMPTE_INACTIF} : {user.get_username()} '
                    f'({compte.statut}) porte {actives} attribution(s) active(s).')

    # ── Doublons probables ──────────────────────────────────────────────────
    try:
        from habilitations.services.identite import identifier_doublons
        for groupe in identifier_doublons():
            rapport.doublons.append(
                f'{A_PERSONNES_DOUBLONS} : {groupe["critere"]} → {groupe["personnes"]}')
    except Exception:  # litige de lecture : signalé, jamais bloquant
        rapport.doublons.append('Détection des doublons indisponible.')

    # ── Attributions (droits effectifs) ─────────────────────────────────────
    attributions = AttributionRole.objects.select_related('role', 'compte__user')
    par_statut: dict[str, int] = {}
    sensibles_sans_signature: list[str] = []
    viol_perimetre: list[str] = []
    for attribution in attributions:
        par_statut[attribution.statut] = par_statut.get(attribution.statut, 0) + 1
        if attribution.role.sensible and attribution.statut == AttributionRole.Statut.ACTIVE \
                and not attribution.valide_par_id:
            sensibles_sans_signature.append(
                f'{attribution.compte.user.get_username()} → {attribution.role.code}')
        for code in attribution.contraintes():
            viol_perimetre.append(
                f'{attribution.compte.user.get_username()} / {attribution.role.code} : {code}')
    rapport.attributions = {
        'total': attributions.count(),
        'par_statut': par_statut,
        'sensibles_actives_sans_seconde_signature': sensibles_sans_signature,
        'violations_contraintes': viol_perimetre,
    }

    # ── Catalogue de rôles ──────────────────────────────────────────────────
    roles = list(RoleMetier.objects.all())
    anomalies_roles = []
    for role in roles:
        analyse = analyser_role(role)
        for anomalie in analyse['anomalies']:
            anomalies_roles.append(f'{role.code} : {anomalie}')
    rapport.roles = {
        'total': len(roles),
        'actifs': sum(1 for r in roles if r.actif),
        'sensibles': sum(1 for r in roles if r.sensible),
        'permissions': PermissionMetier.objects.count(),
        'anomalies': anomalies_roles,
        'comparaison_fichier': comparer_catalogue_fichier(),
    }

    plafonds = set(PermissionMetier.objects.filter(actif=True)
                   .values_list('portee_maximale', flat=True).distinct())
    if plafonds == {Perimetre.Type.INJS_ENTIER}:
        rapport.anomalies_perimetre.append(
            'Toutes les permissions actives plafonnent à INJS_ENTIER : le plafond '
            'ne restreint aucun rôle — la seule borne est le périmètre de '
            'l’attribution. À arbitrer avant toute montée en charge.')
    rapport.anomalies_perimetre.extend(anomalies_roles)

    # ── Opérations prévues ──────────────────────────────────────────────────
    rapport.operations = [
        f"Créer {len(a_creer)} compte(s) RBAC manquant(s) : {', '.join(a_creer[:20])}"
        + ('…' if len(a_creer) > 20 else '') if a_creer else
        'Aucun compte RBAC manquant : aucune création.',
        'Aucune attribution de rôle créée (règle : aucun rôle déduit de User.role).',
        'Aucune modification d’utilisateur Django, de compte existant ou '
        'd’attribution existante.',
        'Aucune réinitialisation ni réimportation du catalogue de rôles.',
    ]
    return rapport


# =============================================================================
# Application — comptes uniquement, idempotente
# =============================================================================
def appliquer_rapport(rapport: Rapport, *, acteur=None, adresse_ip: str = '',
                      agent: str = '') -> Rapport:
    """Crée **uniquement** les comptes RBAC manquants. Idempotent.

    Aucune attribution n'est créée, aucun compte existant n'est modifié, aucun
    utilisateur Django n'est touché, aucune suppression n'est pratiquée — même
    en cas d'erreur (chaque compte est traité dans sa propre transaction).
    """
    deja = set(CompteUtilisateur.objects.values_list('user_id', flat=True))
    for username in rapport.comptes['a_creer']:
        user = User.objects.filter(**{User.USERNAME_FIELD: username}).first()
        if user is None:
            rapport.realise.append(f'{username} : utilisateur introuvable — rien de fait.')
            continue
        if user.pk in deja:
            rapport.realise.append(f'{username} : compte déjà présent — rien de fait.')
            continue
        try:
            with transaction.atomic():
                compte, cree = CompteUtilisateur.objects.get_or_create(
                    user=user,
                    defaults={
                        'statut': (CompteUtilisateur.Statut.ACTIF if user.is_active
                                   else CompteUtilisateur.Statut.DESACTIVE),
                        'canal': CompteUtilisateur._meta.get_field('canal').default,
                        'motif_statut': MOTIF_COMPTE,
                        'cree_par': acteur if acteur and acteur.is_authenticated else None,
                    },
                )
                if cree:
                    journaliser(
                        JournalHabilitation.TypeEvenement.COMPTE_CREE,
                        acteur=acteur if acteur and acteur.is_authenticated else None,
                        compte=compte,
                        nouvelle_valeur={
                            'username': user.get_username(),
                            'origine': 'INITIALISATION_RBAC',
                            'statut': compte.statut,
                        },
                        motif=MOTIF_COMPTE, adresse_ip=adresse_ip,
                        agent_utilisateur=agent,
                    )
            deja.add(user.pk)
            rapport.realise.append(
                f'{username} : compte créé ({compte.statut})' if cree
                else f'{username} : compte déjà présent — rien de fait.')
        except Exception as exc:  # aucune suppression automatique : on signale
            rapport.realise.append(f'{username} : ÉCHEC — {exc} (aucune suppression).')
    rapport.comptes['manquants'] = User.objects.filter(
        profil_habilitation__isnull=True).count()
    return rapport
