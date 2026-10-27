from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0072_add_note_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='participant',
            name='motif_notoire',
            field=models.CharField(
                max_length=255,
                blank=True,
                default='',
                help_text='Motif de notoriété du participant',
            ),
        ),
    ]
