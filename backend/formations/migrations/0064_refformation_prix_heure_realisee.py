from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0063_financesettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='refformation',
            name='prix_heure_realisee',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Tarif horaire spécifique. Si non renseigné, le tarif par défaut des paramètres finance s'applique.",
                max_digits=12,
                null=True,
                verbose_name='Prix pour 1 heure réalisée',
            ),
        ),
    ]
