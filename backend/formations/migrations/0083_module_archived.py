from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('formations', '0082_formateur_observations'),
    ]

    operations = [
        migrations.AddField(
            model_name='module',
            name='archived',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Module archivé : visible uniquement dans l'espace Archives.",
            ),
        ),
        migrations.AddField(
            model_name='module',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='module',
            name='archived_by',
            field=models.ForeignKey(
                blank=True,
                help_text='Utilisateur ayant archivé le module',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='modules_archives',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
