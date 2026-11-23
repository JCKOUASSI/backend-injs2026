from django.db import migrations, models


def copy_geofence_module_to_site(apps, schema_editor):
    """Copie les coords geofence depuis Module vers RefSite (match par nom, iexact)."""
    Module = apps.get_model('formations', 'Module')
    RefSite = apps.get_model('formations', 'RefSite')

    for mod in Module.objects.exclude(geofence_latitude__isnull=True).exclude(
        geofence_longitude__isnull=True
    ):
        site_name = (mod.site or '').strip()
        if not site_name:
            continue
        site = RefSite.objects.filter(nom__iexact=site_name).first()
        if site is None:
            site = RefSite.objects.create(nom=site_name, actif=True)
        # N'écrase pas un RefSite déjà configuré.
        if site.geofence_latitude is None or site.geofence_longitude is None:
            site.geofence_latitude = mod.geofence_latitude
            site.geofence_longitude = mod.geofence_longitude
            site.geofence_rayon_m = mod.geofence_rayon_m or 200
            site.save(update_fields=[
                'geofence_latitude', 'geofence_longitude', 'geofence_rayon_m',
            ])


def noop_reverse(apps, schema_editor):
    # Pas de restauration : les champs du Module sont supprimés juste après.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0056_module_geofence_fields'),
    ]

    operations = [
        # 1. Ajouter les champs geofence à RefSite.
        migrations.AddField(
            model_name='refsite',
            name='geofence_latitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text='Latitude du centre de formation (contrôle de présence mobile)',
                max_digits=9,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='refsite',
            name='geofence_longitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text='Longitude du centre de formation',
                max_digits=9,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='refsite',
            name='geofence_rayon_m',
            field=models.PositiveIntegerField(
                default=200,
                help_text='Rayon autorisé en mètres pour le badgeage mobile',
            ),
        ),

        # 2. Copier les valeurs du Module vers le RefSite correspondant.
        migrations.RunPython(copy_geofence_module_to_site, noop_reverse),

        # 3. Supprimer les champs geofence du Module (désormais portés par RefSite).
        migrations.RemoveField(model_name='module', name='geofence_latitude'),
        migrations.RemoveField(model_name='module', name='geofence_longitude'),
        migrations.RemoveField(model_name='module', name='geofence_rayon_m'),

        # 4. Mettre à jour le help_text du champ site pour refléter le nouveau rôle.
        migrations.AlterField(
            model_name='module',
            name='site',
            field=models.CharField(
                blank=True,
                default='',
                help_text=(
                    'Centre de formation (doit correspondre à un RefSite pour que '
                    'le contrôle de présence mobile soit actif)'
                ),
                max_length=255,
            ),
        ),
    ]
