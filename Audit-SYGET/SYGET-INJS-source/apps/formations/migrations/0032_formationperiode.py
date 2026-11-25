# Generated manually for périodes de formation

from django.db import migrations, models
import django.db.models.deletion


def creer_periodes_et_rattacher_modules(apps, schema_editor):
    Formation = apps.get_model("formations", "Formation")
    FormationPeriode = apps.get_model("formations", "FormationPeriode")
    FormationModule = apps.get_model("formations", "FormationModule")

    for formation in Formation.objects.all().iterator():
        modules = list(FormationModule.objects.filter(formation_id=formation.pk))
        if not modules:
            FormationPeriode.objects.create(
                formation_id=formation.pk,
                libelle="Période 1",
                date_debut=formation.date_debut,
                date_fin=formation.date_fin,
                rythme_mensuel=formation.rythme_mensuel or "4",
                ordre=0,
            )
            continue

        groupes_dates: dict[tuple, list] = {}
        for fm in modules:
            debut = fm.date_debut or formation.date_debut
            fin = fm.date_fin or formation.date_fin
            groupes_dates.setdefault((debut, fin), []).append(fm)

        for ordre, ((debut, fin), fms) in enumerate(sorted(groupes_dates.items(), key=lambda x: x[0])):
            periode = FormationPeriode.objects.create(
                formation_id=formation.pk,
                libelle=f"Période {ordre + 1}",
                date_debut=debut,
                date_fin=fin,
                rythme_mensuel=formation.rythme_mensuel or "4",
                ordre=ordre,
            )
            for fm in fms:
                fm.periode_id = periode.pk
                fm.date_debut = debut
                fm.date_fin = fin
                fm.save(update_fields=["periode_id", "date_debut", "date_fin"])


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0031_formation_responsable"),
    ]

    operations = [
        migrations.CreateModel(
            name="FormationPeriode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("libelle", models.CharField(max_length=100)),
                ("date_debut", models.DateField()),
                ("date_fin", models.DateField()),
                (
                    "rythme_mensuel",
                    models.CharField(
                        choices=[
                            ("1", "Une semaine par mois"),
                            ("2", "Deux semaines par mois"),
                            ("3", "Trois semaines par mois"),
                            ("4", "Tout le mois"),
                        ],
                        default="4",
                        help_text="Contraint le nombre de semaines planifiables par mois pour les modules de cette période.",
                        max_length=1,
                    ),
                ),
                (
                    "ordre",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text="Ordre d'affichage des périodes sur la fiche formation.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "formation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="periodes",
                        to="formations.formation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Période de formation",
                "verbose_name_plural": "Périodes de formation",
                "ordering": ["formation", "ordre", "date_debut", "pk"],
            },
        ),
        migrations.AddField(
            model_name="formationmodule",
            name="periode",
            field=models.ForeignKey(
                help_text="Période d'enseignement à laquelle ce module appartient.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="modules",
                to="formations.formationperiode",
            ),
        ),
        migrations.RunPython(creer_periodes_et_rattacher_modules, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="formationmodule",
            name="periode",
            field=models.ForeignKey(
                help_text="Période d'enseignement à laquelle ce module appartient.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="modules",
                to="formations.formationperiode",
            ),
        ),
    ]
