"""Réplication des journaux applicatifs vers le registre unifié (P01-01).

Chaque entrée créée dans un journal pilote (``presences.AuditLog``,
``scolarite.JournalScolarite``, ``referentiels.ReferentielJournal``) est
dupliquée dans ``core.EvenementAudit`` **lorsque le feature flag LOT 1 est
activé**. Tant qu'il est désactivé (livraison par défaut), rien ne se passe et
le comportement historique reste strictement identique.

Un échec de réplication ne doit jamais casser l'opération métier qui écrit le
journal source : l'erreur est journalisée, à l'image de
``scolarite.journaliser``. Les tests appellent les connecteurs directement et
vérifient néanmoins leur correction.
"""
import logging

from django.db.models.signals import post_save

from . import audit_services

logger = logging.getLogger(__name__)

# Identifiants de connexion stables : un rechargement de l'AppConfig ne doit
# pas dupliquer les récepteurs.
DISPATCH = {
    'presences.AuditLog': 'core.replication.presences.v1',
    'scolarite.JournalScolarite': 'core.replication.scolarite.v1',
    'referentiels.ReferentielJournal': 'core.replication.referentiels.v1',
}


def _replicer(created, instance, connecteur, etiquette):
    if not created:
        return
    if not audit_services.flag_actif():
        return
    try:
        connecteur(instance)
    except Exception:  # noqa: BLE001 — l'audit ne doit jamais casser le métier
        logger.exception(
            'Réplication core impossible depuis %s entrée n°%s',
            etiquette, instance.pk,
        )


def replicer_audit_log(sender, instance, created, **kwargs):
    _replicer(created, instance,
              audit_services.repliquer_depuis_presences, 'presences.AuditLog')


def replicer_journal_scolarite(sender, instance, created, **kwargs):
    _replicer(created, instance,
              audit_services.repliquer_depuis_scolarite, 'scolarite.JournalScolarite')


def replicer_journal_referentiel(sender, instance, created, **kwargs):
    _replicer(created, instance,
              audit_services.repliquer_depuis_referentiels,
              'referentiels.ReferentielJournal')


def brancher():
    """Connecte les récepteurs aux trois journaux pilotes (appelé au ready())."""
    from presences.models import AuditLog
    from referentiels.models import ReferentielJournal
    from scolarite.models import JournalScolarite

    branchements = (
        (AuditLog, replicer_audit_log, DISPATCH['presences.AuditLog']),
        (JournalScolarite, replicer_journal_scolarite,
         DISPATCH['scolarite.JournalScolarite']),
        (ReferentielJournal, replicer_journal_referentiel,
         DISPATCH['referentiels.ReferentielJournal']),
    )
    for modele, recepteur, dispatch_uid in branchements:
        post_save.connect(
            recepteur, sender=modele, dispatch_uid=dispatch_uid, weak=False,
        )
