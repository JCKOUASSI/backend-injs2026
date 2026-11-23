from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0015_add_type_to_secretariat'),
    ]

    operations = [
        migrations.AddField(
            model_name='formateur',
            name='secretariats',
            field=models.ManyToManyField(
                blank=True,
                help_text='Secrétariats auxquels appartient ce formateur',
                related_name='formateurs',
                to='formations.secretariat',
            ),
        ),
        migrations.RemoveField(
            model_name='formateur',
            name='secretariat',
        ),
    ]
