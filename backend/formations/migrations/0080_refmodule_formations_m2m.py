# Generated manually — RefModule.formation FK → formations M2M

from django.db import migrations, models


def migrate_formation_fk_to_m2m(apps, schema_editor):
    RefModule = apps.get_model('formations', 'RefModule')
    for module in RefModule.objects.exclude(formation_id__isnull=True):
        module.formations.add(module.formation_id)


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0079_alter_notemodule_colonne'),
    ]

    operations = [
        migrations.AddField(
            model_name='refmodule',
            name='formations',
            field=models.ManyToManyField(
                help_text='Formation(s) (cycle) auxquelles appartient ce module',
                related_name='modules',
                to='formations.refformation',
            ),
        ),
        migrations.RunPython(migrate_formation_fk_to_m2m, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='refmodule',
            name='formation',
        ),
    ]
