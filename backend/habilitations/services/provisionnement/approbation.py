"""Approbation humaine des propositions de provisionnement (L2).

Toute application passe par ces deux seules fonctions : aucune sonde, aucune
tâche planifiée ne crée ou modifie un compte directement. L'approbation
s'exécute dans une transaction unique, réutilise les services U4
(``creer_compte``, ``changer_statut``, ``_appliquer_roles``) et journalise
la décision avec son motif.
"""
import copy
import secrets
import string
from datetime import timedelta

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from ...models import (
    AttributionRole,
    CompteUtilisateur,
    Perimetre,
    PolitiqueSecurite,
    PropositionProvisionnement,
)
from .. import comptes_admin
from ..comptes_admin import ErreurConsole, _appliquer_roles
from ..journalisation import journaliser


def _mot_de_passe_temporaire():
    """Génère un secret conforme à la politique par défaut (12+ caractères)."""
    politique = PolitiqueSecurite.objet()
    longueur = max(12, politique.longueur_min_mot_de_passe)
    alphabet = string.ascii_letters + string.digits + '!#$%&*+-=?@'
    while True:
        mdp = ''.join(secrets.choice(alphabet) for _ in range(longueur))
        if (any(c.islower() for c in mdp) and any(c.isupper() for c in mdp)
                and any(c.isdigit() for c in mdp)
                and any(c in '!#$%&*+-=?@' for c in mdp)):
            return mdp


def _resoudre_perimetres(specifications):
    """Transforme des specs génériques {app, modele, id} en :class:`Perimetre`."""
    perimetres = []
    for spec in specifications or []:
        try:
            modele = apps.get_model(spec['app'], spec['modele'])
            ct = ContentType.objects.get_for_model(modele)
            objet = modele.objects.filter(pk=spec['objet_id']).first()
        except (LookupError, KeyError, TypeError):
            continue
        if objet is None:
            continue
        perimetre, _ = Perimetre.objects.get_or_create(
            type=spec['type'], content_type=ct, object_id=objet.pk,
            defaults={'reference_lisible': str(spec.get('reference', ''))[:100]},
        )
        perimetres.append(perimetre)
    return perimetres


def _attacher_perimetres_generiques(compte, lignes_roles):
    """Ajoute (sans écraser) les périmètres génériques aux attributions."""
    for ligne in lignes_roles:
        specs = ligne.get('perimetres_generiques')
        if not specs:
            continue
        attribution = compte.attributions.filter(
            role__code=ligne['role'], statut=AttributionRole.Statut.ACTIVE,
        ).first()
        if attribution is None:
            continue
        existants = set(attribution.perimetres.values_list('pk', flat=True))
        nouveaux = [p.pk for p in _resoudre_perimetres(specs) if p.pk not in existants]
        if nouveaux:
            attribution.perimetres.add(*nouveaux)


def _compte_depuis_proposition(proposition):
    if proposition.compte_cible_id:
        return proposition.compte_cible
    username = proposition.proposition.get('identifiants', {}).get('username', '')
    return (
        CompteUtilisateur.objects.filter(user__username=username).first()
        if username else None
    )


