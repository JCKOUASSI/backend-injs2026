from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parametrage", "0006_jourferie_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="moduletypeformation",
            name="grade_cible",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Grade ciblé (laisser vide pour tous les grades)",
                max_length=20,
            ),
        ),
        migrations.AlterUniqueTogether(
            name="moduletypeformation",
            unique_together={("module", "type_formation", "grade_cible")},
        ),
    ]
