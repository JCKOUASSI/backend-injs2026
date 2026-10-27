from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('formations', '0084_notificationmodificationnote'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationFinanceAjustement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('evenement', models.CharField(choices=[('PROPOSE', 'Ajustement proposé'), ('VALIDE', 'Ajustement validé'), ('REJETE', 'Ajustement rejeté')], max_length=20)),
                ('message', models.TextField()),
                ('lu', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ajustement', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications', to='formations.financeajustement')),
                ('auteur', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications_finance_ajustement_emises', to=settings.AUTH_USER_MODEL)),
                ('destinataire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications_finance_ajustement', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Notification ajustement finance',
                'verbose_name_plural': 'Notifications ajustements finance',
                'ordering': ['-created_at'],
            },
        ),
    ]
