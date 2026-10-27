#!/usr/bin/env bash
# Déploiement fiable sur iPhone physique (contourne le timeout CONFIGURATION_BUILD_DIR).
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
  echo "Aucun iPhone connecté. Branchez l'appareil puis relancez."
  exit 1
fi

echo "→ Appareil cible : $DEVICE"
echo "→ Debug LLDB (évite le timeout CONFIGURATION_BUILD_DIR avec Xcode 26)…"
flutter config --enable-lldb-debugging >/dev/null 2>&1 || true

echo "→ Fermeture de Xcode et nettoyage DerivedData Runner…"
osascript -e 'tell application "Xcode" to quit' 2>/dev/null || true
sleep 2
killall lldb-rpc-server 2>/dev/null || true
killall debugserver 2>/dev/null || true
rm -rf ~/Library/Developer/Xcode/DerivedData/Runner-* ~/Library/Developer/Xcode/DerivedData/*Runner* 2>/dev/null || true

MODE="${RUN_IOS_MODE:-debug}"
echo "→ flutter run --$MODE sur $DEVICE"
echo "   (logs visibles dans ce terminal ; filtre : grep qr_badge)"
echo ""

exec flutter run --"$MODE" -d "$DEVICE"
