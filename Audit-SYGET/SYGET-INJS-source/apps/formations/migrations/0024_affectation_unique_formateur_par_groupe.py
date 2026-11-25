from django.db import migrations, models


def dedoublonner_formateur_par_groupe(apps, schema_editor):
    """Garde une affectation par couple (formateur, groupe) — la plus petite pk."""
    Affectation = apps.get_model("formations", "AffectationFormateurGroupe")
    from collections import defaultdict

    par_cle: dict[tuple[int, int], list[int]] = defaultdict(list)
    for row in Affectation.objects.all().values_list("id", "formateur_id", "groupe_id"):
        pk, fid, gid = row
        par_cle[(fid, gid)].append(pk)
    for pks in par_cle.values():
        if len(pks) <= 1:
            continue
        garder = min(pks)
        Affectation.objects.filter(pk__in=[p for p in pks if p != garder]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0023_formationmodule_salle_nombre_pool_default"),
    ]

    operations = [
        migrations.RunPython(dedoublonner_formateur_par_groupe, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="affectationformateurgroupe",
            constraint=models.UniqueConstraint(
                fields=("formateur", "groupe"),
                name="uniq_formateur_par_groupe",
            ),
        ),
    ]
