"""Lot L4a (suite) — convergence des groupes Django après `post_migrate`.

`authentication.apps._on_post_migrate_ensure_roles` appelle `ensure_role_groups()`
sur le signal `post_migrate`. Ce signal peut se déclencher **entre** le
`AlterField` (0021) et le `RunPython` de renommage (0022) : les groupes
canoniques `ROLE_INJS_ADMIN` / `ROLE_CHEF_INJS_ADMIN` sont alors créés par
`get_or_create` **avant** que le renommage ne les atteigne, laissant un doublon :

    ROLE_CPFAE_ADMIN (legacy, peuplé)  +  ROLE_INJS_ADMIN (nouveau, peuplé)
    → les mêmes droits comptés deux fois.

Cette migration reported les deux groupes en un seul, sans jamais retirer de
droit : permissions et utilisateurs du groupe legacy sont ré-attribués au groupe
canonique, puis le legacy vide est supprimé.

Elle est idempotente : rejouée sur un état déjà convergé, elle ne fait rien.
"""

from django.db import migrations

MAPPING_ROLES = {
    'CPFAE_ADMIN': 'INJS_ADMIN',
    'CHEF_CPFAE_ADMIN': 'CHEF_INJS_ADMIN',
}


def converger_groupes(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')

    for ancien, nouveau in MAPPING_ROLES.items():
        nom_legacy, nom_canonique = f'ROLE_{ancien}', f'ROLE_{nouveau}'
        legacy = Group.objects.filter(name=nom_legacy).first()
        if legacy is None:
            # Déjà convergé (ou jamais migré) : rien à faire.
            continue

        canonique = Group.objects.filter(name=nom_canonique).first()
        if canonique is None:
            # Cas nominal : le legacy EST le groupe canonique, on le renomme.
            # Renommer (et non recréer) conserve ses permissions et ses membres.
            legacy.name = nom_canonique
            legacy.save(update_fields=['name'])
            continue

        # Doublon : le canonique est l'autorité, on fusionne le legacy dedans.
        # `add()` (et non `set()`) ne retire jamais une permission existante.
        canonique.permissions.add(*legacy.permissions.all())
        canonique.user_set.add(*legacy.user_set.all())
        legacy.delete()


def ne_rien_faire(apps, schema_editor):
    """L'annulation est volontairement neutre : la convergence ne detruit rien.

    Repartir d'un etat intermediaire (groupes legacy et canoniques
    coexistant) reste sur ; recreer un doublon serait en revanche nuisible.
    On prefere donc un retour arriere neutre a une reconstruction risquee.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0022_migration_roles_injs'),
    ]

    operations = [
        migrations.RunPython(converger_groupes, ne_rien_faire),
    ]
