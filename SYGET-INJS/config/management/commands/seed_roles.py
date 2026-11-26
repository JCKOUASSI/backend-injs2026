"""
Commande de gestion : seed_roles
Crée les groupes applicatifs et leur assigne les permissions Django associées.

Matrice cible :
- ADMIN_EDT          : full sur tout (planning, formations, auditeurs, groupes,
                       référentiels, paramétrage).
- GESTIONNAIRE_EDT   : full sur tout sauf paramétrage (lecture seule sur le
                       paramétrage, considéré sensible). Pas de delete sur
                       l'audit planning.
- DIRECTION_EDT      : lecture seule partout (vue planning + audit + métier).
- RUP_EDT            : un module référentiel par utilisateur ; lecture formations/groupes/séances ;
                       gestion des affectations formateurs pour ce module.
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

# Liste des modèles « écriture autorisée pour le gestionnaire »
# (app_label, model_name) — utilisée pour donner les 4 permissions natives.
WRITE_MODELS_GESTION = [
    ("seances", "seance"),
    ("formations", "formation"),
    ("formations", "formationmodule"),
    ("formations", "formateur"),
    ("formations", "affectationformateurgroupe"),
    ("formations", "inscription"),
    ("auditeurs", "auditeur"),
    ("groupes", "groupe"),
    ("groupes", "groupeauditeur"),
    ("groupes", "configgroupe"),
    ("groupes", "jourcours"),
    ("referentiels", "module"),
    ("referentiels", "specialite"),
    ("referentiels", "typeformation"),
    ("simulation", "scenariosimulation"),
]

# Paramétrage : lecture pour gestionnaire/direction, écriture pour admin seul.
PARAMETRAGE_MODELS = [
    ("parametrage", "grade"),
    ("parametrage", "vague"),
    ("parametrage", "site"),
    ("parametrage", "batiment"),
    ("parametrage", "salle"),
    ("parametrage", "parametregeneral"),
    ("parametrage", "parametreformation"),
    ("parametrage", "moduletypeformation"),
    ("parametrage", "jourferie"),
    ("parametrage", "periodedisponibilitesite"),
]

ALL_MODELS = (
    WRITE_MODELS_GESTION
    + PARAMETRAGE_MODELS
    + [
        ("seances", "planningauditlog"),
        ("seances", "planningrun"),
    ]
)


def _perms_for(models: list[tuple[str, str]], codenames: list[str]) -> list[Permission]:
    """Retourne la liste des permissions Django correspondant aux modèles et codenames."""
    perms: list[Permission] = []
    for app_label, model_name in models:
        try:
            ct = ContentType.objects.get(app_label=app_label, model=model_name)
        except ContentType.DoesNotExist:
            continue
        for codename in codenames:
            full_codename = f"{codename}_{model_name}"
            try:
                perms.append(Permission.objects.get(content_type=ct, codename=full_codename))
            except Permission.DoesNotExist:
                continue
    return perms


class Command(BaseCommand):
    """Crée/met à jour les groupes applicatifs et leurs permissions."""

    help = (
        "Crée les groupes ADMIN_EDT, GESTIONNAIRE_EDT, DIRECTION_EDT, RUP_EDT avec les "
        "permissions Django couvrant tout le périmètre fonctionnel."
    )

    ROLE_ADMIN = "ADMIN_EDT"
    ROLE_GESTIONNAIRE = "GESTIONNAIRE_EDT"
    ROLE_DIRECTION = "DIRECTION_EDT"
    ROLE_RUP = "RUP_EDT"

    READ_MODELS_RUP = [
        ("formations", "formation"),
        ("formations", "formationmodule"),
        ("formations", "formateur"),
        ("formations", "affectationformateurgroupe"),
        ("groupes", "groupe"),
        ("seances", "seance"),
    ]

    WRITE_MODELS_RUP = [
        ("formations", "affectationformateurgroupe"),
        ("formations", "formateur"),
    ]

    def handle(self, *args, **options) -> None:
        admin_group, _ = Group.objects.get_or_create(name=self.ROLE_ADMIN)
        gestion_group, _ = Group.objects.get_or_create(name=self.ROLE_GESTIONNAIRE)
        direction_group, _ = Group.objects.get_or_create(name=self.ROLE_DIRECTION)
        rup_group, _ = Group.objects.get_or_create(name=self.ROLE_RUP)

        # ADMIN : 4 permissions sur tous les modèles métiers + paramétrage + audit.
        admin_perms = _perms_for(ALL_MODELS, ["add", "change", "delete", "view"])
        admin_group.permissions.set(admin_perms)

        # GESTIONNAIRE : écriture sur tout sauf paramétrage ; lecture sur paramétrage
        # et sur l'audit planning (pas de delete sur audit).
        gestion_perms = _perms_for(WRITE_MODELS_GESTION, ["add", "change", "delete", "view"])
        gestion_perms += _perms_for(PARAMETRAGE_MODELS, ["view"])
        gestion_perms += _perms_for([("seances", "planningauditlog"), ("seances", "planningrun")], ["view"])
        gestion_group.permissions.set(gestion_perms)

        # DIRECTION : lecture seule sur tout le périmètre.
        direction_perms = _perms_for(ALL_MODELS, ["view"])
        direction_group.permissions.set(direction_perms)

        # RUP : lecture métier limitée + gestion affectations formateurs et référentiel formateurs.
        rup_perms = _perms_for(self.READ_MODELS_RUP, ["view"])
        rup_perms += _perms_for(self.WRITE_MODELS_RUP, ["add", "change", "view"])
        rup_perms += _perms_for([("formations", "affectationformateurgroupe")], ["delete"])
        rup_group.permissions.set(rup_perms)

        self.stdout.write(
            self.style.SUCCESS(
                "Rôles applicatifs créés/mis à jour : "
                f"{self.ROLE_ADMIN} ({len(admin_perms)} perms), "
                f"{self.ROLE_GESTIONNAIRE} ({len(gestion_perms)} perms), "
                f"{self.ROLE_DIRECTION} ({len(direction_perms)} perms), "
                f"{self.ROLE_RUP} ({len(rup_perms)} perms)."
            )
        )
