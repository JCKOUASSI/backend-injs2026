"""Context processors partagés pour les templates."""

from shared.formations_scope import utilisateur_voit_toutes_les_formations


def perimetre_utilisateur(request):
    """Expose le périmètre gestionnaire pour afficher une bannière d'information."""
    if request.user.is_authenticated and not utilisateur_voit_toutes_les_formations(request.user):
        return {
            "perimetre_gestionnaire_limite": True,
            "perimetre_gestionnaire_message": (
                "Vous ne voyez que les formations dont vous êtes responsable. "
                "La génération de planning tient compte de toutes les séances "
                "(salles et formateurs) pour éviter les collisions."
            ),
        }
    return {"perimetre_gestionnaire_limite": False, "perimetre_gestionnaire_message": ""}
