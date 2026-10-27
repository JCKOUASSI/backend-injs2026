# Colonne `cycle` déjà présente sur certaines bases (NOT NULL) sans entrée dans l'historique Django.
# Colonne `cycle` déjà présente sur certaines bases (NOT NULL) sans entrée dans l'historique Django.
# Compatible SQLite (pas de IF NOT EXISTS dans ALTER TABLE SQLite).

from django.db import migrations, models, connection


def _add_cycle_column_if_not_exists(apps, schema_editor):
    """Ajoute la colonne cycle si elle n'existe pas (SQLite compatible)."""
    from django.db import connection
    cursor = connection.cursor()
    try:
        cursor.execute(
            "ALTER TABLE formations_module "
            "ADD COLUMN cycle varchar(255) NOT NULL DEFAULT '';"
        )
    except Exception:
        # Colonne existe déjà ou autre erreur — on ignore
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0058_add_refvague'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    code=_add_cycle_column_if_not_exists,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='module',
                    name='cycle',
                    field=models.CharField(
                        blank=True,
                        default='',
                        help_text='Libellé du cycle de formation (ex. même valeur que Formation.formation)',
                        max_length=255,
                    ),
                ),
            ],
        ),
    ]
