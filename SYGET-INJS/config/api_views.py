"""Endpoints JSON (session + permissions Django, sans DRF)."""

from __future__ import annotations

import json
from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.utils.dateparse import parse_date, parse_time
from django.views import View

from shared.formations_scope import get_formation_pour_utilisateur, get_groupe_pour_utilisateur, queryset_formations


def _json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def _seance_json(s) -> dict:
    return {
        "id": s.pk,
        "groupe_id": s.groupe_id,
        "groupe_nom": s.groupe.nom,
        "module_id": s.module_id,
        "module_titre": s.module.titre,
        "date": s.date.isoformat(),
        "heure_debut": s.heure_debut.isoformat(timespec="minutes"),
        "heure_fin": s.heure_fin.isoformat(timespec="minutes"),
        "duree_minutes": s.duree_minutes,
        "site_nom": s.site_nom,
        "batiment_nom": s.batiment_nom,
        "salle_nom": s.salle_nom,
        "salle_id": s.salle_id,
        "formateur_libelle": s.formateur_libelle,
        "formateur_referentiel_id": s.formateur_referentiel_id,
    }


class FormationsListAPIView(LoginRequiredMixin, View):
    """GET /api/formations/ — formations visibles par l'utilisateur."""

    def get(self, request):
        if not request.user.has_perm("formations.view_formation"):
            return JsonResponse({"detail": "Permission refusée."}, status=403)
        rows = list(
            queryset_formations(request.user).values(
                "id",
                "intitule",
                "vague",
                "date_debut",
                "date_fin",
                "responsable_id",
            )
        )
        return JsonResponse({"formations": rows})


class FormationSeancesAPIView(LoginRequiredMixin, View):
    """GET /api/formations/<pk>/seances/ — séances des groupes d'une formation."""

    def get(self, request, pk: int):
        if not request.user.has_perm("seances.view_seance"):
            return JsonResponse({"detail": "Permission refusée."}, status=403)
        try:
            formation = get_formation_pour_utilisateur(request.user, pk)
        except Http404:
            return JsonResponse({"detail": "Formation introuvable."}, status=404)

        from apps.seances.models import Seance

        seances = (
            Seance.objects.filter(groupe__formation_id=formation.pk)
            .select_related("groupe", "module", "salle", "formateur_referentiel")
            .order_by("date", "heure_debut")
        )
        return JsonResponse({"formation_id": formation.pk, "seances": [_seance_json(s) for s in seances]})


class SeanceDetailAPIView(LoginRequiredMixin, View):
    """GET/PATCH /api/seances/<pk>/ — lecture et mise à jour limitée d'une séance."""

    def _get_seance(self, request, pk: int):
        from apps.seances.models import Seance

        seance = (
            Seance.objects.select_related("groupe", "module", "salle", "formateur_referentiel").filter(pk=pk).first()
        )
        if seance is None:
            return None, JsonResponse({"detail": "Séance introuvable."}, status=404)
        try:
            get_groupe_pour_utilisateur(request.user, seance.groupe_id)
        except Http404:
            return None, JsonResponse({"detail": "Séance hors périmètre."}, status=404)
        return seance, None

    def get(self, request, pk: int):
        if not request.user.has_perm("seances.view_seance"):
            return JsonResponse({"detail": "Permission refusée."}, status=403)
        seance, err = self._get_seance(request, pk)
        if err:
            return err
        return JsonResponse(_seance_json(seance))

    def patch(self, request, pk: int):
        if not request.user.has_perm("seances.change_seance"):
            return JsonResponse({"detail": "Permission refusée."}, status=403)
        seance, err = self._get_seance(request, pk)
        if err:
            return err

        from apps.seances.api_validation import PATCH_ALLOWED_FIELDS, valider_patch_seance

        raw = _json_body(request)
        if not raw:
            return JsonResponse({"detail": "Corps JSON requis."}, status=400)

        unknown = set(raw.keys()) - PATCH_ALLOWED_FIELDS
        if unknown:
            return JsonResponse(
                {"detail": f"Champ(s) non autorisé(s) : {', '.join(sorted(unknown))}."},
                status=400,
            )

        parsed: dict = {}
        update_fields: list[str] = []
        for key, val in raw.items():
            if key == "date":
                parsed_date = parse_date(str(val))
                if parsed_date is None:
                    return JsonResponse({"detail": "Date invalide."}, status=400)
                parsed["date"] = parsed_date
                seance.date = parsed_date
                update_fields.append("date")
            elif key in ("heure_debut", "heure_fin"):
                parsed_t = parse_time(str(val))
                if parsed_t is None:
                    return JsonResponse({"detail": f"{key} invalide."}, status=400)
                parsed[key] = parsed_t
                setattr(seance, key, parsed_t)
                update_fields.append(key)
            else:
                stripped = str(val or "").strip()
                parsed[key] = stripped
                setattr(seance, key, stripped)
                update_fields.append(key)

        validation_errors = valider_patch_seance(seance, parsed)
        if validation_errors:
            return JsonResponse({"detail": " ; ".join(validation_errors)}, status=400)

        delta = datetime.combine(seance.date, seance.heure_fin) - datetime.combine(seance.date, seance.heure_debut)
        seance.duree_minutes = max(1, int(delta.total_seconds() // 60))
        update_fields.append("duree_minutes")

        from apps.formations.models import Formateur
        from apps.seances.planning.locations import charger_localisations_salles, salle_id_pour_nom

        localisations, salle_ids = charger_localisations_salles()
        seance.salle_id = salle_id_pour_nom(seance.salle_nom or "", salle_ids)
        cle_salle = (seance.salle_nom or "").strip().upper()
        if cle_salle and cle_salle in localisations:
            site, batiment, _cap = localisations[cle_salle]
            if site and not (seance.site_nom or "").strip():
                seance.site_nom = site
                update_fields.append("site_nom")
            if batiment and not (seance.batiment_nom or "").strip():
                seance.batiment_nom = batiment
                update_fields.append("batiment_nom")

        numero = (seance.formateur_numero or "").strip()
        email = (seance.formateur_email or "").strip()
        ref = Formateur.objects.filter(numero=numero).first() if numero else None
        if ref is None and email:
            ref = Formateur.objects.filter(email__iexact=email).first()
        seance.formateur_referentiel = ref

        all_fields = list(dict.fromkeys(update_fields + ["salle_id", "formateur_referentiel_id"]))
        seance.save(update_fields=all_fields)

        seance.refresh_from_db()
        return JsonResponse(_seance_json(seance))


class OpenAPISchemaView(LoginRequiredMixin, View):
    """GET /api/openapi.yaml — schéma OpenAPI 3 de l'API JSON."""

    def get(self, request):
        from pathlib import Path

        from django.conf import settings

        schema_path = Path(settings.BASE_DIR) / "docs" / "openapi.yaml"
        if not schema_path.exists():
            return JsonResponse({"detail": "Schéma OpenAPI introuvable."}, status=404)
        response = HttpResponse(schema_path.read_text(encoding="utf-8"), content_type="application/yaml")
        response["Content-Disposition"] = 'inline; filename="openapi.yaml"'
        return response
