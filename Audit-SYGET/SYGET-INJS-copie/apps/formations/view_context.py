"""Construction de contexte template pour les vues formations."""

from __future__ import annotations

from apps.formations.forms import FormationModuleForm, FormationPeriodeForm
from apps.formations.models import Formation


def build_formation_detail_context(
    formation: Formation,
    module_form: FormationModuleForm,
    *,
    periode_form: FormationPeriodeForm | None = None,
) -> dict:
    """Contexte de la page détail formation."""
    from apps.parametrage.models import Batiment, ModuleTypeFormation, Salle
    from apps.referentiels.models import Module

    periodes = list(formation.periodes.all())
    return {
        "formation": formation,
        "module_form": module_form,
        "periode_form": periode_form or FormationPeriodeForm(formation=formation),
        "periodes": periodes,
        "modules_catalog_data": list(
            Module.objects.filter(
                actif=True,
                type_associations__type_formation_id=formation.type_formation_id,
            )
            .distinct()
            .values("id", "titre")
            .order_by("titre")
        ),
        "periodes_data": [
            {
                "id": p.pk,
                "libelle": p.libelle,
                "date_debut": p.date_debut.isoformat(),
                "date_fin": p.date_fin.isoformat(),
                "rythme": p.get_rythme_mensuel_display(),
            }
            for p in periodes
        ],
        "module_volumes_data": list(
            ModuleTypeFormation.objects.filter(type_formation_id=formation.type_formation_id)
            .values("module_id", "grade_cible", "volume_horaire_defaut")
            .order_by("module_id", "grade_cible")
        ),
        "batiments_data": list(
            Batiment.objects.filter(actif=True, site__isnull=False).values("id", "nom", "site_id").order_by("nom")
        ),
        "salles_data": list(
            Salle.objects.filter(actif=True, batiment__isnull=False).values("id", "nom", "batiment_id").order_by("nom")
        ),
    }


def location_json_context() -> dict:
    """Données sites/bâtiments/salles pour les formulaires module (JSON côté client)."""
    from apps.parametrage.models import Batiment, Salle

    return {
        "batiments_data": list(
            Batiment.objects.filter(actif=True, site__isnull=False).values("id", "nom", "site_id").order_by("nom")
        ),
        "salles_data": list(
            Salle.objects.filter(actif=True, batiment__isnull=False).values("id", "nom", "batiment_id").order_by("nom")
        ),
    }
