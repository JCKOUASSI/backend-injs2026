"""
Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur
d'import/reprise — sorties print() de console volontaires ;
exclu du garde-fou check_repo_hygiene.
Crée ou met à jour les comptes utilisateur mobile (auditeurs / formateurs).

Usage (dev uniquement) :
  SEED_MOBILE_WRITE_CREDENTIALS=1 python scripts/seed_mobile_users.py

Les identifiants générés sont écrits dans backend/.local/credentials_mobile.txt
(fichier gitignoré). Ne jamais committer ce fichier.
"""
import os
import secrets
import string
import sys

import django

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from formations.models import Participant, Formateur

User = get_user_model()

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEFAULT_CREDENTIALS_PATH = os.path.join(BACKEND_DIR, '.local', 'credentials_mobile.txt')


def _gen_password(length=8):
    """Mot de passe aléatoire cryptographique (non reproductible)."""
    alphabet = string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _link_user(participant_or_formateur, *, role, username, password, reset_passwords):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'first_name': participant_or_formateur.prenom,
            'last_name': participant_or_formateur.nom,
            'email': getattr(participant_or_formateur, 'email', '') or '',
            'role': role,
        },
    )
    password_changed = created or reset_passwords
    if password_changed:
        user.set_password(password)
        user.save(update_fields=['password'])
    if participant_or_formateur.user_id != user.id:
        participant_or_formateur.user = user
        participant_or_formateur.save(update_fields=['user'])
    return user, password_changed


def main():
    write_credentials = os.environ.get('SEED_MOBILE_WRITE_CREDENTIALS', '').lower() in ('1', 'true', 'yes')
    reset_passwords = os.environ.get('SEED_MOBILE_RESET_PASSWORDS', '').lower() in ('1', 'true', 'yes')
    creds_path = os.environ.get('MOBILE_CREDENTIALS_OUTPUT', DEFAULT_CREDENTIALS_PATH)

    credentials = []

    for participant in Participant.objects.all():
        username = participant.numero.lower()
        password = _gen_password()
        _, password_changed = _link_user(
            participant,
            role=User.Role.AUDITEUR,
            username=username,
            password=password,
            reset_passwords=reset_passwords,
        )
        credentials.append({
            'type': 'Participant',
            'nom': f'{participant.prenom} {participant.nom}',
            'username': username,
            'password': password if password_changed else '(inchangé)',
        })

    for formateur in Formateur.objects.all():
        username = formateur.numerobadge.lower()
        password = _gen_password()
        _, password_changed = _link_user(
            formateur,
            role=User.Role.FORMATEUR,
            username=username,
            password=password,
            reset_passwords=reset_passwords,
        )
        credentials.append({
            'type': 'Formateur',
            'nom': f'{formateur.prenom} {formateur.nom}',
            'username': username,
            'password': password if password_changed else '(inchangé)',
        })

    print(f'Comptes mobile traités : {len(credentials)}')

    if write_credentials:
        os.makedirs(os.path.dirname(creds_path), exist_ok=True)
        with open(creds_path, 'w', encoding='utf-8') as fh:
            fh.write('=' * 50 + '\n')
            fh.write('  IDENTIFIANTS APP MOBILE QR BADGE (CONFIDENTIEL)\n')
            fh.write('=' * 50 + '\n\n')
            for c in credentials:
                fh.write(
                    f"  {c['type']:12s} | {c['nom']:30s} | {c['username']:20s} | {c['password']}\n"
                )
            fh.write('\n' + '=' * 50 + '\n')
            fh.write('  NE PAS PARTAGER — chaque code est personnel.\n')
            fh.write('=' * 50 + '\n')
        print(f'Identifiants écrits dans : {creds_path}')
    else:
        print('Aucun fichier écrit (SEED_MOBILE_WRITE_CREDENTIALS non activé).')


if __name__ == '__main__':
    main()
