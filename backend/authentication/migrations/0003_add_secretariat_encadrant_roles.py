# Generated migration for adding SECRETARIAT and ENCADRANT roles and grade field
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_alter_user_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='grade',
            field=models.CharField(blank=True, default='', help_text='Grade (A4, A3…)', max_length=20),
        ),
    ]
