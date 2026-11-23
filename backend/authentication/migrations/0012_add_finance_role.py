from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0011_user_must_change_password'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('ADMIN', 'Administrateur'),
                    ('DIRECTION', 'Direction'),
                    ('CHEF_CPFAE_ADMIN', 'Chef CPFAE Admin'),
                    ('CPFAE_ADMIN', 'CPFAE Admin'),
                    ('CHEF_SECRETARIAT', 'Chef Secrétariat'),
                    ('SECRETARIAT', 'Secrétariat'),
                    ('FINANCE', 'Finance'),
                    ('ENCADRANT', 'Encadrant'),
                    ('AUDITEUR', 'Auditeur'),
                ],
                default='AUDITEUR',
                max_length=30,
            ),
        ),
    ]
