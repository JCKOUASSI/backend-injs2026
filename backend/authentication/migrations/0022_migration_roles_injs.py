"""Lot L4a — migration contrôlée des rôles RBAC INJS-LMD.

    CPFAE_ADMIN       -> INJS_ADMIN
    CHEF_CPFAE_ADMIN  -> CHEF_INJS_ADMIN

Périmètre strict : les valeurs persistées de `User.role`, les groupes Django
`ROLE_*` associés et leurs permissions. Ni compte, ni mot de passe, ni statut,
ni relation métier n'est modifié.

Garanties :
- **idempotente** : rejouable sans effet de bord (reconnaît l'état déjà migré) ;
- **non destructive** : aucun `DELETE`/`DROP` ; les groupes legacy ne sont
  supprimés que s'ils sont devenus vides, ce qui est vérifié dans la même
  opération ;
- **réversible** : la fonction inverse restaure les valeurs legacy.

Les permissions ne sont jamais recalculées depuis la politique : elles sont
**transférées telles quelles** du groupe legacy vers le groupe canonique, ce qui
garantit `permissions_avant == permissions_apis` sans perte ni élévation.
"""

from django.db import migrations

# Mapping strict : ancien rôle -> nouveau rôle.
MAPPING_ROLES = {
    'CPFAE_ADMIN': 'INJS_ADMIN',
    'CHEF_CPFAE_ADMIN': 'CHEF_INJS_ADMIN',
}
# Même mapping appliqué aux noms de groupes Django (`ROLE_<rôle>`).


def _migrer(apps, schema_editor, mapping):
    User = apps.get_model('authentication', 'User')
    Group = apps.get_model('auth', 'Group')

    # 1) Valeurs de rôle persistées sur les comptes.
    for ancien, nouveau in mapping.items():
        User.objects.filter(role=ancien).update(role=nouveau)

    # 2) Groupes Django : renommage en conservant l'identifiant de groupe.
    #    ⚠️ Le nom stocké est `ROLE_<rôle>` : on compare sur le nom préfixé, sinon
    #    le filtre ne matche rien et le groupe legacy survit en doublon.
    #    Renommer (et non recréer) garantit que les permissions et les
    #    utilisateurs attachés restent intacts.
    for ancien, nouveau in mapping.items():
        Group.objects.filter(name=f'ROLE_{ancien}').update(name=f'ROLE_{nouveau}')

    # 3) Purge des groupes legacy devenus vides ET orphelins (aucun
    #    utilisateur, aucune permission). Un groupe legacy encore peuplé est
    #    conservé : la migration ne détruit jamais de droits.
    for ancien in mapping:
        legacy = Group.objects.filter(name=f'ROLE_{ancien}').first()
        if legacy is None:
            continue
        a_utilisateurs = legacy.user_set.exists()
        a_permissions = legacy.permissions.exists()
        if not a_utilisateurs and not a_permissions:
            legacy.delete()


def vers_injs(apps, schema_editor):
    _migrer(apps, schema_editor, MAPPING_ROLES)


def vers_legacy(apps, schema_editor):
    _migrer(apps, schema_editor, {v: k for k, v in MAPPING_ROLES.items()})


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0021_alter_user_role'),
    ]

    operations = [
        migrations.RunPython(vers_injs, vers_legacy),
    ]


