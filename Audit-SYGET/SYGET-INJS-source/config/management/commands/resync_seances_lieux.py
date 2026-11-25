"""Realigne site_nom, batiment_nom, salle_nom et salle_id depuis le référentiel paramétrage."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.seances.models import Seance
from apps.seances.planning.locations import charger_localisations_salles, salle_id_pour_nom


class Command(BaseCommand):
    help = (
        "Synchronise les champs lieu des séances avec le référentiel des salles actives "
        "(salle_id, noms site/bâtiment/salle). Utile après un renommage dans le paramétrage."
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
        localisations, salle_ids = charger_localisations_salles()

        qs = Seance.objects.filter(Q(salle_nom__gt="") | Q(salle_id__isnull=False))
        if formation_id:
            qs = qs.filter(groupe__formation_id=formation_id)

        updated = 0
        skipped = 0
        for seance in qs.select_related("salle__batiment__site"):
            nom_ref = (seance.salle_nom or "").strip()
            if not nom_ref and seance.salle_id:
                nom_ref = (seance.salle.nom if seance.salle_id else "").strip()
            if not nom_ref:
                skipped += 1
                continue

            cle = nom_ref.upper()
            loc = localisations.get(cle)
            new_salle_id = salle_id_pour_nom(nom_ref, salle_ids)
            if loc:
                site, batiment, _cap = loc
                new_site = site or seance.site_nom
                new_bat = batiment or seance.batiment_nom
                new_nom = nom_ref
            else:
                new_site = seance.site_nom
                new_bat = seance.batiment_nom
                new_nom = seance.salle_nom
                new_salle_id = None

            changed = (
                seance.salle_id != new_salle_id
                or (seance.site_nom or "") != (new_site or "")
                or (seance.batiment_nom or "") != (new_bat or "")
                or (seance.salle_nom or "") != (new_nom or "")
            )
            if not changed:
                continue
            updated += 1
            msg = (
                f"Séance pk={seance.pk} groupe={seance.groupe_id} "
                f"salle_id {seance.salle_id!r} -> {new_salle_id!r} "
                f"site {seance.site_nom!r} -> {new_site!r}"
            )
            if dry_run:
                self.stdout.write(f"[dry-run] {msg}")
            else:
                seance.salle_id = new_salle_id
                seance.site_nom = new_site or ""
                seance.batiment_nom = new_bat or ""
                seance.salle_nom = new_nom or ""
                seance.save(update_fields=["salle_id", "site_nom", "batiment_nom", "salle_nom"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Terminé : {updated} séance(s) {'à mettre à jour' if dry_run else 'mises à jour'}, "
                f"{skipped} ignorée(s) sans nom de salle."
            )
        )
