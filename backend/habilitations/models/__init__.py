"""Modèles de l'application ``habilitations`` (socle CURP, unités U1, U4, U5).

Répartis par fichier selon la chaîne :
PERSONNE → COMPTE → RÔLE / PERMISSION → PÉRIMÈTRE → ATTRIBUTIONS/DÉLÉGATIONS,
avec la politique de sécurité, le journal append-only chaîné et les objets
du cycle de vie U5 (file de provisionnement, imports réversibles,
notifications).
"""
from .attribution import AttributionRole, PermissionAttribuee
from .compte import CompteUtilisateur
from .cycle_vie import (
    ExecutionImport,
    NotificationHabilitation,
    PropositionProvisionnement,
)
from .demande_acces import DemandeAcces
from .delegation import DelegationHabilitation
from .enums import (
    CanalAcces,
    DomaineMetier,
    NiveauAcces,
    SituationPersonne,
)
from .journal import (
    JournalHabilitation,
    JournalImmuableError,
    JournalQuerySet,
)
from .perimetre import Perimetre
from .permission import PermissionMetier
from .personne import Personne
from .politique import PolitiqueSecurite
from .role import RoleMetier
from .version_role import CHAMPS_VERSIONNES, RoleVersion

__all__ = [
    'Personne',
    'CompteUtilisateur',
    'RoleMetier',
    'RoleVersion',
    'CHAMPS_VERSIONNES',
    'PermissionMetier',
    'Perimetre',
    'AttributionRole',
    'PermissionAttribuee',
    'DemandeAcces',
    'DelegationHabilitation',
    'PropositionProvisionnement',
    'ExecutionImport',
    'NotificationHabilitation',
    'PolitiqueSecurite',
    'JournalHabilitation',
    'JournalImmuableError',
    'JournalQuerySet',
    'NiveauAcces',
    'CanalAcces',
    'DomaineMetier',
    'SituationPersonne',
]
