from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0053_ref_categorie_grade_no_code'),
    ]

    operations = [
        migrations.RenameField(
            model_name='formateur',
            old_name='numero',
            new_name='numerobadge',
        ),
    ]
