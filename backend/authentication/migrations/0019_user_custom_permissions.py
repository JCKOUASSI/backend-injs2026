from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0018_add_archive_role'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='user',
            options={
                'permissions': [
                    ('access_web', 'Accès à la plateforme web'),
                    ('operational_web', 'Personnel opérationnel web (hors module Finance)'),
                    ('mutate_users', 'Créer ou modifier des comptes utilisateurs'),
                    ('global_scope', 'Périmètre global (tous secrétariats)'),
                    ('list_participants', 'Consulter la liste des participants'),
                    ('finance_module', 'Accès au module Finance'),
                    ('manage_questionnaires', 'Gérer les questionnaires d\'évaluation'),
                    ('manage_notes', 'Gérer les notes et épreuves'),
                    ('validate_decisions', 'Valider les décisions pédagogiques'),
                    ('consult_evaluation', 'Consulter les évaluations'),
                ],
                'verbose_name': 'Utilisateur',
                'verbose_name_plural': 'Utilisateurs',
            },
        ),
    ]
