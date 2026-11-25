"""Renomme les groupes existants au format A4_GROUPE1."""

from django.core.management.base import BaseCommand

from apps.groupes.models import Groupe
from apps.groupes.services import GroupeService
from apps.groupes.repositories import (
    ConfigGroupeRepository,
    GroupeRepository,
    JourCoursRepository,
)


class Command(BaseCommand):
    help = "Renomme les groupes au format GRADE_GROUPEn (ex. A4_GROUPE1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--formation",
            type=int,
            default=None,
            help="ID formation (toutes les formations si omis).",
        )

    def handle(self, *args, **options):
        service = GroupeService(
            GroupeRepository(),
            ConfigGroupeRepository(),
            JourCoursRepository(),
        )
        formation_id = options.get("formation")
        if formation_id:
            formation_ids = [formation_id]
        else:
            formation_ids = list(Groupe.objects.values_list("formation_id", flat=True).distinct())

        total = 0
        for fid in formation_ids:
            n = service.normaliser_noms_groupes_formation(fid)
            if n:
                self.stdout.write(self.style.SUCCESS(f"Formation {fid} : {n} groupe(s) renommé(s)."))
            total += n
        self.stdout.write(self.style.SUCCESS(f"Total : {total} groupe(s) renommé(s)."))
