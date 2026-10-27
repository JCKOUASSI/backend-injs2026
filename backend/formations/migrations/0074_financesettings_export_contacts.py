from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0073_participant_motif_notoire'),
    ]

    operations = [
        migrations.AddField(
            model_name='financesettings',
            name='export_contacts',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Une ligne par contact ou phrase affichée sous la note NB des exports fiche formateur.',
                verbose_name='Contacts (fiche récap formateur)',
            ),
        ),
    ]
