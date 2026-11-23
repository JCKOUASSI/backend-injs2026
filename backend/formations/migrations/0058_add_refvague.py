from django.db import migrations, models


def seed_vagues(apps, schema_editor):
    """Initialise les vagues standards."""
    RefVague = apps.get_model('formations', 'RefVague')
    vagues = [
        ('PREMIERE VAGUE', 1),
        ('DEUXIEME VAGUE', 2),
        ('TROISIEME VAGUE', 3),
    ]
    for libelle, ordre in vagues:
        RefVague.objects.get_or_create(libelle=libelle, defaults={'ordre': ordre, 'actif': True})


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0057_move_geofence_to_refsite'),
    ]

    operations = [
        migrations.CreateModel(
            name='RefVague',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('libelle', models.CharField(max_length=100, unique=True)),
                ('ordre', models.PositiveSmallIntegerField(default=1, help_text="Ordre d'affichage")),
                ('actif', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Référentiel – Vague',
                'verbose_name_plural': 'Référentiel – Vagues',
                'ordering': ['ordre', 'libelle'],
            },
        ),
        migrations.RunPython(seed_vagues, migrations.RunPython.noop),
    ]
