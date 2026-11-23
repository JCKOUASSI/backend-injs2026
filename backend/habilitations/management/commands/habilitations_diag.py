"""Diagnostic en lecture seule du socle d'habilitation (U1, non bloquant).

Signale, sans jamais modifier ni refuser quoi que ce soit :
* les comptes d'authentification sans profil CURP (normal avant la migration
  U8) ;
* les personnes en doublon probable ;
* les attributions qui enfreignent une règle déclarée (incompatibilité,
  module absent, seconde signature manquante, périmètre de secrétariat) ;
* les dérogations et délégations actives en base mais échues en date ;
* l'absence de politique de sécurité.

Le code de sortie reste 0 : U1 OBSERVE et n'applique encore aucune règle.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from habilitations.models import (
    AttributionRole,
    DelegationHabilitation,
    PermissionAttribuee,
    Personne,
    PolitiqueSecurite,
)
from habilitations.services.identite import identifier_doublons

User = get_user_model()


class Command(BaseCommand):
    help = "Signale les anomalies d'habilitation (lecture seule, ne bloque pas)."

    def handle(self, *args, **options):
        lignes = []
        aujourdhui = timezone.localdate()

        sans_profil = User.objects.filter(profil_habilitation__isnull=True).count()
        lignes.append(f"Comptes sans profil CURP : {sans_profil} (attendu avant U8).")

        if not PolitiqueSecurite.objects.exists():
            lignes.append("Politique de sécurité absente (lancer init_habilitations_injs).")

        groupes = identifier_doublons()
        lignes.append(f"Groupes de personnes en doublon probable : {len(groupes)}.")
        for groupe in groupes:
            lignes.append(f"  - critère {groupe['critere']} → personnes {groupe['personnes']}")

        for attribution in AttributionRole.objects.select_related('role', 'compte'):
            for code in attribution.contraintes():
                lignes.append(
                    f"Attribution {attribution.compte_id}/{attribution.role.code} : {code}"
                )
            if attribution.statut == AttributionRole.Statut.ACTIVE and \
                    attribution.date_fin and aujourdhui > attribution.date_fin:
                lignes.append(
                    f"Attribution {attribution.compte_id}/{attribution.role.code} "
                    "ACTIVE mais date de fin dépassée."
                )

        derogations_echues = PermissionAttribuee.objects.filter(
            statut=PermissionAttribuee.Statut.ACTIVE,
            date_fin__lt=aujourdhui,
        ).count()
        lignes.append(f"Dérogations ACTIVES mais échues : {derogations_echues}.")

        delegations_echues = DelegationHabilitation.objects.filter(
            statut=DelegationHabilitation.Statut.ACTIVE,
            date_fin__lt=aujourdhui,
        ).count()
        lignes.append(f"Délégations ACTIVES mais échues : {delegations_echues}.")

        lignes.append(f"Personnes référencées : {Personne.objects.count()}.")

        self.stdout.write(self.style.MIGRATE_HEADING("DIAGNOSTIC HABILITATIONS"))
        for ligne in lignes:
            self.stdout.write(f"  · {ligne}")
        self.stdout.write(self.style.SUCCESS("Diagnostic terminé (indicatif, non bloquant)."))
