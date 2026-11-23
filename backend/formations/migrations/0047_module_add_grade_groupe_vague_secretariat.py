from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0046_remove_formation_fk_from_qrtoken'),
    ]

    operations = [
        migrations.AddField(
            model_name='module',
            name='grade',
            field=models.CharField(blank=True, default='', help_text='Grade (A4, A3…)', max_length=20),
        ),
        migrations.AddField(
            model_name='module',
            name='groupe',
            field=models.CharField(blank=True, default='', help_text='Groupe (GROUPE 1, GROUPE 2…)', max_length=50),
        ),
        migrations.AddField(
            model_name='module',
            name='vague',
            field=models.CharField(blank=True, default='', help_text='Vague (PREMIERE VAGUE, DEUXIEME VAGUE…)', max_length=50),
        ),
        migrations.AddField(
            model_name='module',
            name='secretariat',
            field=models.ForeignKey(
                blank=True,
                help_text='Secrétariat responsable de ce module',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='modules_secretariat',
                to='formations.secretariat',
            ),
        ),
    ]
