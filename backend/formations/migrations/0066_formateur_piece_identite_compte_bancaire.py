from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0065_financesettings_export_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='formateur',
            name='numero_compte_bancaire',
            field=models.CharField(
                blank=True,
                default='',
                max_length=100,
                verbose_name='N° de compte bancaire',
            ),
        ),
        migrations.AddField(
            model_name='formateur',
            name='numero_piece_identite',
            field=models.CharField(
                blank=True,
                default='',
                max_length=100,
                verbose_name="N° pièce d'identité",
            ),
        ),
    ]
