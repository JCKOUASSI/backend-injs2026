from django.db import migrations, models


def migrate_roles_forward(apps, schema_editor):
    User = apps.get_model('authentication', 'User')
    # PARTICIPANT → AUDITEUR
    User.objects.filter(role='PARTICIPANT').update(role='AUDITEUR')
    # SUPERVISEUR → ENCADRANT
    User.objects.filter(role='SUPERVISEUR').update(role='ENCADRANT')


def migrate_roles_backward(apps, schema_editor):
    User = apps.get_model('authentication', 'User')
    # AUDITEUR → PARTICIPANT
    User.objects.filter(role='AUDITEUR').update(role='PARTICIPANT')


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0006_add_admin_role'),
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
                    ('DFRC', 'DFRC'),
                    ('SECRETARIAT', 'Secrétariat'),
                    ('ENCADRANT', 'Encadrant'),
                    ('AUDITEUR', 'Auditeur'),
                ],
                default='AUDITEUR',
                max_length=20,
            ),
        ),
    ]
