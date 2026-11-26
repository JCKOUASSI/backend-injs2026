from django.db import migrations, models


def rattacher_specialite_generale_aux_formateurs_sans_specialite(apps, schema_editor):
    Specialite = apps.get_model("referentiels", "Specialite")
    Formateur = apps.get_model("formations", "Formateur")
    db_alias = schema_editor.connection.alias
    gen = Specialite.objects.using(db_alias).get(code="GENERAL")
    Through = Formateur._meta.get_field("specialites").remote_field.through
    for fid in Formateur.objects.using(db_alias).values_list("pk", flat=True):
        if not Through.objects.using(db_alias).filter(formateur_id=fid).exists():
            Through.objects.using(db_alias).create(formateur_id=fid, specialite_id=gen.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0019_formateur_specialites"),
        ("referentiels", "0005_module_specialite_obligatoire"),
    ]

    operations = [
        migrations.RunPython(rattacher_specialite_generale_aux_formateurs_sans_specialite, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="formateur",
            name="specialites",
            field=models.ManyToManyField(
                blank=False,
                help_text="Au moins une spécialité obligatoire ; utilisée pour le dispatch des séances.",
                related_name="formateurs",
                to="referentiels.specialite",
            ),
        ),
    ]
