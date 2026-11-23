from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0008_rename_role_dfrc_to_cpfae_admin'),
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
                    ('ENCADRANT', 'Encadrant'),
                    ('AUDITEUR', 'Auditeur'),
                ],
                default='AUDITEUR',
                max_length=30,
            ),
        ),
    ]
