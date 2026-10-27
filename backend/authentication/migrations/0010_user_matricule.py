from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0009_add_chef_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='matricule',
            field=models.CharField(
                blank=True,
                help_text='N° matricule utilisé comme numéro de badgeage',
                max_length=50,
                null=True,
                unique=True,
            ),
        ),
    ]
