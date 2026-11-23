"""Paramètre la géofence (périmètre de badgeage) d'un site INJS.

La règle métier « alerte ET refus hors périmètre » (arbitrage A-02 du
26/09/2026) n'a d'effet que si le site porte des coordonnées. Sur la base
officielle `injs_lmd_current`, le site `INJS MARCORY` avait
`geofence_latitude = NULL` : `_check_geofence()` retournait toujours
`(True, ...)` et **aucun badgeage ne pouvait être refusé pour cause de
position** (audit AUDIT-INJS-LMD-2026-09-26.md, § 9.2 et § 24).

Cette commande est **idempotente** : la relancer avec les mêmes valeurs ne
produit aucun changement. Elle n'effectue ni suppression ni réinitialisation —
elle met à jour les seules colonnes de géofence du site visé.

Coordonnées officielles de l'INJS Marcory (arbitrage A-03 du 26/09/2026) :
``5.3083 / -3.9825``.

Usage :
    python manage.py set_geofence_site --site "INJS MARCORY" \\
        --lat 5.3083 --lon -3.9825 --rayon 200

    # Sans --site : applique les coordonnées au seul site actif de la base.
    python manage.py set_geofence_site --dry-run

    # Retire volontairement le contrôle de périmètre (retour arrière).
    python manage.py set_geofence_site --site "INJS MARCORY" --desactiver
"""
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from formations.models import RefSite

#: Coordonnées officielles validées par le commanditaire le 26/09/2026.
LAT_OFFICIELLE = Decimal('5.308300')
LON_OFFICIELLE = Decimal('-3.982500')
#: Rayon par défaut, aligné sur ``MOBILE_GEOFENCE_DEFAULT_RADIUS_M``.
RAYON_DEFAUT = 200


class Command(BaseCommand):
    help = "Paramètre (ou retire) la géofence d'un site : contrôle de périmètre du badgeage."

    def add_arguments(self, parser):
        parser.add_argument('--site', dest='site', default=None,
                            help="Nom du site (casse insensible). Omis : le site actif unique.")
        parser.add_argument('--lat', dest='lat', default=None, help="Latitude (degrés décimaux).")
        parser.add_argument('--lon', dest='lon', default=None, help="Longitude (degrés décimaux).")
        parser.add_argument('--rayon', dest='rayon', type=int, default=RAYON_DEFAUT,
                            help=f"Rayon autorisé en mètres (défaut {RAYON_DEFAUT}).")
        parser.add_argument('--desactiver', dest='desactiver', action='store_true',
                            help="Retire la géofence : le contrôle de périmètre redevient inopérant.")
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            help="Affiche le résultat sans écrire en base.")

    def _resoudre_site(self, nom):
        if nom:
            site = RefSite.objects.filter(nom__iexact=nom).first()
            if site is None:
                raise CommandError(
                    f"Site introuvable : {nom!r}. "
                    f"Sites disponibles : {', '.join(RefSite.objects.values_list('nom', flat=True)) or '(aucun)'}"
                )
            return site
        sites = list(RefSite.objects.filter(actif=True)[:2])
        if not sites:
            raise CommandError("Aucun site actif. Précisez --site.")
        if len(sites) > 1:
            raise CommandError(
                f"Plusieurs sites actifs ({', '.join(s.nom for s in sites)}) : "
                f"précisez --site pour ne pas modifier la mauvaise entrée."
            )
        return sites[0]

    @transaction.atomic
    def handle(self, *args, **options):
        site = self._resoudre_site(options['site'])
        dry_run = options['dry_run']

        avant = (site.geofence_latitude, site.geofence_longitude, site.geofence_rayon_m)

        if options['desactiver']:
            if dry_run:
                self.stdout.write(f"[dry-run] {site.nom} : géofence {avant} -> (None, None, "
                                 f"{site.geofence_rayon_m})")
                return
            site.geofence_latitude = None
            site.geofence_longitude = None
            site.save(update_fields=['geofence_latitude', 'geofence_longitude'])
            self.stdout.write(self.style.WARNING(
                f"⚠ Géofence retirée pour « {site.nom} » : le badgeage ne vérifierra plus la position."))
            return

        if options['lat'] is None or options['lon'] is None:
            options['lat'] = LAT_OFFICIELLE
            options['lon'] = LON_OFFICIELLE
            self.stdout.write(self.style.WARNING(
                f"⚠ --lat/--lon absents : application des coordonnées officielles "
                f"{LAT_OFFICIELLE} / {LON_OFFICIELLE} (arbitrage A-03 du 26/09/2026)."))
        try:
            lat = Decimal(str(options['lat']))
            lon = Decimal(str(options['lon']))
        except (InvalidOperation, ValueError) as exc:
            raise CommandError(f"Coordonnées invalides : {exc}") from exc
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise CommandError(f"Coordonnées hors bornes : lat={lat} lon={lon}")
        rayon = int(options['rayon'])
        if rayon <= 0:
            raise CommandError(f"Rayon invalide : {rayon}")

        if dry_run:
            self.stdout.write(f"[dry-run] {site.nom} : géofence {avant} -> "
                             f"({lat}, {lon}, {rayon})")
            return

        site.geofence_latitude = lat
        site.geofence_longitude = lon
        site.geofence_rayon_m = rayon
        site.save(update_fields=['geofence_latitude', 'geofence_longitude', 'geofence_rayon_m'])

        self.stdout.write(self.style.SUCCESS(
            f"✓ Géofence appliquée — « {site.nom} » : {lat} / {lon} (rayon {rayon} m)"))
        self.stdout.write(
            f"  Avant : {avant[0]} / {avant[1]} (rayon {avant[2]} m)"
            if avant[0] is not None else "  Avant : aucune géofence configurée")
        self.stdout.write("  Le contrôle de périmètre s'applique désormais aux deux canaux "
                          "de badgeage (legacy et EDT).")