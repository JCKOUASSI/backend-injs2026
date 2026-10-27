from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0074_financesettings_export_contacts'),
    ]

    operations = [
        migrations.AddField(
            model_name='financesettings',
            name='export_pied_page_titre',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Ex. DOCUMENT CONFIDENTIEL — affiché en gras en bas de la fiche formateur.',
                max_length=255,
                verbose_name='Titre pied de page (fiche récap)',
            ),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_pied_page_texte',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Coordonnées institutionnelles affichées sous le titre en bas de la fiche formateur.',
                verbose_name='Texte pied de page (fiche récap)',
            ),
        ),
    ]
