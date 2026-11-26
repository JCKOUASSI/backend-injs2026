from django.db import migrations, models
import django.db.models.deletion


def migrer_formateurs_vers_referentiel_global(apps, schema_editor):
    FormateurFormation = apps.get_model("formations", "FormateurFormation")
    Formateur = apps.get_model("formations", "Formateur")
    AffectationFormateurGroupe = apps.get_model("formations", "AffectationFormateurGroupe")

    numero_to_pk: dict[str, int] = {}
    for ff in FormateurFormation.objects.all().order_by("id"):
        f, _ = Formateur.objects.get_or_create(
            numero=ff.numero,
            defaults={
                "nom": ff.nom,
                "prenom": ff.prenom,
                "email": ff.email or "",
                "telephone": ff.telephone or "",
                "organisation": ff.organisation or "",
            },
        )
        numero_to_pk[ff.numero] = f.pk

    for aff in AffectationFormateurGroupe.objects.all():
        ff = FormateurFormation.objects.filter(pk=aff.formateur_id).first()
        if ff is None:
            aff.delete()
            continue
        pk = numero_to_pk.get(ff.numero)
        if pk is None:
            aff.delete()
            continue
        aff.formateur_ref_id = pk
        aff.save(update_fields=["formateur_ref_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0017_one_formateur_par_groupe_module"),
    ]

    operations = [
        migrations.CreateModel(
            name="Formateur",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.CharField(max_length=30)),
                ("nom", models.CharField(max_length=150)),
                ("prenom", models.CharField(max_length=150)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("telephone", models.CharField(blank=True, default="", max_length=30)),
                ("organisation", models.CharField(blank=True, default="", max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Formateur",
                "verbose_name_plural": "Formateurs",
                "ordering": ["nom", "prenom"],
            },
        ),
        migrations.AddConstraint(
            model_name="formateur",
            constraint=models.UniqueConstraint(fields=("numero",), name="uniq_formateur_numero_global"),
        ),
        migrations.AddField(
            model_name="affectationformateurgroupe",
            name="formateur_ref",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="formations.formateur",
            ),
        ),
        migrations.RunPython(migrer_formateurs_vers_referentiel_global, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="affectationformateurgroupe",
            name="formateur",
        ),
        migrations.RenameField(
            model_name="affectationformateurgroupe",
            old_name="formateur_ref",
            new_name="formateur",
        ),
        migrations.AlterField(
            model_name="affectationformateurgroupe",
            name="formateur",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="affectations_groupes",
                to="formations.formateur",
            ),
        ),
        migrations.DeleteModel(
            name="FormateurFormation",
        ),
    ]
