#!/usr/bin/env bash
# Installe l'app sans session debug Xcode (utile si flutter run échoue au lancement).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=lib/ios_device.sh
source "$ROOT/scripts/lib/ios_device.sh"

DEVICE="${1:-}"
if [[ -z "$DEVICE" ]]; then
  DEVICE="$(pick_ios_device_id)"
fi
if [[ -z "$DEVICE" ]]; then
  echo "Aucun iPhone connecté."
  exit 1
fi

echo "→ Build debug iOS…"
flutter build ios --debug

echo "→ Installation sur $DEVICE (sans attach Xcode)…"
flutter install -d "$DEVICE"

echo ""
echo "App installée. Ouvrez l’application INJS de présence sur l’iPhone."
echo "Pour les logs sans relancer via Xcode :"
echo "  ./scripts/watch_logs.sh"
