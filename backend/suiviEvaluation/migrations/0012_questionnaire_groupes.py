from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('suiviEvaluation', '0011_academic_evaluation_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='questionnaire',
            name='groupes',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Liste des groupes ciblés (GROUPE 1, GROUPE 2…). Vide = tous.',
            ),
        ),
    ]
