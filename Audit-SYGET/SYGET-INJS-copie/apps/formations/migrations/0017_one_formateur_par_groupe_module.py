from django.db import migrations, models


def dedoublonner_affectations(apps, schema_editor):
    Affectation = apps.get_model("formations", "AffectationFormateurGroupe")
    seen = {}
    for row in Affectation.objects.all().order_by("-id"):
        key = (row.groupe_id, row.module_id)
        if key in seen:
            row.delete()
            continue
        seen[key] = row.id


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0016_affectationformateurgroupe"),
    ]

    operations = [
        migrations.RunPython(dedoublonner_affectations, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="affectationformateurgroupe",
            name="uniq_affectation_formateur_groupe_module",
        ),
        migrations.AddConstraint(
            model_name="affectationformateurgroupe",
            constraint=models.UniqueConstraint(
                fields=("groupe", "module"),
                name="uniq_formateur_par_groupe_module",
            ),
        ),
    ]
