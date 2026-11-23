from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_notes_to_colonnes(apps, schema_editor):
    OldNote = apps.get_model('formations', 'NoteModule')
    Colonne = apps.get_model('formations', 'NoteModuleColonne')
    Synthese = apps.get_model('formations', 'NoteModuleSynthese')

    colonnes_par_module = {}
    for old in OldNote.objects.select_related('module', 'participant').order_by('id'):
        module_id = old.module_id
        if module_id not in colonnes_par_module:
            colonnes_par_module[module_id] = Colonne.objects.create(
                module_id=module_id,
                libelle='Note /20',
                ordre=0,
                note_max=20,
            )
        colonne = colonnes_par_module[module_id]

        if old.note is not None:
            OldNote.objects.filter(pk=old.pk).update(
                colonne_id=colonne.id,
                mention='',
                observations='',
            )

        if old.mention or old.observations:
            Synthese.objects.update_or_create(
                module_id=module_id,
                participant_id=old.participant_id,
                defaults={
                    'mention': old.mention or '',
                    'observations': old.observations or '',
                    'saisie_par_id': old.saisie_par_id,
                },
            )

    OldNote.objects.filter(colonne__isnull=True).delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0077_add_refmodule_volume_horaire_categorie'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NoteModuleColonne',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('libelle', models.CharField(help_text='Intitulé affiché en en-tête de colonne', max_length=120)),
                ('ordre', models.PositiveSmallIntegerField(default=0)),
                ('note_max', models.DecimalField(decimal_places=2, default=20, help_text='Note maximale (ex : 20)', max_digits=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='colonnes_notes', to='formations.module')),
            ],
            options={
                'verbose_name': 'Colonne de note module',
                'verbose_name_plural': 'Colonnes de notes module',
                'ordering': ['module', 'ordre', 'id'],
            },
        ),
        migrations.CreateModel(
            name='NoteModuleSynthese',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mention', models.CharField(blank=True, choices=[('TRES_BIEN', 'Très bien'), ('BIEN', 'Bien'), ('ASSEZ_BIEN', 'Assez bien'), ('PASSABLE', 'Passable'), ('INSUFFISANT', 'Insuffisant')], default='', help_text='Mention calculée ou saisie manuellement', max_length=20)),
                ('observations', models.TextField(blank=True, default='', help_text='Observations éventuelles du secrétariat')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='syntheses_notes', to='formations.module')),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='syntheses_notes_modules', to='formations.participant')),
                ('saisie_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='syntheses_notes_saisies', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Synthèse notes module',
                'verbose_name_plural': 'Synthèses notes module',
                'ordering': ['module', 'participant__nom', 'participant__prenom'],
                'unique_together': {('module', 'participant')},
            },
        ),
        migrations.AddField(
            model_name='notemodule',
            name='colonne',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='valeurs', to='formations.notemodulecolonne'),
        ),
        migrations.RunPython(migrate_notes_to_colonnes, noop),
        migrations.AlterUniqueTogether(
            name='notemodule',
            unique_together={('colonne', 'participant')},
        ),
        migrations.RemoveField(
            model_name='notemodule',
            name='mention',
        ),
        migrations.RemoveField(
            model_name='notemodule',
            name='observations',
        ),
        migrations.RemoveField(
            model_name='notemodule',
            name='module',
        ),
        migrations.AlterModelOptions(
            name='notemodule',
            options={'ordering': ['colonne', 'participant__nom', 'participant__prenom'], 'verbose_name': 'Note module', 'verbose_name_plural': 'Notes modules'},
        ),
    ]
