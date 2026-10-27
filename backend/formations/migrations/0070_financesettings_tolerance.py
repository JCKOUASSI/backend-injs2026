from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0069_module_ref_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='financesettings',
            name='tolerance_active',
            field=models.BooleanField(
                default=False,
                help_text='Active la marge de tolérance sur les volumes réalisés inférieurs au planifié.',
                verbose_name='Activer la tolérance horaire',
            ),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='tolerance_minutes',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Marge absolue acceptée (minutes) entre planifié et réalisé.',
                verbose_name='Tolérance (minutes)',
            ),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='tolerance_pct',
            field=models.DecimalField(
                decimal_places=2,
                default=5,
                help_text='Marge relative (% du volume planifié). Le seuil retenu est le plus favorable des deux.',
                max_digits=5,
                verbose_name='Tolérance (%)',
            ),
        ),
    ]
