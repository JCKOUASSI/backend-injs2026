from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('formations', '0062_alter_module_site_alter_module_site_legacy'),
    ]

    operations = [
        migrations.CreateModel(
            name='FinanceSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prix_heure_realisee', models.DecimalField(
                    decimal_places=2,
                    default=0,
                    help_text='Montant versé par heure de cours effectivement réalisée (badgeage).',
                    max_digits=12,
                    verbose_name='Prix pour 1 heure réalisée',
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='finance_settings_updates',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Paramètres finance',
                'verbose_name_plural': 'Paramètres finance',
            },
        ),
    ]
