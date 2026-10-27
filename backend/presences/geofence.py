"""Contrôle de périmètre géographique — source de vérité unique du badgeage mobile.

Ce module factorise la logique de géolocalisation utilisée par **les deux canaux**
de badgeage :

- le canal **legacy** ``/api/scan/secure/`` (``SessionModule``) ;
- le canal **EDT / LMD** ``/api/presences/seances-edt/scan/`` (``AffectationCreneau``).

Avant cette factorisation, la fonction ``_check_geofence`` de ``presences/views.py``
n'était appelée **que** par le canal legacy : le canal EDT enregistrait la position
reçue sans jamais la vérifier. Le présent module garantit que les deux canaux
appliquent exactement la même règle.

Règles appliquées (identiques à celles du canal legacy, à ne pas diverger) :

- si le site n'a **pas** de coordonnées configurées → aucun contrôle (comportement
  historique, site non géolocalisé) ;
- précision GPS supérieure à ``MOBILE_GEOFENCE_MAX_ACCURACY_M`` → refus
  ``LOCATION_INACCURATE`` ;
- distance supérieure au rayon du site → refus ``OUT_OF_GEOFENCE``.

Décision métier du commanditaire (26/09/2026, arbitrage A-02) : **alerte ET refus**
hors périmètre.
"""
from math import atan2, cos, radians, sin, sqrt

from django.conf import settings

#: Rayon appliqué quand ``RefSite.geofence_rayon_m`` est vide.
RAYON_DEFAUT_ATTR = 'MOBILE_GEOFENCE_DEFAULT_RADIUS_M'
#: Précision GPS maximale tolérée avant refus.
PRECISION_MAX_ATTR = 'MOBILE_GEOFENCE_MAX_ACCURACY_M'


def distance_meters(lat1, lon1, lat2, lon2):
    """Distance approximative en mètres entre deux points (formule de haversine)."""
    rayon_terre_m = 6371000
    phi1 = radians(float(lat1))
    phi2 = radians(float(lat2))
    d_phi = radians(float(lat2) - float(lat1))
    d_lambda = radians(float(lon2) - float(lon1))
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * rayon_terre_m * atan2(sqrt(a), sqrt(1 - a))


def rayon_du_site(site):
    """Rayon autorisé du site, à défaut de ``MOBILE_GEOFENCE_DEFAULT_RADIUS_M``."""
    rayon = getattr(site, 'geofence_rayon_m', None)
    if not rayon:
        rayon = getattr(settings, RAYON_DEFAUT_ATTR, 200)
    return float(rayon)


def site_non_localise(site):
    """True si le site n'a pas de géofence exploitable."""
    return site is None or site.geofence_latitude is None or site.geofence_longitude is None


def site_de_seance_edt(affectation):
    """``RefSite`` d'une ``AffectationCreneau``.

    ``AffectationCreneau`` ne porte pas de FK vers ``RefSite`` : le rattachement
    passe par la salle planifiée (``RefSalle.site``). À défaut de salle
    renseignée ou connue, on retombe sur l'unique site actif afin de ne pas
    laisser un site géolocalisé sans effet.

    Retourne ``None`` si aucun site ne peut être déterminé.
    """
    from formations.models import RefSalle, RefSite

    nom_salle = (getattr(affectation, 'salle_nom', '') or '').strip()
    if nom_salle:
        salle = RefSalle.objects.filter(nom__iexact=nom_salle).select_related('site').first()
        site = getattr(salle, 'site', None)
        if site is not None:
            return site

    sites = list(RefSite.objects.filter(actif=True)[:2])
    if len(sites) == 1:
        return sites[0]
    return None


def verifier_position(site, latitude, longitude, accuracy_m=None):
    """Vérifie une position face au périmètre d'un site.

    Retourne ``(ok, code, detail, distance_m, rayon_m)`` — signature identique à
    celle de l'ancien ``_check_geofence`` de ``views.py`` afin de préserver le
    comportement du canal legacy.
    """
    if site_non_localise(site):
        return True, None, None, None, None

    precision_max = getattr(settings, PRECISION_MAX_ATTR, 80)
    if accuracy_m is not None and float(accuracy_m) > float(precision_max):
        return (
            False,
            'LOCATION_INACCURATE',
            f"Précision GPS insuffisante ({round(float(accuracy_m), 1)}m). "
            f"Seuil maximum autorisé: {precision_max}m.",
            None,
            None,
        )

    rayon_m = rayon_du_site(site)
    distance_m = distance_meters(latitude, longitude, site.geofence_latitude, site.geofence_longitude)
    if distance_m > rayon_m:
        return (
            False,
            'OUT_OF_GEOFENCE',
            f"Hors périmètre autorisé ({round(distance_m, 1)}m du site, "
            f"rayon max {round(rayon_m, 1)}m).",
            distance_m,
            rayon_m,
        )

    return True, None, None, distance_m, rayon_m


def verifier_geofence_module(module, latitude, longitude, accuracy_m=None):
    """Contrôle pour le canal legacy : résout le site via ``Module.site``."""
    from formations.models import RefSite

    site = getattr(module, 'site', None)
    if site is None:
        site_id = getattr(module, 'site_id', None)
        if site_id:
            site = RefSite.objects.filter(pk=site_id).first()

    if site is None:
        # Repli legacy : correspondance par nom.
        nom_site = (getattr(module, 'site_legacy', '') or '').strip()
        if nom_site:
            site = RefSite.objects.filter(nom__iexact=nom_site).first()

    return verifier_position(site, latitude, longitude, accuracy_m)
