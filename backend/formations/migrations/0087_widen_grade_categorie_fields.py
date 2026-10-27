from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0086_refsalle_type_lieu_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='module',
            name='grade',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Grade (profil INJS ou A4, A3…)',
                max_length=100,
            ),
        ),
        migrations.AlterField(
            model_name='participant',
            name='categorie',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='participant',
            name='grade',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='participant',
            name='grade_groupe',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
    ]
