from django.db import migrations, models


def migrate_roles_forward(apps, schema_editor):
    User = apps.get_model('authentication', 'User')
    User.objects.filter(role='DFRC').update(role='CPFAE_ADMIN')


def migrate_roles_backward(apps, schema_editor):
    User = apps.get_model('authentication', 'User')
    User.objects.filter(role='CPFAE_ADMIN').update(role='DFRC')


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0007_rename_roles_auditeur'),
    ]

    operations = [
        migrations.RunPython(migrate_roles_forward, migrate_roles_backward),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('ADMIN', 'Administrateur'),
                    ('DIRECTION', 'Direction'),
                    ('CPFAE_ADMIN', 'CPFAE Admin'),
                    ('SECRETARIAT', 'Secrétariat'),
                    ('ENCADRANT', 'Encadrant'),
                    ('AUDITEUR', 'Auditeur'),
                ],
                default='AUDITEUR',
                max_length=20,
            ),
        ),
    ]
