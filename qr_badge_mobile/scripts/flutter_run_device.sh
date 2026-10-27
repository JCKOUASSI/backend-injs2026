#!/usr/bin/env bash
# Lance l’app sur un appareil réel avec l’IP LAN du Mac (backend runserver 0.0.0.0:8001).
# Usage : depuis qr_badge_mobile/  →  ./scripts/flutter_run_device.sh
#         ou : ./scripts/flutter_run_device.sh -d "iPhone de Tobi"
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${DEV_API_HOST:-}"
if [[ -z "${HOST}" ]]; then
  HOST="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [[ -z "${HOST}" ]]; then
  HOST="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi
if [[ -z "${HOST}" ]]; then
  echo "Impossible de détecter l’IP LAN. Définissez DEV_API_HOST, ex. :" >&2
  echo "  export DEV_API_HOST=192.168.1.12 && ./scripts/flutter_run_device.sh" >&2
  exit 1
fi

PORT="${DEV_API_PORT:-8001}"
echo "API backend attendue sur http://${HOST}:${PORT} (dart-define)"
exec flutter run \
  --dart-define=DEV_API_HOST="$HOST" \
  --dart-define=DEV_API_PORT="$PORT" \
  "$@"
