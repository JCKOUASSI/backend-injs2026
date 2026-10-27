import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('statistiques', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationRapport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('evenement', models.CharField(choices=[('MODIFIE', 'Rapport modifié'), ('SUPPRIME', 'Rapport supprimé')], max_length=20)),
                ('rapport_id', models.PositiveIntegerField(blank=True, null=True)),
                ('rapport_titre', models.CharField(max_length=255)),
                ('message', models.TextField()),
                ('lu', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('auteur', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications_rapport_emises', to=settings.AUTH_USER_MODEL)),
                ('destinataire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications_rapport', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Notification rapport',
                'verbose_name_plural': 'Notifications rapports',
                'ordering': ['-created_at'],
            },
        ),
    ]
