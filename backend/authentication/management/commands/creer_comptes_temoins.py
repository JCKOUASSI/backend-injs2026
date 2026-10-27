"""U0 (CURP-INJS) — crée les comptes témoins du scénario de fumée.

Les 12 rôles existants disposent chacun d'un compte témoin ; les deux rôles
de secrétariat disposent en plus d'un second compte rattaché à un SECOND
secrétariat, afin que le cloisonnement puisse être prouvé par un test croisé
(un secrétariat ne doit jamais voir les données de l'autre). Soit 14 comptes.

La commande est IDEMPOTENTE (mise à jour ou création, les comptes ne sont
jamais supprimés) et ne réalise aucune création automatique hors de son appel
: aucune migration, aucun signal ne l'invoque. Les mots de passe viennent de la
variable d'environnement ``COMPTE_TEMOIN_MOT_DE_PASSE`` (défaut documenté pour
la base de démonstration uniquement) ; en recette/production réelles, cette
variable est obligatoire.

Usage :
    python manage.py creer_comptes_temoins
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authentication.role_groups import ROLE_GROUP_NAMES, ensure_role_groups

User = get_user_model()

MOT_DE_PASSE_DEFAUT = "Temoin#2026"

# (suffixe username, rôle, secrétariat de rattachement ou None)
COMPTES = [
    ("temoin_admin", User.Role.ADMIN, None),
    ("temoin_chef_cpfae_admin", User.Role.CHEF_INJS_ADMIN, None),
    ("temoin_cpfae_admin", User.Role.INJS_ADMIN, None),
    ("temoin_direction", User.Role.DIRECTION, None),
    ("temoin_chef_secretariat_a", User.Role.CHEF_SECRETARIAT, "A"),
    ("temoin_chef_secretariat_b", User.Role.CHEF_SECRETARIAT, "B"),
    ("temoin_secretariat_a", User.Role.SECRETARIAT, "A"),
    ("temoin_secretariat_b", User.Role.SECRETARIAT, "B"),
    ("temoin_finance", User.Role.FINANCE, None),
    ("temoin_archive", User.Role.ARCHIVE, None),
    ("temoin_encadrant", User.Role.ENCADRANT, None),
    ("temoin_superviseur", User.Role.SUPERVISEUR, None),
    ("temoin_formateur", User.Role.FORMATEUR, None),
    ("temoin_auditeur", User.Role.AUDITEUR, None),
]

SECRETARIATS_DEMO = {
    "A": {"numero": "SECR-DEMO-A", "nom": "Secrétariat témoin A"},
    "B": {"numero": "SECR-DEMO-B", "nom": "Secrétariat témoin B"},
}


class Command(BaseCommand):
    help = "Crée (idempotent) les 14 comptes témoins de la fumée d'authentification."

    def add_arguments(self, parser):
        parser.add_argument(
            '--mot-de-passe', dest='mdp', default=None,
            help="Mot de passe commun des comptes (sinon variable COMPTE_TEMOIN_MOT_DE_PASSE).",
        )

    def handle(self, *args, **options):
        mdp = (
            options['mdp']
            or os.environ.get('COMPTE_TEMOIN_MOT_DE_PASSE')
            or MOT_DE_PASSE_DEFAUT
        )

        # Les groupes ROLE_* doivent exister pour que la synchronisation des
        # utilisateurs s'appuie dessus (sinon le signal ne peut rien lier).
        ensure_role_groups()

        from formations.models import Secretariat
        secretariats = {}
        for cle, valeurs in SECRETARIATS_DEMO.items():
            obj, _ = Secretariat.objects.get_or_create(
                numero=valeurs["numero"], defaults={"nom": valeurs["nom"]}
            )
            secretariats[cle] = obj

        crees = maj = 0
        for username, role, secr_cle in COMPTES:
            secretariat = secretariats[secr_cle] if secr_cle else None
            compte, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "role": role,
                    "secretariat": secretariat,
                    "is_active": True,
                    "email": f"{username}@recette.injs.local",
                },
            )
            if created:
                compte.set_password(mdp)
                compte.role = role
                compte.secretariat = secretariat
                compte.is_active = True
                compte.save()
                crees += 1
            else:
                # On corrige uniquement les attributs de rattachement du témoin,
                # jamais son mot de passe (il peut avoir été changé à dessein).
                modifie = False
                if compte.role != role:
                    compte.role = role
                    modifie = True
                if secretariat and compte.secretariat_id != secretariat.id:
                    compte.secretariat = secretariat
                    modifie = True
                if not compte.is_active:
                    compte.is_active = True
                    modifie = True
                if modifie:
                    compte.save()
                    maj += 1

        self.stdout.write(self.style.SUCCESS(
            f"Comptes témoins prêts : {crees} créés, {maj} remis à jour, "
            f"{len(COMPTES) - crees - maj} déjà présents."
        ))
        self.stdout.write(
            f"Rôles couverts : {sorted({str(r) for _, r, _ in COMPTES})} ; "
            f"groupe associé à chaque rôle : ROLE_* "
            f"({len(ROLE_GROUP_NAMES)} rôles synchronisables)."
        )
        mobile = ", ".join(sorted(str(r) for r in User.objects.filter(
            username__startswith='temoin_'
        ).exclude(role__in=['FORMATEUR', 'AUDITEUR']).values_list('role', flat=True)))
        self.stdout.write(f"Connexion web attendue pour : {mobile}")
        self.stdout.write("Connexion web attendue REFUSÉE pour : AUDITEUR, FORMATEUR.")