@transaction.atomic
def approuver(proposition, acteur, motif, ajustements=None, meta=None):
    """Approuve et APPLIQUE immédiatement la proposition (transaction unique)."""
    meta = meta or {}
    proposition = PropositionProvisionnement.objects.select_for_update().get(
        pk=proposition.pk,
    )
    if proposition.statut != PropositionProvisionnement.Statut.EN_ATTENTE:
        raise ErreurConsole(
            'PROPOSITION_CLOTUREE',
            "Cette proposition n'est plus en attente de validation.",
            409,
        )
    if not (motif or '').strip():
        raise ErreurConsole('MOTIF_REQUIS',
                            "Un motif est obligatoire pour approuver une proposition.")
    charge = copy.deepcopy(proposition.proposition)
    if ajustements:
        # L'écran de validation permet de compléter/corriger la charge (rôle
        # legacy notamment pour les agents recrutés).
        if ajustements.get('identifiants'):
            charge.setdefault('identifiants', {}).update(ajustements['identifiants'])
        if ajustements.get('roles') is not None:
            charge['roles'] = ajustements['roles']
        if ajustements.get('canal'):
            charge['canal'] = ajustements['canal']

    mdp_genere = None
    resultat = {}
    action = proposition.action_proposee

    if action == PropositionProvisionnement.Action.CREER_COMPTE:
        identifiants = charge.get('identifiants', {})
        if not identifiants.get('role_legacy'):
            raise ErreurConsole(
                'ROLE_A_COMPLETER',
                "Le rôle d'accès actuel doit être déterminé avant la création.",
            )
        if not identifiants.get('mot_de_passe'):
            mdp_genere = _mot_de_passe_temporaire()
            identifiants['mot_de_passe'] = mdp_genere
        charge['motif'] = f"[{proposition.get_declencheur_display()}] {charge.get('motif', '')} " \
                          f"— Approbation : {motif}"
        compte = comptes_admin.creer_compte(acteur, charge, meta)
        _attacher_perimetres_generiques(compte, charge.get('roles', []))
        proposition.compte_cible = compte
        resultat = {'compte': compte.pk, 'username': compte.user.get_username(),
                    'mot_de_passe_temporaire': mdp_genere,
                    'changement_mdp_obligatoire': bool(mdp_genere)}
        if mdp_genere:
            compte.user.must_change_password = True
            compte.user.save(update_fields=['must_change_password'])

    elif action == PropositionProvisionnement.Action.ACTIVER_COMPTE:
        compte = _compte_depuis_proposition(proposition)
        if compte is None:
            identifiants = charge.get('identifiants', {})
            if not identifiants.get('role_legacy'):
                raise ErreurConsole('ROLE_A_COMPLETER',
                                    "Le rôle d'accès doit être déterminé avant la création.")
            mdp_genere = _mot_de_passe_temporaire()
            identifiants['mot_de_passe'] = mdp_genere
            compte = comptes_admin.creer_compte(acteur, charge, meta)
            resultat['compte_cree'] = True
        else:
            if compte.statut != CompteUtilisateur.Statut.ACTIF:
                comptes_admin.changer_statut(
                    compte, acteur, 'activer',
                    f"Activation sur proposition {proposition.get_declencheur_display()} : {motif}",
                    meta,
                )
            lignes = charge.get('roles') or []
            if lignes:
                _appliquer_roles(compte, lignes, acteur, meta, motif=motif)
                _attacher_perimetres_generiques(compte, lignes)
            resultat['compte'] = compte.pk
        proposition.compte_cible = compte

    elif action == PropositionProvisionnement.Action.ATTRIBUER_ROLE:
        compte = _compte_depuis_proposition(proposition)
        if compte is None:
            raise ErreurConsole('COMPTE_INTROUVABLE',
                                "Aucun compte cible rattaché à cette proposition.")
        lignes = charge.get('roles') or []
        if not lignes:
            raise ErreurConsole('ROLE_MANQUANT', "Aucun rôle à attribuer dans la proposition.")
        _appliquer_roles(compte, lignes, acteur, meta, motif=motif)
        _attacher_perimetres_generiques(compte, lignes)
        resultat = {'compte': compte.pk, 'roles': [l['role'] for l in lignes]}

    elif action in (PropositionProvisionnement.Action.SUSPENDRE_COMPTE,
                    PropositionProvisionnement.Action.DESACTIVER_COMPTE):
        compte = _compte_depuis_proposition(proposition)
        if compte is None:
            raise ErreurConsole('COMPTE_INTROUVABLE',
                                "Aucun compte cible rattaché à cette proposition.")
        transition = charge.get('transition') or (
            'desactiver' if action == PropositionProvisionnement.Action.DESACTIVER_COMPTE
            else 'suspendre'
        )
        comptes_admin.changer_statut(
            compte, acteur, transition,
            f"[{proposition.get_declencheur_display()}] {charge.get('motif', '')} — {motif}",
            meta,
        )
        proposition.compte_cible = compte
        resultat = {'compte': compte.pk, 'statut': compte.statut}

    else:  # pragma: no cover - garde-fou
        raise ErreurConsole('ACTION_INCONNUE', f"Action {action} non prise en charge.")

    proposition.statut = PropositionProvisionnement.Statut.APPLIQUEE
    proposition.approuve_par = acteur
    proposition.traite_le = timezone.now()
    proposition.resultat = resultat
    proposition.motif = (proposition.motif + f' || APPROUVÉ : {motif}')[:4000]
    proposition.save()
    journaliser(
        'PROPOSITION_APPROUVEE', acteur=acteur, compte=proposition.compte_cible,
        cible=proposition,
        nouvelle_valeur={'action': action, 'resultat': {
            k: v for k, v in resultat.items() if k != 'mot_de_passe_temporaire'}},
        motif=motif, adresse_ip=meta.get('ip', ''),
        agent_utilisateur=meta.get('ua', ''),
    )
    return proposition


@transaction.atomic
def rejeter(proposition, acteur, motif, meta=None):
    meta = meta or {}
    proposition = PropositionProvisionnement.objects.select_for_update().get(
        pk=proposition.pk,
    )
    if proposition.statut != PropositionProvisionnement.Statut.EN_ATTENTE:
        raise ErreurConsole(
            'PROPOSITION_CLOTUREE',
            "Cette proposition n'est plus en attente de validation.",
            409,
        )
    if not (motif or '').strip():
        raise ErreurConsole('MOTIF_REQUIS',
                            "Un motif est obligatoire pour rejeter une proposition.")
    proposition.statut = PropositionProvisionnement.Statut.REJETEE
    proposition.approuve_par = acteur
    proposition.traite_le = timezone.now()
    proposition.motif_rejet = motif
    # On libère la clé de déduplication (contrainte UNIQUE en base) : le
    # même fait métier pourra de nouveau être détecté et remis en file.
    proposition.cle_dedoublonnage = (
        f'{proposition.cle_dedoublonnage}#rj{proposition.pk}'
    )[:180]
    proposition.save()
    journaliser(
        'PROPOSITION_REJETEE', acteur=acteur, compte=proposition.compte_cible,
        cible=proposition, nouvelle_valeur={'action': proposition.action_proposee},
        motif=motif, adresse_ip=meta.get('ip', ''),
        agent_utilisateur=meta.get('ua', ''),
    )
    return proposition


def delai_grace_expire(date_effet, grace_jours):
    """Vrai si la date d'effet est dépassée d'au moins ``grace_jours``."""
    return date_effet + timedelta(days=grace_jours) <= timezone.localdate()
