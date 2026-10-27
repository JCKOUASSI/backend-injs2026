from django.db import migrations


def sync_dual_access_staff(apps, schema_editor):
    from authentication.role_groups import sync_all_users_role_groups

    sync_all_users_role_groups()


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0013_add_formateur_role'),
    ]

    operations = [
        migrations.RunPython(sync_dual_access_staff, migrations.RunPython.noop),
    ]
