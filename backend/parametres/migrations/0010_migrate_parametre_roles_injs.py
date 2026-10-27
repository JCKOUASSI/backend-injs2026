"""Lot L4a — migration des listes de rôles stockées dans les paramètres.

`Parametre.modifiable_par_roles` et `Parametre.lecturable_par_roles` stockent un
tableau JSON de rôles. Après le renommage CPFAE → INJS, les valeurs enregistrées
en base désignent toujours l'ancien identifiant : sans cette migration de
données, un compte `INJS_ADMIN` perdrait ses droits de lecture/modification sur
les 40 paramètres concernés (perte de privilège).

La migration ne touche QUE les chaînes de rôles historiques :

    "CPFAE_ADMIN"      -> "INJS_ADMIN"
    "CHEF_CPFAE_ADMIN" -> "CHEF_INJS_ADMIN"

Aucun autre contenu n'est modifié : la structure JSON, l'ordre des éléments et
tous les autres rôles sont préservés à l'identique.
"""

import json

from django.db import migrations

MAPPING_ROLES = {
    'CPFAE_ADMIN': 'INJS_ADMIN',
    'CHEF_CPFAE_ADMIN': 'CHEF_INJS_ADMIN',
}


def _convertir(valeur_brute):
    """Remplace les rôles legacy dans un tableau JSON, sans toucher au reste."""
    if not valeur_brute or 'CPFAE' not in valeur_brute:
        return None
    try:
       roles = json.loads(valeur_brute)
    except (json.JSONDecodeError, TypeError):
        # Valeur non JSON : on n'interprète pas, on laisse tel quel.
        return None
    if not isinstance(roles, list):
        return None
    converti = [MAPPING_ROLES.get(r, r) for r in roles]
    # Déduplication en conservant l'ordre (au cas où la liste contenait les deux).
    vus, uniques = set(), []
    for r in converti:
        if r not in vus:
            vus.add(r)
            uniques.append(r)
    if converti == roles and uniques == roles:
        return None  # déjà migré
    return json.dumps(uniques, ensure_ascii=False)


def _migrer(apps, schema_editor, mapping):
    Parametre = apps.get_model('parametres', 'Parametre')
    for parametre in Parametre.objects.all().iterator():
        modifications = {}
        for champ in ('modifiable_par_roles', 'lecturable_par_roles'):
            converti = _convertir(getattr(parametre, champ))
            if converti is not None:
                modifications[champ] = converti
        if modifications:
            Parametre.objects.filter(pk=parametre.pk).update(**modifications)


def vers_injs(apps, schema_editor):
    _migrer(apps, schema_editor, MAPPING_ROLES)


def vers_legacy(apps, schema_editor):
    _migrer(apps, schema_editor, {v: k for k, v in MAPPING_ROLES.items()})


class Migration(migrations.Migration):

    dependencies = [
        ('parametres', '0009_alter_parametre_lecturable_par_roles_and_more'),
    ]

    operations = [
        migrations.RunPython(vers_injs, vers_legacy),
    ]
