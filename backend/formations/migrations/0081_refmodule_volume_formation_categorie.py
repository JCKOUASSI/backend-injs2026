# Volume horaire référentiel : formation × catégorie

import django.db.models.deletion
from django.db import migrations, models


def attach_formation_to_existing_volumes(apps, schema_editor):
    RefModule = apps.get_model('formations', 'RefModule')
    RefModuleVolumeHoraire = apps.get_model('formations', 'RefModuleVolumeHoraire')

    for vol in RefModuleVolumeHoraire.objects.filter(formation_id__isnull=True).select_related('module'):
        formations = list(vol.module.formations.all())
        if not formations:
            continue
        vol.formation_id = formations[0].id
        vol.save(update_fields=['formation_id'])
        for extra in formations[1:]:
            RefModuleVolumeHoraire.objects.get_or_create(
                module_id=vol.module_id,
                formation_id=extra.id,
                categorie_id=vol.categorie_id,
                defaults={'volume_horaire': vol.volume_horaire},
            )

    RefFormation = apps.get_model('formations', 'RefFormation')
    fallback = RefFormation.objects.order_by('id').first()
    for vol in RefModuleVolumeHoraire.objects.filter(formation_id__isnull=True):
        if fallback:
            vol.formation_id = fallback.id
            vol.save(update_fields=['formation_id'])
        else:
            vol.delete()

    # Volume global du module → grille formation × catégories actives si aucune entrée
    RefCategorie = apps.get_model('formations', 'RefCategorie')
    categories = list(RefCategorie.objects.filter(actif=True))
    for mod in RefModule.objects.filter(volume_horaire__isnull=False).exclude(volume_horaire=0):
        if mod.volumes_horaires.exists():
            continue
        formations = list(mod.formations.all())
        if not formations or not categories:
            continue
        for formation in formations:
            for cat in categories:
                RefModuleVolumeHoraire.objects.get_or_create(
                    module_id=mod.id,
                    formation_id=formation.id,
                    categorie_id=cat.id,
                    defaults={'volume_horaire': mod.volume_horaire},
                )


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('formations', '0080_refmodule_formations_m2m'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='refmodulevolumehoraire',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='refmodulevolumehoraire',
            name='formation',
            field=models.ForeignKey(
                blank=True,
                help_text='Formation (cycle) concernée',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='volumes_horaires_modules',
                to='formations.refformation',
            ),
        ),
        migrations.RunPython(attach_formation_to_existing_volumes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='refmodulevolumehoraire',
            name='formation',
            field=models.ForeignKey(
                help_text='Formation (cycle) concernée',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='volumes_horaires_modules',
                to='formations.refformation',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='refmodulevolumehoraire',
            unique_together={('module', 'formation', 'categorie')},
        ),
        migrations.AlterModelOptions(
            name='refmodulevolumehoraire',
            options={
                'ordering': ['module', 'formation__intitule', 'categorie__libelle'],
                'verbose_name': 'Référentiel – Volume horaire (formation × catégorie)',
                'verbose_name_plural': 'Référentiel – Volumes horaires (formation × catégorie)',
            },
        ),
    ]
