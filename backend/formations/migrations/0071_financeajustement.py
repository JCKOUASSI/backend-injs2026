import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('formations', '0070_financesettings_tolerance'),
    ]

    operations = [
        migrations.CreateModel(
            name='FinanceAjustement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('minutes_delta', models.IntegerField(help_text='Minutes à ajouter (positif) ou retirer (négatif) du volume réalisé.')),
                ('motif', models.TextField()),
                ('statut', models.CharField(choices=[('EN_ATTENTE', 'En attente'), ('VALIDE', 'Validé'), ('REJETE', 'Rejeté')], db_index=True, default='EN_ATTENTE', max_length=20)),
                ('realise_avant_minutes', models.FloatField(blank=True, help_text='Volume réalisé de la séance avant ajustement (snapshot).', null=True)),
                ('realise_apres_minutes', models.FloatField(blank=True, help_text='Volume réalisé attendu après validation.', null=True)),
                ('proposed_at', models.DateTimeField(auto_now_add=True)),
                ('validated_at', models.DateTimeField(blank=True, null=True)),
                ('rejected_at', models.DateTimeField(blank=True, null=True)),
                ('rejection_motif', models.TextField(blank=True, default='')),
                ('formateur', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='finance_ajustements', to='formations.formateur')),
                ('proposed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_ajustements_proposes', to=settings.AUTH_USER_MODEL)),
                ('rejected_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_ajustements_rejetes', to=settings.AUTH_USER_MODEL)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='finance_ajustements', to='formations.sessionmodule')),
                ('validated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_ajustements_valides', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Ajustement horaire finance',
                'verbose_name_plural': 'Ajustements horaires finance',
                'ordering': ['-proposed_at'],
            },
        ),
        migrations.AddIndex(
            model_name='financeajustement',
            index=models.Index(fields=['statut', 'proposed_at'], name='formations__statut_8e2f0a_idx'),
        ),
        migrations.AddIndex(
            model_name='financeajustement',
            index=models.Index(fields=['session', 'statut'], name='formations__session_4c1b2d_idx'),
        ),
    ]
