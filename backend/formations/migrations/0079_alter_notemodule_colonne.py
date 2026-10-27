import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0078_note_module_colonnes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notemodule',
            name='colonne',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='valeurs',
                to='formations.notemodulecolonne',
            ),
        ),
    ]
