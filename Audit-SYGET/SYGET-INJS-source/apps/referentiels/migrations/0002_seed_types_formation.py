from django.db import migrations


def seed_types_formation(apps, schema_editor):
    TypeFormation = apps.get_model("referentiels", "TypeFormation")
    TypeFormation.objects.get_or_create(code="FAC", defaults={"libelle": "Formation d'Adaptation à la Carrière"})
    TypeFormation.objects.get_or_create(code="FAB", defaults={"libelle": "Formation d'Adaptation au Budget"})


class Migration(migrations.Migration):
    dependencies = [("referentiels", "0001_initial")]

    operations = [migrations.RunPython(seed_types_formation, migrations.RunPython.noop)]
