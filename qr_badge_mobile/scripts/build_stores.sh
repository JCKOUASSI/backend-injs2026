#!/usr/bin/env bash
# Build release Play Store (AAB) et/ou App Store (IPA).
#
# Usage :
#   ./scripts/build_stores.sh              # Android + iOS
#   ./scripts/build_stores.sh android      # AAB uniquement
#   ./scripts/build_stores.sh ios          # IPA uniquement
#   OBFUSCATE=1 ./scripts/build_stores.sh android   # AAB + obfuscation Dart
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TARGET="${1:-all}"
OBFUSCATE="${OBFUSCATE:-0}"

usage() {
  echo "Usage: $0 [all|android|ios]" >&2
  exit 1
}

case "$TARGET" in
  all|android|ios) ;;
  -h|--help) usage ;;
  *) usage ;;
esac

VERSION="$(grep '^version:' pubspec.yaml | awk '{print $2}')"
echo "═══════════════════════════════════════════════"
echo " INJS-LMD — build stores (version ${VERSION})"
echo "═══════════════════════════════════════════════"
echo ""

echo "→ flutter pub get"
flutter pub get
echo ""

build_android() {
  echo "── Play Store (Android AAB) ──"
  if [[ ! -f android/key.properties ]]; then
    echo "⚠ android/key.properties absent — le AAB sera signé en debug (refus Play Store)." >&2
    echo "  Copiez android/key.properties.example → android/key.properties" >&2
    echo ""
  fi

  # Évite « intermediary-bundle.aab already exists » après un build Gradle interrompu.
  rm -rf build/app/intermediates/intermediary_bundle 2>/dev/null || true

  local -a args=(build appbundle --release)
  if [[ "$OBFUSCATE" == "1" ]]; then
    args+=(--obfuscate --split-debug-info=build/debug-info)
    echo "→ Obfuscation Dart activée (symboles : build/debug-info/)"
  fi

  echo "→ flutter ${args[*]}"
  flutter "${args[@]}"

  local aab="build/app/outputs/bundle/release/app-release.aab"
  local mapping="build/app/outputs/mapping/release/mapping.txt"
  echo ""
  if [[ -f "$aab" ]]; then
    echo "✓ AAB : ${ROOT}/${aab}"
    echo "  → Play Console : importer ce fichier"
  fi
  if [[ -f "$mapping" ]]; then
    echo "✓ Mapping R8 : ${ROOT}/${mapping}"
    echo "  → Play Console : fichier de désobscurcissement (même version)"
  fi
  if [[ "$OBFUSCATE" == "1" ]]; then
    echo "✓ Symboles Dart : ${ROOT}/build/debug-info/ (à conserver hors store)"
  fi
  echo ""
}

build_ios() {
  echo "── App Store (iOS IPA) ──"
  bash "$ROOT/scripts/build_ipa_appstore.sh"
  echo ""
}

case "$TARGET" in
  all)
    build_android
    build_ios
    ;;
  android) build_android ;;
  ios) build_ios ;;
esac

echo "═══════════════════════════════════════════════"
echo " Terminé."
echo "═══════════════════════════════════════════════"
