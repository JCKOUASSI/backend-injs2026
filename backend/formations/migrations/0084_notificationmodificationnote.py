from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('formations', '0083_module_archived'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationModificationNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('colonne_libelle', models.CharField(blank=True, default='', max_length=120)),
                ('ancienne_note', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('nouvelle_note', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('message', models.TextField()),
                ('lu', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('auteur', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications_modification_note_emises', to=settings.AUTH_USER_MODEL)),
                ('destinataire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications_modification_note', to=settings.AUTH_USER_MODEL)),
                ('module', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications_modification_note', to='formations.module')),
                ('participant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications_modification_note', to='formations.participant')),
            ],
            options={
                'verbose_name': 'Notification modification de note',
                'verbose_name_plural': 'Notifications modifications de notes',
                'ordering': ['-created_at'],
            },
        ),
    ]
