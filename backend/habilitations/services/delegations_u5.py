"""Délégation temporaire d'habilitations — contrôles U5 (C3 point 5, L4).

Règles appliquées côté serveur (S3 : le backend est la seule source de
vérité) :

* **on ne délègue que ce que l'on détient** : chaque rôle ou permission
  explicite doit provenir d'une attribution DIRECTE, active et couvrant la
  date de fin de la délégation ;
* **pas de re-délégation** : un droit reçu uniquement par délégation ne
  peut être re-délégué (la comparaison se fait sur les attributions
  directes, jamais sur les délégations reçues) ;
* durée **obligatoirement bornée**, pas de délégation à soi-même,
  périmètres inclus dans ceux du délégant ;
* la délégation est créée PROPOSÉE et **activée** par un administrateur
  après recontrôle ; seule une délégation active produit ses effets ;
* chaque action exercée en vertu d'une délégation est journalisée avec la
  référence de la délégation et la mention du délégant.
"""
from django.utils import timezone

from ..models import (
    AttributionRole,
    DelegationHabilitation,
    JournalHabilitation,
    PermissionMetier,
    RoleMetier,
)
from .comptes_admin import ErreurConsole, permissions_des_roles
from .journalisation import journaliser


def _attributions_directes_actives(compte, date_fin=None):
    """Attributions ACTIVES du compte à la date courante (ou ``date_fin``)."""
    aujourdhui = date_fin or timezone.localdate()
    return [
        a for a in compte.attributions.filter(
            statut=AttributionRole.Statut.ACTIVE,
        ).select_related('role').prefetch_related('perimetres')
        if a.est_active(aujourdhui)
    ]


def controler_delegation(delegant, delegataire, roles_codes, permissions_codes,
                         date_fin, perimetres_ids=None, date_debut=None):
    """Lève :class:`ErreurConsole` si la délégation enfreint une règle."""
    date_debut = date_debut or timezone.localdate()
    if delegant.pk == delegataire.pk:
        raise ErreurConsole('DELEGATION_SOI_MEME',
                            "Le délégant et le délégataire doivent être distincts.")
    if not date_fin:
        raise ErreurConsole('DELEGATION_NON_BORNEE',
                            "Toute délégation doit être bornée dans le temps.")
    if date_fin < date_debut:
        raise ErreurConsole('PERIODE_INCOHERENTE',
                            "La date de fin doit être postérieure au début.")

    # Détention « aujourd'hui » (attributions directes actives) : c'est ce
    # qui distingue une détention directe d'un droit reçu par délégation.
    attributions = _attributions_directes_actives(delegant, date_debut)
    roles_detenus = {a.role for a in attributions}
    roles_demandes = list(RoleMetier.objects.filter(code__in=roles_codes or []))
    if len(roles_demandes) != len(set(roles_codes or [])):
        raise ErreurConsole('ROLE_INCONNU', "Un ou plusieurs rôles sont inconnus.")

    roles_non_detenus = sorted({
        r.code for r in roles_demandes if r not in roles_detenus
    })
    if roles_non_detenus:
        # Inclut le cas de la re-délégation : un rôle détenu seulement par
        # délégation reçue n'est PAS dans les attributions directes.
        raise ErreurConsole(
            'DROIT_NON_DETENU',
            "Le délégant ne peut déléguer des droits qu'il ne détient pas "
            "directement : "
            + ', '.join(roles_non_detenus) + ". La re-délégation est interdite.",
            409,
        )

    # Couverture temporelle : chaque attribution doit porter jusqu'à la fin
    # de la délégation (une attribution bornée qui s'achève avant fait l'objet
    # d'un refus explicite, distinct de la non-détention).
    for attribution in attributions:
        if attribution.role in roles_demandes and attribution.date_fin \
                and attribution.date_fin < date_fin:
            raise ErreurConsole(
                'DELEGATION_HORS_TERME',
                f"Le rôle {attribution.role.code} du délégant expire le "
                f"{attribution.date_fin.isoformat()} avant la fin de la délégation.",
                409,
            )

    if permissions_codes:
        permissions_demandees = list(PermissionMetier.objects.filter(
            code__in=permissions_codes))
        if len(permissions_demandees) != len(set(permissions_codes)):
            raise ErreurConsole('PERMISSION_INCONNUE',
                                "Une ou plusieurs permissions sont inconnues.")
        # Permissions DIRECTES (rôles + dérogations), sans les délégations reçues.
        permissions_directes = permissions_des_roles(roles_detenus)
        for derog in delegant.derogations.filter(statut='ACTIVE', sens='OCTROI'):
            if derog.est_active(date_debut):
                permissions_directes.add(derog.permission.code)
        manquantes = sorted({
            p.code for p in permissions_demandes
            if p.code not in permissions_directes
        })
        if manquantes:
            raise ErreurConsole(
                'DROIT_NON_DETENU',
                "Permissions non détenues directement par le délégant : "
                + ', '.join(manquantes),
                409,
            )

    # Périmètres : chaque périmètre délégué doit être couvert par les
    # attributions des rôles délégués (les périmètres globaux couvrent tout).
    if perimetres_ids:
        couverts = set()
        for attribution in attributions:
            if attribution.role in roles_demandes:
                if attribution.role.perimetre_defaut == 'INJS_ENTIER':
                    couverts = None
                    break
                couverts.update(attribution.perimetres.values_list('pk', flat=True))
        if couverts is not None:
            hors_portee = sorted(set(perimetres_ids) - couverts)
            if hors_portee:
                raise ErreurConsole(
                    'PERIMETRE_NON_DETENU',
                    "Un ou plusieurs périmètres délégués ne sont pas couverts "
                    "par les rôles du délégant.",
                    409,
                )


