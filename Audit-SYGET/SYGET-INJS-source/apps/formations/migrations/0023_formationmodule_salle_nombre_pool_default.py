from django.db import migrations, models
import django.core.validators


def forwards_salle_nombre_pool_complet(apps, schema_editor):
    FormationModule = apps.get_model("formations", "FormationModule")
    for fm in FormationModule.objects.only("pk", "salle_nom", "salle_nombre").iterator():
        sn = (fm.salle_nom or "").strip()
        if not sn and fm.salle_nombre == 1:
            FormationModule.objects.filter(pk=fm.pk).update(salle_nombre=0)


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0022_formation_planning_union_sites_programme"),
    ]

    operations = [
        migrations.RunPython(forwards_salle_nombre_pool_complet, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="formationmodule",
            name="salle_nombre",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Nombre max. de salles prises dans le pool pour le dispatch si les salles ne sont pas listées explicitement : 0 = toutes les salles actives du/des site(s), N > 0 = les N premières du référentiel (ordre alphabétique). Ignoré lorsque des salles sont nommées dans `salle_nom`.",
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
