from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0055_module_duree_prevue_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='module',
            name='geofence_latitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text='Latitude du point de référence pour le contrôle de présence mobile',
                max_digits=9,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='module',
            name='geofence_longitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text='Longitude du point de référence pour le contrôle de présence mobile',
                max_digits=9,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='module',
            name='geofence_rayon_m',
            field=models.PositiveIntegerField(
                default=200,
                help_text='Rayon autorisé en mètres pour le badgeage mobile',
            ),
        ),
    ]
