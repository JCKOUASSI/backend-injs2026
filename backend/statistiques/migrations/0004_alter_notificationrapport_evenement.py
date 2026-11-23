from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('statistiques', '0003_rapport_secretariat'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notificationrapport',
            name='evenement',
            field=models.CharField(
                choices=[
                    ('MODIFIE', 'Rapport modifié'),
                    ('SUPPRIME', 'Rapport supprimé'),
                    ('SOUMIS', 'Rapport soumis à validation'),
                    ('VALIDE', 'Rapport validé'),
                    ('PUBLIE', 'Rapport publié'),
                    ('REJETE', 'Rapport rejeté'),
                ],
                max_length=20,
            ),
        ),
    ]
