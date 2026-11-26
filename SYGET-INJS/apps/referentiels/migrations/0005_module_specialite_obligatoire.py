import django.db.models.deletion
from django.db import migrations, models


def creer_specialite_generale_et_remplir_modules(apps, schema_editor):
    Specialite = apps.get_model("referentiels", "Specialite")
    Module = apps.get_model("referentiels", "Module")
    db_alias = schema_editor.connection.alias
    gen, _ = Specialite.objects.using(db_alias).get_or_create(
        code="GENERAL",
        defaults={"libelle": "Général / non classé"},
    )
    Module.objects.using(db_alias).filter(specialite_id__isnull=True).update(specialite_id=gen.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("referentiels", "0004_specialite_module_specialite"),
    ]

    operations = [
        migrations.RunPython(creer_specialite_generale_et_remplir_modules, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="module",
            name="specialite",
            field=models.ForeignKey(
                help_text="Spécialité du module ; le planning ne retient que des formateurs qui ont cette spécialité.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="modules",
                to="referentiels.specialite",
            ),
        ),
    ]
