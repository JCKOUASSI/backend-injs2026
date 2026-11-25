from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrer_specialite_vers_module(apps, schema_editor):
    """Reprise : premier module du référentiel pour l'ancienne spécialité RUP."""
    ResponsableUnitePedagogique = apps.get_model("formations", "ResponsableUnitePedagogique")
    Module = apps.get_model("referentiels", "Module")
    for rup in ResponsableUnitePedagogique.objects.exclude(specialite_id__isnull=True).iterator():
        module = (
            Module.objects.filter(specialite_id=rup.specialite_id).order_by("titre", "pk").first()
        )
        if module:
            rup.module_id = module.pk
            rup.save(update_fields=["module_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("referentiels", "0001_initial"),
        ("formations", "0035_alter_responsableunitepedagogique_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="responsableunitepedagogique",
            name="module",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="responsables_up",
                to="referentiels.module",
            ),
        ),
        migrations.RunPython(migrer_specialite_vers_module, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="responsableunitepedagogique",
            name="specialite",
        ),
        migrations.AlterField(
            model_name="responsableunitepedagogique",
            name="module",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="responsables_up",
                to="referentiels.module",
            ),
        ),
        migrations.AlterModelOptions(
            name="responsableunitepedagogique",
            options={
                "ordering": ["module__titre", "user__username"],
                "verbose_name": "Responsable d'unité pédagogique",
                "verbose_name_plural": "Responsables d'unités pédagogiques",
            },
        ),
    ]
