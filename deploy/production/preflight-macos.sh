#!/bin/sh
# Préflight de lecture seule depuis un Mac vers le VPS INJS.
# Usage : sh deploy/production/preflight-macos.sh
# Prérequis : vérifier l'empreinte SSH du VPS par un canal indépendant,
# puis inscrire sa clé publique hôte dans ~/.ssh/known_hosts sur le Mac.
# Ne jamais envoyer le mot de passe, la clé privée ni les fichiers .env.
set -eu
HOST=152.228.233.123
USER=almalinux

# StrictHostKeyChecking=yes refuse tout serveur non préalablement identifié.
# SSH peut demander le mot de passe dans le terminal LOCAL du Mac ; il n'est
# ni lu par ce script, ni stocké dans le dépôt, ni transmis en argument.
ssh -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$HOME/.ssh/known_hosts" \
    "$USER@$HOST" 'sh -s' <<'REMOTE'
set -eu
printf '\n=== Hôte et date UTC ===\n'
hostname
date -u '+%Y-%m-%dT%H:%M:%SZ'
printf '\n=== Docker (noms, images, ports ; pas de variables d’environnement) ===\n'
docker ps --format '{{.Names}} | {{.Image}} | {{.Ports}}'
printf '\n=== Volumes et réseaux (noms uniquement) ===\n'
docker volume ls --format '{{.Name}}'
docker network ls --format '{{.Name}}'
printf '\n=== Disques ===\n'
df -h /opt/injs
printf '\n=== Installation candidate ===\n'
if [ -d /opt/injs/injs-lmd/deploy/production ]; then
  echo 'Dossier candidat présent'
else
  echo 'Dossier candidat absent'
fi
printf '\n=== Sauvegardes : noms, tailles, dates (pas de contenu) ===\n'
if [ -d /opt/injs/backups ]; then
  find /opt/injs/backups -maxdepth 1 -type f -name '*.dump' \
    -printf '%f | %s octets | %TY-%Tm-%Td %TH:%TM\n' | sort
else
  echo 'Dossier de sauvegardes absent'
fi
printf '\n=== Santé du domaine actuel (ne teste PAS la nouvelle version) ===\n'
if command -v curl >/dev/null 2>&1; then
  curl -sS --max-time 15 -o /dev/null -w 'HTTP %{http_code}\n' \
    https://injs.badge-qr-code.pro/api/health/ || true
fi
REMOTE
