from django.db import migrations


def remove_auditeur_staff(apps, schema_editor):
    from authentication.role_groups import sync_all_users_role_groups

    sync_all_users_role_groups()


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0014_sync_dual_access_staff'),
    ]

    operations = [
        migrations.RunPython(remove_auditeur_staff, migrations.RunPython.noop),
    ]
