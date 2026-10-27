from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0071_financeajustement'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NoteModule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note', models.DecimalField(blank=True, decimal_places=2, help_text='Note numérique (ex : 14.50)', max_digits=5, null=True)),
                ('mention', models.CharField(blank=True, choices=[('TRES_BIEN', 'Très bien'), ('BIEN', 'Bien'), ('ASSEZ_BIEN', 'Assez bien'), ('PASSABLE', 'Passable'), ('INSUFFISANT', 'Insuffisant')], default='', help_text='Mention calculée ou saisie manuellement', max_length=20)),
                ('observations', models.TextField(blank=True, default='', help_text='Observations éventuelles du secrétariat')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notes', to='formations.module')),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notes_modules', to='formations.participant')),
                ('saisie_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notes_saisies', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Note module',
                'verbose_name_plural': 'Notes modules',
                'ordering': ['module', 'participant__nom', 'participant__prenom'],
                'unique_together': {('module', 'participant')},
            },
        ),
    ]
