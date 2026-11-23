"""Création strictement contrôlée des comptes de démonstration INJS-LMD."""
import os
from pathlib import Path

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def valider_cible_demo(databases, base_dir, environ=None):
    """Refuse toute cible autre que la SQLite sandbox explicitement autorisée."""
    env = os.environ if environ is None else environ
    if env.get('DEMO_ACCOUNTS_ALLOW') != '1':
        raise RuntimeError('Création démo refusée : DEMO_ACCOUNTS_ALLOW=1 est requis.')
    if env.get('USE_SQLITE', '').lower() not in ('1', 'true', 'yes'):
        raise RuntimeError('Création démo refusée : USE_SQLITE doit être activé.')
    if set(databases) != {'default'}:
        raise RuntimeError('Création démo refusée : alias de base ambigu.')
    cible = databases['default']
    if cible.get('ENGINE') != 'django.db.backends.sqlite3':
        raise RuntimeError('Création démo refusée : PostgreSQL ou moteur non autorisé.')
    attendue = (Path(base_dir) / 'db_sandbox.sqlite3').resolve()
    reelle = Path(cible.get('NAME', '')).expanduser().resolve()
    if reelle != attendue:
        raise RuntimeError('Création démo refusée : chemin SQLite non autorisé.')
    return reelle


def main():
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model

    valider_cible_demo(settings.DATABASES, settings.BASE_DIR)
    User = get_user_model()
    demo_accounts = [
        ('admin', 'ADMIN', True, 'Admin', 'INJS', 'admin@injs.ci'),
        ('Enseignant', 'FORMATEUR', False, 'Enseignant', 'INJS', 'enseignant@injs.ci'),
        ('Etudiant', 'AUDITEUR', False, 'Etudiant', 'INJS', 'etudiant@injs.ci'),
        ('DirestG', 'DIRECTION', True, 'Direction', 'Generale', 'direction@injs.ci'),
        ('DirectFC', 'FINANCE', True, 'Direction', 'Financiere', 'directfc@injs.ci'),
        ('Sect', 'SECRETARIAT', True, 'Secretariat', 'INJS', 'secretariat@injs.ci'),
    ]
    prefixes = {username: f'DEMO_PASSWORD_{username.upper()}' for username, *_ in demo_accounts}
    passwords = {username: os.environ.get(prefixes[username], '') for username, *_ in demo_accounts}
    if any(not password for password in passwords.values()):
        raise RuntimeError('Création démo refusée : un mot de passe local requis est absent.')

    resultats = []
    for username, role_name, is_staff, first_name, last_name, email in demo_accounts:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'role': getattr(User.Role, role_name),
                'is_staff': is_staff,
                'is_superuser': False,
                'is_active': True,
            },
        )
        if created:
            user.set_password(passwords[username])
            user.save()
            resultats.append((username, 'CREE', user.role, user.is_staff))
        else:
            resultats.append((username, 'EXISTANT (inchangé)', user.role, user.is_staff))

    for username, statut, role, is_staff in resultats:
        print(f'  {username:12s} | {statut:20s} | role={role} | is_staff={is_staff}')


if __name__ == '__main__':
    main()