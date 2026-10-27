from django.db import migrations, models


def forwards(apps, schema_editor):
    Module = apps.get_model('formations', 'Module')
    RefSite = apps.get_model('formations', 'RefSite')

    # Backfill: créer/rattacher RefSite depuis l'ancien champ texte.
    for m in Module.objects.all().only('id', 'site_legacy', 'site_id'):
        if m.site_id:
            continue
        raw = (m.site_legacy or '').strip()
        if not raw:
            continue
        site, _ = RefSite.objects.get_or_create(nom=raw, defaults={'actif': True})
        m.site_id = site.id
        m.save(update_fields=['site'])


def backwards(apps, schema_editor):
    Module = apps.get_model('formations', 'Module')

    # Re-remplir site_legacy depuis la FK si besoin.
    for m in Module.objects.select_related('site').all().only('id', 'site_legacy', 'site'):
        if (m.site_legacy or '').strip():
            continue
        if m.site_id and m.site and (m.site.nom or '').strip():
            m.site_legacy = (m.site.nom or '').strip()
            m.save(update_fields=['site_legacy'])


class Migration(migrations.Migration):
    dependencies = [
        ('formations', '0060_alter_module_batiment_alter_module_salle_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='module',
            old_name='site',
            new_name='site_legacy',
        ),
        migrations.AddField(
            model_name='module',
            name='site',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name='modules',
                to='formations.refsite',
                verbose_name='Site',
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]

