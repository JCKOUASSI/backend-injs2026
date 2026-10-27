"""Sérialiseurs du noyau (lecture seule, P01-01)."""
from rest_framework import serializers

from .models import EvenementAudit


class EvenementAuditSerializer(serializers.ModelSerializer):
    """Représentation figée d'un événement du journal unifié."""

    acteur_nom = serializers.SerializerMethodField()
    source_libelle = serializers.CharField(source='get_source_display', read_only=True)
    action_libelle = serializers.SerializerMethodField()

    class Meta:
        model = EvenementAudit
        fields = (
            'code', 'source', 'source_libelle', 'action', 'action_libelle',
            'horodatage', 'acteur', 'acteur_nom', 'acteur_label',
            'objet_type', 'objet_id', 'objet_libelle', 'detail', 'ip_address',
        )
        read_only_fields = fields

    def get_acteur_nom(self, obj):
        if obj.acteur_id is None:
            return obj.acteur_label or None
        acteur = obj.acteur
        nom = ' '.join(
            partie for partie in (getattr(acteur, 'first_name', ''),
                                  getattr(acteur, 'last_name', ''))
            if partie
        )
        return nom or acteur.get_username()

    def get_action_libelle(self, obj):
        """Libellé humain quand l'action correspond à un choix d'un journal source."""
        for modele in _MODELES_SOURCES:
            choix = getattr(getattr(modele, 'Action', None), 'choices', None)
            if choix:
                for valeur, libelle in choix:
                    if valeur == obj.action:
                        return libelle
        return obj.action


# Résolution paresseuse des modèles sources pour les libellés d'actions.
def _charger_modeles_sources():
    from presences.models import AuditLog
    from referentiels.models import ReferentielJournal
    from scolarite.models import JournalScolarite
    return (AuditLog, JournalScolarite, ReferentielJournal)


_MODELES_SOURCES = _charger_modeles_sources()
