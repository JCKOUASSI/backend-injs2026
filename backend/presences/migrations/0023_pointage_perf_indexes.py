from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('presences', '0022_alter_auditlog_action_rattrapage'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='pointage',
            index=models.Index(fields=['session', 'formateur'], name='pointage_session_form_idx'),
        ),
        migrations.AddIndex(
            model_name='pointage',
            index=models.Index(fields=['session', 'encadrant'], name='pointage_session_enc_idx'),
        ),
        migrations.AddIndex(
            model_name='pointage',
            index=models.Index(fields=['participant', 'date_journee'], name='pointage_part_date_idx'),
        ),
        migrations.AddIndex(
            model_name='pointage',
            index=models.Index(fields=['statut', 'timestamp_sortie'], name='pointage_statut_sortie_idx'),
        ),
    ]
