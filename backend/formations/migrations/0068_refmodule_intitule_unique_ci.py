from django.db import migrations, models
from django.db.models.functions import Lower


def dedupe_refmodule_intitules(apps, schema_editor):
    RefModule = apps.get_model('formations', 'RefModule')
    seen = set()
    for mod in RefModule.objects.order_by('id'):
        key = (mod.intitule or '').strip().lower()
        if not key:
            continue
        if key in seen:
            mod.delete()
        else:
            seen.add(key)


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0067_admin_verbose_names'),
    ]

    operations = [
        migrations.RunPython(dedupe_refmodule_intitules, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='refmodule',
            constraint=models.UniqueConstraint(
                Lower('intitule'),
                name='uniq_refmodule_intitule_ci',
            ),
        ),
    ]
