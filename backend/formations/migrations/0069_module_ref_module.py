from django.db import migrations, models
import django.db.models.deletion


def link_existing_modules_to_ref(apps, schema_editor):
    Module = apps.get_model('formations', 'Module')
    RefModule = apps.get_model('formations', 'RefModule')
    for module in Module.objects.exclude(intitule='').iterator():
        normalized = (module.intitule or '').strip()
        if not normalized:
            continue
        ref = RefModule.objects.filter(intitule__iexact=normalized).first()
        if not ref:
            ref = RefModule.objects.create(intitule=normalized, actif=True)
        module.ref_module_id = ref.id
        module.save(update_fields=['ref_module_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0068_refmodule_intitule_unique_ci'),
    ]

    operations = [
        migrations.AddField(
            model_name='module',
            name='ref_module',
            field=models.ForeignKey(
                blank=True,
                help_text='Référentiel canonique du module (nomenclature unifiée)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='modules_instances',
                to='formations.refmodule',
            ),
        ),
        migrations.RunPython(link_existing_modules_to_ref, migrations.RunPython.noop),
    ]
