"""U3 — chargement du référentiel INJS (rôles A1, permissions A3, matrice A2).

Migration de DONNÉES idempotente : elle ne crée aucune table, elle peuple
les tables existantes à partir du package ``habilitations.referentiel``. La
repasser ne crée aucun doublon (``update_or_create`` sur les codes stables).

Le retour arrière ne supprime aucune ligne (règle S5) : il rend inactifs les
rôles et permissions du catalogue. La commande ``charger_referentiel_injs``
refait le même chargement sans toucher aux migrations.

Isolation des tests du socle (règle R5) : pendant ``manage.py test``, la
constitution de la base de test NE peuple pas le référentiel, afin que les
tests U1/U2 — qui créent leurs propres permissions avec des codes du
catalogue — retrouvent exactement des tables vides comme avant U3. Le
comportement de la migration est alors prouvé par un test dédié
(``test_referentiel_injs.MigrationChargementTests``) qui appelle
explicitement les deux fonctions. Poser ``CURP_FORCER_REFERENTIEL=1`` force
le peuplement même sous tests.
"""
import os
import sys

from django.db import migrations


def _en_contexte_de_test():
    return 'test' in sys.argv[:2]


def charger(apps, schema_editor):
    if _en_contexte_de_test() and os.environ.get('CURP_FORCER_REFERENTIEL') != '1':
        return
    from habilitations.referentiel.chargement import charger_referentiel
    charger_referentiel()


def decharger(apps, schema_editor):
    if _en_contexte_de_test() and os.environ.get('CURP_FORCER_REFERENTIEL') != '1':
        return
    from habilitations.referentiel.chargement import desactiver_referentiel
    desactiver_referentiel()


class Migration(migrations.Migration):

    dependencies = [
        ('habilitations', '0004_alter_permissionmetier_action'),
    ]

    operations = [
        migrations.RunPython(charger, reverse_code=decharger),
    ]
