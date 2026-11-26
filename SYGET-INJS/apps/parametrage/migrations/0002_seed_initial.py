from django.db import migrations


def seed_initial_data(apps, schema_editor):
    Grade = apps.get_model("parametrage", "Grade")
    Vague = apps.get_model("parametrage", "Vague")
    ParametreGeneral = apps.get_model("parametrage", "ParametreGeneral")

    for ordre, libelle in enumerate(["A3", "A4", "B3", "B4", "C3"], start=1):
        Grade.objects.get_or_create(libelle=libelle, defaults={"ordre": ordre, "actif": True})

    for libelle in ["Vague 1", "Vague 2", "2024-A", "2025-A"]:
        Vague.objects.get_or_create(libelle=libelle, defaults={"actif": True})

    ParametreGeneral.objects.get_or_create(
        pk=1,
        defaults={
            "max_auditeurs_groupe_defaut": 25,
            "matin_heure_debut_defaut": "08:00",
            "matin_heure_fin_defaut": "12:00",
            "soir_heure_debut_defaut": "13:00",
            "soir_heure_fin_defaut": "17:00",
            "jours_defaut": [0, 1, 2, 3, 4],
        },
    )


class Migration(migrations.Migration):
    dependencies = [("parametrage", "0001_initial")]

    operations = [migrations.RunPython(seed_initial_data, migrations.RunPython.noop)]
