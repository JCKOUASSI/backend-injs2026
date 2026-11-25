from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("formations", "0010_alter_inscription_unique_together_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="formationmodule",
            name="site_nom",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Nom(s) des sites (CSV)",
                max_length=500,
            ),
        ),
        migrations.AlterField(
            model_name="formationmodule",
            name="batiment_nom",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Nom(s) des bâtiments (CSV)",
                max_length=500,
            ),
        ),
        migrations.AlterField(
            model_name="formationmodule",
            name="salle_nom",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Nom(s) des salles (CSV)",
                max_length=500,
            ),
        ),
    ]
