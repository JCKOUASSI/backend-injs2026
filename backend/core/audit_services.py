"""Services du journal d'audit unifié (P01-01).

* :func:`enregistrer_evenement` crée une entrée immuable en lui attribuant un
  code métier unique ``AUDIT-AAAAMMJJ-NNNNNN`` de façon atomique ;
* :func:`replier_depuis_*` dupliquent les journaux applicatifs existants dans
  le registre unifié, sans jamais les modifier, et de façon idempotente.

La génération du code verrouille le :class:`~core.models.CompteurCode` de la
journée (``select_for_update`` sur PostgreSQL). Une boucle de reprise sur
``IntegrityError`` garantit aussi l'absence de doublon sur les moteurs sans
verrou de ligne (SQLite) comme en cas de code préexistant.
"""
from datetime import date as date_cls

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone

from parametres.flags import is_enabled

from .models import CompteurCode, EvenementAudit

#: Feature flag de branchement du LOT 1 (socle / référentiels / RBAC).
FLAG_LOT1 = 'flag.lot01_socle_referentiels_rbac'

PREFIXE_CODE = 'AUDIT'
LONGUEUR_SEQUENCE = 6
# Nombre de tentatives de reprise sur collision avant d'abandonner.
TENTATIVES_MAX = 10


def flag_actif(user=None):
    """Indique si la réplication/l'API du journal unifié sont activées."""
    return is_enabled(FLAG_LOT1, user)


def cle_compteur(le_jour):
    """Clé du compteur pour une journée, ex. ``AUDIT-20260913``."""
    return f'{PREFIXE_CODE}-{le_jour:%Y%m%d}'


def formater_code(le_jour, numero):
    """Code complet pour une journée et un numéro de séquence."""
    return f'{cle_compteur(le_jour)}-{numero:0{LONGUEUR_SEQUENCE}d}'


def _resoudre_cible(cible):
    """Retourne ``(content_type, object_id)`` pour une instance Django."""
    if cible is None:
        return None, None
    return ContentType.objects.get_for_model(cible.__class__), cible.pk


@transaction.atomic
def enregistrer_evenement(
    *, source, action, acteur=None, acteur_label='', cible=None,
    objet_type='', objet_id='', objet_libelle='', detail=None,
    ip_address=None, horodatage=None, source_entree_id=None, le_jour=None,
):
    """Crée et retourne un :class:`EvenementAudit` immuable.

    Le code est généré dans la même transaction que l'insertion, ce qui rend
    la séquence sans trou (toute annulation annule aussi le compteur).
    """
    if le_jour is None:
        le_jour = horodatage.date() if horodatage is not None else date_cls.today()
    cle = cle_compteur(le_jour)
    ct, oid = _resoudre_cible(cible)

    derniere_erreur = None
    for _ in range(TENTATIVES_MAX):
        # Verrou de la ligne compteur de la journée (création comprise).
        compteur, _ = CompteurCode.objects.select_for_update().get_or_create(
            cle=cle, defaults={'dernier_numero': 0},
        )
        compteur.dernier_numero += 1
        compteur.save(update_fields=['dernier_numero'])
        code = formater_code(le_jour, compteur.dernier_numero)
        try:
            with transaction.atomic():
                return EvenementAudit.objects.create(
                    code=code,
                    source=source,
                    action=action,
                    horodatage=horodatage or timezone.now(),
                    acteur=acteur,
                    acteur_label=(
                        acteur_label or
                        (acteur.get_username() if acteur else '') or ''
                    ),
                    content_type=ct,
                    object_id=oid,
                    objet_type=objet_type or '',
                    objet_id=str(objet_id) if objet_id not in (None, '') else '',
                    objet_libelle=objet_libelle or '',
                    detail=detail or {},
                    ip_address=ip_address,
                    source_entree_id=source_entree_id,
                )
        except IntegrityError as exc:  # collision défensive : on réessaie
            derniere_erreur = exc
            continue
    raise IntegrityError(
        f'Impossible de générer un code d’audit unique pour {cle} '
        f'après {TENTATIVES_MAX} tentatives'
    ) from derniere_erreur


def _replique_existe(source, source_entree_id):
    return EvenementAudit.objects.filter(
        source=source, source_entree_id=source_entree_id,
    ).exists()


# ---------------------------------------------------------------------------
# Connecteurs des 3 applications pilotes
# ---------------------------------------------------------------------------

def repliquer_depuis_presences(entree):
    """Réplique un ``presences.AuditLog`` (idempotent)."""
    if _replique_existe(EvenementAudit.Source.PRESENCES, entree.pk):
        return None
    cible = entree.formation or entree.pointage
    detail = dict(entree.extra or {})
    if entree.device_id:
        detail.setdefault('device_id', entree.device_id)
    return enregistrer_evenement(
        source=EvenementAudit.Source.PRESENCES,
        action=entree.action,
        horodatage=entree.timestamp,
        acteur=entree.acteur,
        acteur_label=entree.acteur_label,
        cible=cible,
        objet_type=entree.cible_type,
        objet_id=entree.cible_numero,
        objet_libelle=entree.cible_nom,
        detail=detail,
        ip_address=entree.ip_address,
        source_entree_id=entree.pk,
        le_jour=entree.timestamp.date(),
    )


def repliquer_depuis_scolarite(entree):
    """Réplique un ``scolarite.JournalScolarite`` (idempotent)."""
    if _replique_existe(EvenementAudit.Source.SCOLARITE, entree.pk):
        return None
    detail = dict(entree.extra or {})
    if entree.ancienne_valeur or entree.nouvelle_valeur or entree.commentaire:
        detail.setdefault('ancienne_valeur', entree.ancienne_valeur)
        detail.setdefault('nouvelle_valeur', entree.nouvelle_valeur)
        detail.setdefault('commentaire', entree.commentaire)
    return enregistrer_evenement(
        source=EvenementAudit.Source.SCOLARITE,
        action=entree.action,
        horodatage=entree.timestamp,
        acteur=entree.acteur,
        acteur_label=entree.acteur_label,
        objet_type=entree.objet_type,
        objet_id=entree.objet_id if entree.objet_id is not None else '',
        objet_libelle=entree.objet_libelle,
        detail=detail,
        source_entree_id=entree.pk,
        le_jour=entree.timestamp.date(),
    )


def repliquer_depuis_referentiels(entree):
    """Réplique un ``referentiels.ReferentielJournal`` (idempotent)."""
    if _replique_existe(EvenementAudit.Source.REFERENTIELS, entree.pk):
        return None
    cible = entree.cible
    return enregistrer_evenement(
        source=EvenementAudit.Source.REFERENTIELS,
        action=entree.action,
        horodatage=entree.horodatage,
        acteur=entree.utilisateur,
        cible=cible,
        objet_type=entree.content_type.model if entree.content_type_id else '',
        objet_id=entree.object_id if entree.object_id is not None else '',
        objet_libelle=str(cible)[:255] if cible is not None else '',
        detail=entree.detail or {},
        source_entree_id=entree.pk,
        le_jour=entree.horodatage.date(),
    )
