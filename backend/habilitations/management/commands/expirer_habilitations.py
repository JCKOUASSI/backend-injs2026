"""Expiration à terme des attributions, dérogations et délégations (U5).

Applique la date de fin convenue à la création, émet les notifications
J-7 (une seule par objet) et termine les délégations. No-op total tant que
le drapeau ``flag.curp_expiration_auto`` est fermé (défaut).

Planification de production (quotidienne) :

    python manage.py expirer_habilitations
"""
from django.core.management.base import BaseCommand

from habilitations.services.drapeaux import expiration_active
from habilitations.services.expirations import expirer_termes


class Command(BaseCommand):
    help = "Expire les attributions/dérogations/délégations arrivées à terme."

    def handle(self, *args, **options):
        if not expiration_active():
            self.stdout.write(self.style.WARNING(
                "flag.curp_expiration_auto fermé : aucune expiration (no-op)."
            ))
            return
        bilan = expirer_termes()
        self.stdout.write(
            "Expirations : "
            f"{bilan['attributions']} attribution(s), "
            f"{bilan['derogations']} dérogation(s), "
            f"{bilan['delegations']} délégation(s) terminée(s), "
            f"{bilan['comptes']} compte(s), {bilan['invitations']} invitation(s) ; "
            f"{bilan['preavis']} préavis J-7 émis."
        )
