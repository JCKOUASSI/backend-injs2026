from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0067_admin_verbose_names'),
        ('statistiques', '0002_notificationrapport'),
    ]

    operations = [
        migrations.AddField(
            model_name='rapport',
            name='secretariat',
            field=models.ForeignKey(
                blank=True,
                help_text='Secrétariat ciblé (null = périmètre global)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rapports',
                to='formations.secretariat',
            ),
        ),
    ]
