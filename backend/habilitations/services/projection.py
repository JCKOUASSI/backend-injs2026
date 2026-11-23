"""Projection additive du dispositif d'habilitation pour les capacités UI.

La clé ``habilitations`` ajoutée à ``GET /api/auth/capabilities/`` ne fait
qu'annoncer l'état du dispositif : elle n'accorde ni ne retire aucune action.
Tout compte sans profil (la totalité du parc avant la migration U8) reçoit
``gouverne: false`` : l'affichage reste piloté exclusivement par l'ancien
dispositif.
"""
from ..models import CompteUtilisateur
from .moteur import mode_moteur


def projection_capacites(user):
    """Données exposées sous la clé ``habilitations`` des capacités."""
    mode = mode_moteur()
    if user is None or not getattr(user, 'is_authenticated', False):
        return {'gouverne': False, 'mode': mode}
    compte = (
        CompteUtilisateur.objects.filter(user=user)
        .select_related('user')
        .first()
    )
    if compte is None:
        return {'gouverne': False, 'mode': mode}
    return {
        'gouverne': True,
        'mode': mode,
        'statut': compte.statut,
        'canal': compte.canal,
        'mfa_actif': compte.mfa_actif,
        'attributions_actives': compte.attributions.filter(
            statut='ACTIVE'
        ).count(),
    }
