"""Lot L4b — verrouillage du RBAC INJS-LMD au niveau de la base.

La contrainte applicative (`User.Role.choices`) n'est pas une contrainte SQL :
PostgreSQL accepterait encore d'écrire `CPFAE_ADMIN` dans
`authentication_user.role` par un script, un import ou une requête directe.
Ce lot ajoute une contrainte `CHECK` qui rend cette écriture impossible.

Sémantique retenue :
- les **12 rôles canoniques** sont acceptés ;
- toute autre valeur est refusée (`CPFAE_ADMIN`, `CHEF_CPFAE_ADMIN`,
  `UNKNOWN_ROLE`, chaîne vide…).

**Pourquoi pas `AddConstraint` ?**
Sur SQLite, Django traduit `AddConstraint` en reconstruction complète de table :
`CREATE TABLE new__… ; INSERT … SELECT ; DROP TABLE ; ALTER … RENAME`. C'est un
`DROP TABLE` déguisé, interdit par la consigne et inacceptable sur
`authentication_user`. PostgreSQL reçoit donc un `ALTER TABLE … ADD CONSTRAINT` ;
SQLite reçoit deux triggers de validation, sans reconstruction de table.

La migration **échoue proprement** (`MigrationError`) si une valeur inattendue
est découverte : elle ne supprime ni ne réécrit jamais une ligne existante.
"""

from django.db import migrations, models

# Les 12 rôles canoniques INJS-LMD. La liste est figée : ajouter un rôle
# exige un arbitrage métier explicite, pas une édition opportuniste de cette
# migration (qui est déjà appliquée).
ROLES_CANONIQUES = (
    'ADMIN',
    'DIRECTION',
    'CHEF_INJS_ADMIN',
    'INJS_ADMIN',
    'CHEF_SECRETARIAT',
    'SECRETARIAT',
    'FINANCE',
    'ARCHIVE',
    'ENCADRANT',
    'SUPERVISEUR',
    'FORMATEUR',
    'AUDITEUR',
)

NOM_CONTRAINTE = 'auth_user_role_canonique_l4b'

# Même liste que ROLES_CANONIQUES, injectée dans le DDL. On écrit les valeurs
# en dur pour que le SQL reste lisible dans l'historique des migrations.
_VALEURS_SQL = ", ".join(f"'{r}'" for r in ROLES_CANONIQUES)

AJOUTER_CONTRAINTE = (
    'ALTER TABLE "authentication_user" '
    f'ADD CONSTRAINT "{NOM_CONTRAINTE}" '
    f'CHECK ("role" IN ({_VALEURS_SQL}))'
)
RETOURNER_CONTRAINTE = (
    'ALTER TABLE "authentication_user" '
    f'DROP CONSTRAINT IF EXISTS "{NOM_CONTRAINTE}"'
)

NOM_TRIGGER_INSERT = f'{NOM_CONTRAINTE}_insert'
NOM_TRIGGER_UPDATE = f'{NOM_CONTRAINTE}_update'
SQLITE_AJOUTER_TRIGGER_INSERT = (
    f'CREATE TRIGGER IF NOT EXISTS "{NOM_TRIGGER_INSERT}" '
    'BEFORE INSERT ON "authentication_user" '
    f'WHEN NEW."role" NOT IN ({_VALEURS_SQL}) '
    "BEGIN SELECT RAISE(ABORT, 'role hors nomenclature canonique'); END"
)
SQLITE_AJOUTER_TRIGGER_UPDATE = (
    f'CREATE TRIGGER IF NOT EXISTS "{NOM_TRIGGER_UPDATE}" '
    'BEFORE UPDATE OF "role" ON "authentication_user" '
    f'WHEN NEW."role" NOT IN ({_VALEURS_SQL}) '
    "BEGIN SELECT RAISE(ABORT, 'role hors nomenclature canonique'); END"
)


def appliquer_contrainte_role(apps, schema_editor):
    """Pose le garde-fou sans reconstruire de table SQLite."""
    vendor = schema_editor.connection.vendor
    if vendor == 'postgresql':
        schema_editor.execute(AJOUTER_CONTRAINTE)
    elif vendor == 'sqlite':
        schema_editor.execute(SQLITE_AJOUTER_TRIGGER_INSERT)
        schema_editor.execute(SQLITE_AJOUTER_TRIGGER_UPDATE)
    else:
        raise migrations.exceptions.MigrationError(
            f'Lot L4b : backend SQL non pris en charge ({vendor!r}).'
        )


def retirer_contrainte_role(apps, schema_editor):
    """Retire le garde-fou correspondant au backend lors d'un rollback."""
    vendor = schema_editor.connection.vendor
    if vendor == 'postgresql':
        schema_editor.execute(RETOURNER_CONTRAINTE)
    elif vendor == 'sqlite':
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{NOM_TRIGGER_INSERT}"')
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{NOM_TRIGGER_UPDATE}"')


def verifier_donnees(apps, schema_editor):
    """Refuse d'appliquer la contrainte si des données sont hors nomenclature.

    On échoue ici plutôt que de « réparer » silencieusement : supprimer ou
    réécrire un compte n'est jamais acceptable dans une migration.
    """
    User = apps.get_model('authentication', 'User')
    hors = (
        User.objects.exclude(role__in=ROLES_CANONIQUES)
        .values_list('role', flat=True)
        .distinct()
    )
    # Une chaîne vide n'est pas un rôle canonique : la refuser explicitement
    # ici évite qu'elle ne survive en base SQLite, où le garde-fou est un trigger.
    hors = [r for r in hors if r is not None]
    if hors:
        raise migrations.exceptions.MigrationError(
            'Lot L4b : des comptes portent un rôle hors nomenclature canonique '
            f'INJS-LMD : {sorted(hors)!r}. Corriger ces comptes manuellement '
            'avant de rejouer la migration — aucune donnée ne sera modifiée '
            'automatiquement.'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0023_converger_groupes_roles_injs'),
    ]

    operations = [
        migrations.RunPython(verifier_donnees, migrations.RunPython.noop),
        migrations.RunPython(
            code=appliquer_contrainte_role,
            reverse_code=retirer_contrainte_role,
        ),
    ]
