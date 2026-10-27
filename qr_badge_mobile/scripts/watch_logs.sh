#!/usr/bin/env bash
# Affiche uniquement les logs de l’application mobile INJS (appareil ou simulateur connecté).
set -euo pipefail
cd "$(dirname "$0")/.."
echo "Écoute des logs [qr_badge.*] — Ctrl+C pour arrêter"
flutter logs 2>&1 | grep --line-buffered 'qr_badge'
