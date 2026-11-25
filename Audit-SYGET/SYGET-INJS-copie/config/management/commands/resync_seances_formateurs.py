"""Realigne formateur_referentiel depuis le référentiel Formateur (numero puis email)."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.formations.models import Formateur
from apps.seances.models import Seance


class Command(BaseCommand):
    help = (
        "Synchronise formateur_referentiel des séances avec le référentiel Formateur "
        "(correspondance par numero, puis par email). Utile après import ou renommage."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les mises à jour sans les persister.",
        )
        parser.add_argument(
            "--formation-id",
            type=int,
            default=None,
            help="Limiter à une formation (via groupe.formation_id).",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        formation_id: int | None = options["formation_id"]

        qs = Seance.objects.filter(
            Q(formateur_numero__gt="") | Q(formateur_email__gt="") | Q(formateur_referentiel_id__isnull=False)
        )
        if formation_id:
            qs = qs.filter(groupe__formation_id=formation_id)

        updated = 0
        cleared = 0
        skipped = 0
        for seance in qs.select_related("formateur_referentiel"):
            numero = (seance.formateur_numero or "").strip()
            email = (seance.formateur_email or "").strip()
            if not numero and not email and not seance.formateur_referentiel_id:
                skipped += 1
                continue

            ref = Formateur.objects.filter(numero=numero).first() if numero else None
            if ref is None and email:
                ref = Formateur.objects.filter(email__iexact=email).first()

            new_id = ref.pk if ref else None
            if seance.formateur_referentiel_id == new_id:
                continue
            if new_id is None:
                cleared += 1
            updated += 1
            msg = (
                f"Séance pk={seance.pk} groupe={seance.groupe_id} "
                f"formateur_referentiel_id {seance.formateur_referentiel_id!r} -> {new_id!r}"
            )
            if dry_run:
                self.stdout.write(f"[dry-run] {msg}")
            else:
                seance.formateur_referentiel_id = new_id
                seance.save(update_fields=["formateur_referentiel_id"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Terminé : {updated} séance(s) {'à mettre à jour' if dry_run else 'mises à jour'} "
                f"({cleared} déréférencée(s)), {skipped} ignorée(s) sans identifiant formateur."
            )
        )
