from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('presences', '0014_alter_auditlog_cible_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='pointage',
            name='last_accuracy_m',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pointage',
            name='last_battery_level',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pointage',
            name='last_heartbeat_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pointage',
            name='last_is_charging',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pointage',
            name='last_latitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pointage',
            name='last_longitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pointage',
            name='outside_geofence_count',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
