#!/usr/bin/env bash
# Build IPA App Store : compile Flutter, archive Xcode, export xcodebuild.
# (flutter build ipa échoue souvent à l'export sans compte Apple en CLI)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "→ Compilation iOS release…"
flutter build ios --release

echo "→ Archive Xcode…"
mkdir -p build/ios/archive
xcodebuild -workspace ios/Runner.xcworkspace \
  -scheme Runner \
  -configuration Release \
  -archivePath build/ios/archive/Runner.xcarchive \
  -allowProvisioningUpdates \
  DEVELOPMENT_TEAM=GP2G2KQTQV \
  archive

echo "→ Export IPA App Store…"
mkdir -p build/ios/ipa
xcodebuild -exportArchive \
  -archivePath build/ios/archive/Runner.xcarchive \
  -exportPath build/ios/ipa \
  -exportOptionsPlist ios/exportOptions.plist

IPA="$(find build/ios/ipa -maxdepth 1 -name '*.ipa' | head -1)"
if [[ -n "${IPA}" ]]; then
  echo ""
  echo "✓ IPA prête : ${IPA}"
  echo "  → Glisser dans Transporter → Deliver"
else
  echo "Erreur : aucun .ipa trouvé dans build/ios/ipa/" >&2
  exit 1
fi
