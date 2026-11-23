import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0079_alter_notemodule_colonne'),
        ('suiviEvaluation', '0010_remove_ficheauditeuracademique_decision_finale_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ParametresEvaluation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seuil_admission', models.DecimalField(decimal_places=2, default=12, help_text='Moyenne générale minimale (/20) pour être admis', max_digits=4)),
                ('taux_presence_min', models.DecimalField(decimal_places=2, default=80, help_text='Pourcentage minimal du temps de cours effectué', max_digits=5)),
                ('seuil_mention_bien', models.DecimalField(decimal_places=2, default=14, max_digits=4)),
                ('seuil_mention_tres_bien', models.DecimalField(decimal_places=2, default=16, max_digits=4)),
                ('actif', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('formation', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='parametres_evaluation', to='formations.formation')),
            ],
            options={
                'verbose_name': "Paramètres d'évaluation",
                'verbose_name_plural': "Paramètres d'évaluation",
            },
        ),
        migrations.CreateModel(
            name='MoyenneModule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('moyenne', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('nb_notes', models.PositiveSmallIntegerField(default=0)),
                ('heures_presence', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('heures_prevues', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('taux_presence', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('calculee_le', models.DateTimeField(auto_now=True)),
                ('module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moyennes_auditeurs', to='formations.module')),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moyennes_modules', to='formations.participant')),
            ],
            options={
                'verbose_name': 'Moyenne module',
                'verbose_name_plural': 'Moyennes modules',
                'ordering': ['module', 'participant__nom', 'participant__prenom'],
                'unique_together': {('module', 'participant')},
            },
        ),
        migrations.CreateModel(
            name='DecisionPedagogique',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('moyenne_generale', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('taux_presence', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('total_heures_presence', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('total_heures_prevues', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('decision', models.CharField(choices=[('ADMIS', 'Admis'), ('AJOURNE', 'Ajourné'), ('EXCLUSION', 'Exclusion'), ('EN_ATTENTE', 'En attente')], default='EN_ATTENTE', max_length=20)),
                ('mention', models.CharField(blank=True, choices=[('TRES_BIEN', 'Très bien'), ('BIEN', 'Bien'), ('ASSEZ_BIEN', 'Assez bien'), ('PASSABLE', 'Passable')], default='', max_length=20)),
                ('appreciation', models.TextField(blank=True, default='')),
                ('generee_auto', models.BooleanField(default=True)),
                ('validee_le', models.DateTimeField(blank=True, null=True)),
                ('criteres_appliques', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('formation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='decisions', to='formations.formation')),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='decisions', to='formations.participant')),
                ('validee_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='decisions_validees', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Décision pédagogique',
                'verbose_name_plural': 'Décisions pédagogiques',
                'ordering': ['-updated_at'],
                'unique_together': {('formation', 'participant')},
            },
        ),
    ]
