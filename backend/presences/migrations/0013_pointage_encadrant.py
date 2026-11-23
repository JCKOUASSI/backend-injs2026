from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0010_user_matricule'),
        ('presences', '0012_auditlog_module_assign_superviseur'),
    ]

    operations = [
        migrations.AddField(
            model_name='pointage',
            name='encadrant',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'role': 'ENCADRANT'},
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='pointages_encadrant',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
