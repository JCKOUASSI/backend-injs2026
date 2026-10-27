from django.db import migrations


def seed_parametres(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    User = apps.get_model('authentication', 'User')

    admin_user = User.objects.filter(role='ADMIN').first()

    defaults = [
        {
            'cle': 'nom_etablissement',
            'libelle': 'Nom de l\'établissement',
            'description': 'Nom officiel affiché dans les exports et l\'interface.',
            'categorie': 'general',
            'ordre': 10,
            'type': 'text',
            'valeur': 'INJS Abidjan',
            'valeur_defaut': 'INJS Abidjan',
            'modifiable': True,
            'modifiable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]',
            'lecturable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN", "DIRECTION", "FINANCE"]',
            'actif': True,
            'cree_par': admin_user,
        },
        {
            'cle': 'annee_academique_courante',
            'libelle': 'Année académique courante',
            'description': 'Année académique en cours (ex: 2025-2026).',
            'categorie': 'general',
            'ordre': 20,
            'type': 'text',
            'valeur': '2025-2026',
            'valeur_defaut': '2025-2026',
            'modifiable': True,
            'modifiable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]',
            'lecturable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN", "DIRECTION", "FINANCE"]',
            'actif': True,
            'cree_par': admin_user,
        },
        {
            'cle': 'telephone_etablissement',
            'libelle': 'Téléphone de l\'établissement',
            'description': 'Numéro de contact principal.',
            'categorie': 'general',
            'ordre': 30,
            'type': 'text',
            'valeur': '+225 01 00 00 00 00',
            'valeur_defaut': '',
            'modifiable': True,
            'modifiable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]',
            'lecturable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN", "DIRECTION", "FINANCE"]',
            'actif': True,
            'cree_par': admin_user,
        },
        {
            'cle': 'email_etablissement',
            'libelle': 'Email de l\'établissement',
            'description': 'Adresse email de contact.',
            'categorie': 'general',
            'ordre': 40,
            'type': 'email',
            'valeur': 'contact@injs.ci',
            'valeur_defaut': '',
            'modifiable': True,
            'modifiable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]',
            'lecturable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN", "DIRECTION", "FINANCE"]',
            'actif': True,
            'cree_par': admin_user,
        },
        {
            'cle': 'seuil_absence_minutes',
            'libelle': 'Seuil d\'absence (minutes)',
            'description': 'Délai en minutes avant marquage automatique ABSENT_NON_BADGE.',
            'categorie': 'presences',
            'ordre': 10,
            'type': 'integer',
            'valeur': '60',
            'valeur_defaut': '60',
            'modifiable': True,
            'modifiable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]',
            'lecturable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN", "DIRECTION", "FINANCE"]',
            'actif': True,
            'cree_par': admin_user,
        },
        {
            'cle': 'qr_token_lifetime_hours',
            'libelle': 'Durée de validité QR (heures)',
            'description': 'Durée de vie d\'un token QR en heures.',
            'categorie': 'presences',
            'ordre': 20,
            'type': 'integer',
            'valeur': '24',
            'valeur_defaut': '24',
            'modifiable': True,
            'modifiable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]',
            'lecturable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN", "DIRECTION", "FINANCE"]',
            'actif': True,
            'cree_par': admin_user,
        },
        {
            'cle': 'duree_session_heures',
            'libelle': 'Durée de session (heures)',
            'description': 'Durée de vie du token d\'accès en heures.',
            'categorie': 'securite',
            'ordre': 10,
            'type': 'integer',
            'valeur': '12',
            'valeur_defaut': '12',
            'modifiable': True,
            'modifiable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]',
            'lecturable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN", "DIRECTION"]',
            'actif': True,
            'cree_par': admin_user,
        },
        {
            'cle': 'theme_defaut',
            'libelle': 'Thème par défaut',
            'description': 'Thème interface utilisateur.',
            'categorie': 'interface',
            'ordre': 10,
            'type': 'choice',
            'valeur': 'light',
            'valeur_defaut': 'light',
            'choices_json': '{"light": "Clair", "dark": "Sombre"}',
            'modifiable': True,
            'modifiable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]',
            'lecturable_par_roles': '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN", "DIRECTION", "FINANCE"]',
            'actif': True,
            'cree_par': admin_user,
        },
    ]

    for data in defaults:
        Parametre.objects.get_or_create(cle=data['cle'], defaults=data)


def unseed_parametres(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    Parametre.objects.filter(cle__in=[
        'nom_etablissement',
        'annee_academique_courante',
        'telephone_etablissement',
        'email_etablissement',
        'seuil_absence_minutes',
        'qr_token_lifetime_hours',
        'duree_session_heures',
        'theme_defaut',
    ]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('parametres', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_parametres, reverse_code=unseed_parametres),
    ]
