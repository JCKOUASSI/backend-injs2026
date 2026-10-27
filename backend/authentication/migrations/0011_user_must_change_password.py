from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0010_user_matricule'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='must_change_password',
            field=models.BooleanField(
                default=False,
                help_text="Si vrai, l'utilisateur doit changer son mot de passe avant d'utiliser les fonctions sensibles.",
            ),
        ),
    ]
