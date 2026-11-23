from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('presences', '0019_auditlog_auth_secretariat_referentiel_finance'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='pointage',
            index=models.Index(fields=['date_journee', 'session'], name='pointage_date_session_idx'),
        ),
        migrations.AddIndex(
            model_name='pointage',
            index=models.Index(fields=['session', 'participant'], name='pointage_session_part_idx'),
        ),
    ]
