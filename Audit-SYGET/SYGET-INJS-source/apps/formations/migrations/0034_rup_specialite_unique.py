from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrer_module_vers_specialite(apps, schema_editor):
    ResponsableUnitePedagogique = apps.get_model("formations", "ResponsableUnitePedagogique")
    Module = apps.get_model("referentiels", "Module")
    for rup in ResponsableUnitePedagogique.objects.exclude(module_id__isnull=True).iterator():
        module = Module.objects.filter(pk=rup.module_id).first()
        if module and module.specialite_id:
            rup.specialite_id = module.specialite_id
            rup.save(update_fields=["specialite_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("referentiels", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("formations", "0033_responsableunitepedagogique"),
    ]

    operations = [
        migrations.AddField(
            model_name="responsableunitepedagogique",
            name="specialite",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="responsables_up",
                to="referentiels.specialite",
            ),
        ),
        migrations.RunPython(migrer_module_vers_specialite, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="responsableunitepedagogique",
            name="uniq_rup_user_module",
        ),
        migrations.RemoveField(
            model_name="responsableunitepedagogique",
            name="module",
        ),
        migrations.AlterField(
            model_name="responsableunitepedagogique",
            name="specialite",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="responsables_up",
                to="referentiels.specialite",
            ),
        ),
        migrations.AlterField(
            model_name="responsableunitepedagogique",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="responsabilite_up",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