def activer_delegation(delegation, acteur, motif, meta=None):
    """Passe une délégation PROPOSÉE en ACTIVE après recontrôle serveur."""
    meta = meta or {}
    delegation = DelegationHabilitation.objects.select_for_update().get(pk=delegation.pk)
    if delegation.statut == DelegationHabilitation.Statut.ACTIVE:
        return delegation
    if delegation.statut != DelegationHabilitation.Statut.PROPOSEE:
        raise ErreurConsole(
            'DELEGATION_NON_ACTIVABLE',
            f"Une délégation {delegation.get_statut_display().lower()} ne peut être activée.",
            409,
        )
    controler_delegation(
        delegation.delegant, delegation.delegataire,
        list(delegation.roles.values_list('code', flat=True)),
        list(delegation.permissions.values_list('code', flat=True)),
        delegation.date_fin,
        list(delegation.perimetres.values_list('pk', flat=True)),
        delegation.date_debut,
    )
    delegation.statut = DelegationHabilitation.Statut.ACTIVE
    delegation.valide_par = acteur
    delegation.save()
    journaliser(
        JournalHabilitation.TypeEvenement.DELEGATION_ACTIVEE,
        acteur=acteur, compte=delegation.delegataire, cible=delegation,
        nouvelle_valeur={
            'delegant': delegation.delegant.user.get_username(),
            'roles': list(delegation.roles.values_list('code', flat=True)),
            'date_fin': delegation.date_fin.isoformat(),
        },
        motif=motif or 'Activation de la délégation après contrôle.',
        adresse_ip=meta.get('ip', ''), agent_utilisateur=meta.get('ua', ''),
    )
    return delegation


def journaliser_action_deleguee(delegation, acteur, libelle_action,
                                detail=None, motif=''):
    """Trace une action exercée EN VERTU d'une délégation (mention du délégant).

    ``acteur`` doit être l'utilisateur du compte délégataire et la
    délégation doit être active à la date du jour.
    """
    delegation = DelegationHabilitation.objects.get(pk=delegation.pk)
    if delegation.delegataire.user_id != acteur.pk:
        raise ErreurConsole(
            'PAS_LE_DELEGATAIRE',
            "Seul le délégataire peut enregistrer une action pour cette délégation.",
            403,
        )
    if not delegation.est_active():
        raise ErreurConsole(
            'DELEGATION_INACTIVE',
            "La délégation n'est pas active (non activée, terminée ou expirée).",
            409,
        )
    entree = journaliser(
        JournalHabilitation.TypeEvenement.ACTION_DELEGUEE,
        acteur=acteur, compte=delegation.delegataire, cible=delegation,
        delegation_source=delegation,
        nouvelle_valeur={
            'action': libelle_action,
            'delegant': delegation.delegant.user.get_username(),
            'delegataire': delegation.delegataire.user.get_username(),
            'mention': f"Agit par délégation de {delegation.delegant.user.get_username()}",
            'detail': detail or {},
        },
        motif=motif or f"Action par délégation de {delegation.delegant.user.get_username()}",
    )
    return entree
