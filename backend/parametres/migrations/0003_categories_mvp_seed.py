from django.db import migrations, models


def seed_mvp_params(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    User = apps.get_model('authentication', 'User')
    admin_user = User.objects.filter(role='ADMIN').first()

    extras = [
        {
            'cle': 'sigle_etablissement',
            'libelle': 'Sigle de l\'établissement',
            'description': 'Sigle affiché dans l\'en-tête et les documents.',
            'categorie': 'general',
            'ordre': 15,
            'type': 'text',
            'valeur': 'INJS',
            'valeur_defaut': 'INJS',
        },
        {
            'cle': 'credits_ects_ue',
            'libelle': 'Crédits ECTS par UE (référence)',
            'description': 'Référence LMD pour le volume de crédits d\'une UE. N\'écrase pas les maquettes existantes.',
            'categorie': 'scolarite',
            'ordre': 10,
            'type': 'integer',
            'valeur': '6',
            'valeur_defaut': '6',
        },
        {
            'cle': 'seuil_validation_ue',
            'libelle': 'Seuil de validation d\'une UE',
            'description': 'Note minimale de référence pour valider une UE (sur 20).',
            'categorie': 'scolarite',
            'ordre': 20,
            'type': 'decimal',
            'valeur': '10',
            'valeur_defaut': '10',
        },
        {
            'cle': 'edt_source_externe',
            'libelle': 'Source des emplois du temps',
            'description': 'Les EDT sont produits dans l\'application externe app-ept-injs-lmd 2026, puis importés en Excel dans Cours → Séances.',
            'categorie': 'edt',
            'ordre': 10,
            'type': 'text',
            'valeur': 'Import Excel depuis app-ept-injs-lmd 2026 vers Cours / Séances',
            'valeur_defaut': 'Import Excel depuis app-ept-injs-lmd 2026 vers Cours / Séances',
            'modifiable': False,
        },
        {
            'cle': 'notifications_alertes_actives',
            'libelle': 'Alertes système actives',
            'description': 'Active ou suspend les alertes de seuils (module Statistiques).',
            'categorie': 'notifications',
            'ordre': 10,
            'type': 'bool',
            'valeur': 'true',
            'valeur_defaut': 'true',
        },
    ]

    common = {
        'modifiable': True,
        'modifiable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]',
        'lecturable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN", "DIRECTION", "FINANCE"]',
        'actif': True,
        'cree_par': admin_user,
        'choices_json': '',
        'regex_validation': '',
    }

    for data in extras:
        payload = {**common, **data}
        Parametre.objects.get_or_create(cle=payload['cle'], defaults=payload)


def unseed_mvp_params(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    Parametre.objects.filter(cle__in=[
        'sigle_etablissement',
        'credits_ects_ue',
        'seuil_validation_ue',
        'edt_source_externe',
        'notifications_alertes_actives',
    ]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('parametres', '0002_seed_initial_params'),
    ]

    operations = [
        migrations.AlterField(
            model_name='parametre',
            name='categorie',
            field=models.CharField(
                choices=[
                    ('general', 'Général'),
                    ('scolarite', 'Scolarité / LMD'),
                    ('presences', 'Présences'),
                    ('edt', 'EDT (import)'),
                    ('notifications', 'Notifications'),
                    ('securite', 'Sécurité'),
                    ('interface', 'Interface'),
                    ('finance', 'Finance'),
                ],
                db_index=True,
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_mvp_params, reverse_code=unseed_mvp_params),
    ]
