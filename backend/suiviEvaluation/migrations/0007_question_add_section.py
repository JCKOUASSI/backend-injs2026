from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('suiviEvaluation', '0006_add_categories_grades_quizmanuel'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='section',
            field=models.CharField(
                max_length=20,
                choices=[('COURS', 'Évaluation du cours'), ('FORMATEUR', 'Évaluation du formateur')],
                default='COURS',
                help_text='Section du questionnaire : cours ou formateur',
            ),
        ),
        migrations.AlterModelOptions(
            name='question',
            options={
                'ordering': ['questionnaire', 'section', 'ordre'],
                'verbose_name': 'Question',
                'verbose_name_plural': 'Questions',
            },
        ),
        migrations.AlterField(
            model_name='questionnaire',
            name='cible',
            field=models.CharField(
                max_length=20,
                choices=[('COURS', 'Évaluation du cours'), ('FORMATEUR', 'Évaluation du formateur'), ('FORMATEUR_FEEDBACK', 'Questionnaire formateur (feedback didactique/logistique)')],
                default='COURS',
                help_text="Valeur legacy — le questionnaire comporte désormais deux sections (cours + formateur).",
            ),
        ),
    ]
