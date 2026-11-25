from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("formations", "0007_remove_formationmodule_heures"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="formationmodule",
            unique_together=set(),
        ),
    ]
