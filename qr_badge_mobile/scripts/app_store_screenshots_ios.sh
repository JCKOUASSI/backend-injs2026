#!/usr/bin/env bash
# Captures App Store Connect — emplacement « iPhone 6,5 pouces »
# Tailles acceptées par Apple : 1242×2688, 2688×1242, 1284×2778 ou 2778×1284 (px).
#
# Usage (depuis qr_badge_mobile/) :
#   ./scripts/app_store_screenshots_ios.sh boot
#       → démarre un simulateur adapté et ouvre l’app Simulator.
#   Lancez ensuite : flutter run -d <UDID affiché>
#   Placez l’app sur l’écran à capturer, puis :
#   ./scripts/app_store_screenshots_ios.sh capture nom_sans_extension
#       → écrit app_store_exports/6.5inch/nom_sans_extension.png
#   ./scripts/app_store_screenshots_ios.sh verify
#       → contrôle la taille de chaque PNG du dossier d’export.
#   ./scripts/app_store_screenshots_ios.sh resize chemin/vers/capture.png nom_export [1242|1284]
#       → redimensionne une capture (ex. iPhone 17 en 1206×2622) vers 1242×2688 ou 1284×2778
#         exactes, requises par App Store Connect pour le slot 6,5".
#
# Autre option : dans le simulateur, Cmd+S enregistre sur le Bureau (vérifiez la taille avec Aperçu / sips).
#
# Variable d’environnement (optionnel) :
#   APP_STORE_SIM_NAME="iPhone 16 Plus"  (ou iPhone 15 Pro Max, iPhone 11 Pro Max, etc.)

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTDIR="${ROOT}/app_store_exports/6.5inch"
SIM_NAME="${APP_STORE_SIM_NAME:-iPhone 16 Plus}"

# Correspond en général à 1284×2778 (portrait) — valide pour le slot 6,5".
# iPhone 11 Pro Max / XS Max → souvent 1242×2688. Les deux formats sont acceptés.

allowed_dims() {
  echo "1242x2688 2688x1242 1284x2778 2778x1284"
}

find_sim_udid() {
  local name="$1"
  local udid
  udid="$(
    xcrun simctl list devices available -j 2>/dev/null | command -p python3 -c "
import json, sys
name = sys.argv[1]
j = json.load(sys.stdin)
for runtime, devs in j.get('devices', {}).items():
  if 'iOS' not in runtime:
    continue
  for d in devs:
    if d.get('name') == name and d.get('isAvailable', True):
      print(d['udid'])
      sys.exit(0)
sys.exit(1)
" "$name" 2>/dev/null || true
  )"
  if [[ -n "${udid}" ]]; then
    echo "$udid"
    return 0
  fi
  # repli : liste texte
  udid="$(xcrun simctl list devices available | grep -F "${name}" | head -1 | sed -n 's/.*(\([A-F0-9-]*\)).*/\1/p')"
  if [[ -n "${udid}" ]]; then
    echo "$udid"
  fi
}

cmd_boot() {
  local udid
  udid="$(find_sim_udid "$SIM_NAME" || true)"
  if [[ -z "${udid}" ]]; then
    echo "Simulateur « ${SIM_NAME} » introuvable. Installez un runtime iOS dans Xcode," >&2
    echo "ou choisissez un autre modèle, ex. :" >&2
    echo "  APP_STORE_SIM_NAME='iPhone 15 Pro Max' $0 boot" >&2
    echo "" >&2
    echo "Modèles courants pour 6,5\" (vérifier avec : xcrun simctl list devices | grep iPhone) :" >&2
    exit 1
  fi
  xcrun simctl boot "$udid" 2>/dev/null || true
  open -a Simulator
  echo "Simulateur : ${SIM_NAME}"
  echo "UDID       : ${udid}"
  echo ""
  echo "Ensuite, depuis ${ROOT} :"
  echo "  cd \"${ROOT}\" && flutter run -d ${udid}"
  echo ""
  echo "Puis, une fois l’écran prêt :"
  echo "  ./scripts/app_store_screenshots_ios.sh capture 01_connexion"
}

cmd_capture() {
  local base="$1"
  mkdir -p "$OUTDIR"
  local path="${OUTDIR}/${base}.png"
  if ! xcrun simctl list devices | grep -q Booted; then
    echo "Aucun simulateur démarré. Lancez d’abord : $0 boot" >&2
    exit 1
  fi
  xcrun simctl io booted screenshot "$path"
  echo "Enregistré : $path"
  verify_one "$path"
}

verify_one() {
  local f="$1"
  local w h
  w="$(sips -g pixelWidth "$f" 2>/dev/null | awk '/pixelWidth:/ {print $2}')"
  h="$(sips -g pixelHeight "$f" 2>/dev/null | awk '/pixelHeight:/ {print $2}')"
  local dim="${w}x${h}"
  case "$dim" in
    1242x2688|2688x1242|1284x2778|2778x1284)
      echo "OK — ${dim} (accepté pour 6,5 pouces App Store Connect)."
      ;;
    *)
      echo "ATTENTION — ${dim} n’est pas une taille listée pour ce slot (attendu : $(allowed_dims))." >&2
      echo "  Essayez APP_STORE_SIM_NAME='iPhone 11 Pro Max' pour du 1242×2688, ou un autre « Plus / Pro Max »." >&2
      return 1
      ;;
  esac
}

cmd_verify() {
  local ok=0
  if [[ ! -d "$OUTDIR" ]]; then
    echo "Dossier vide : ${OUTDIR}" >&2
    exit 1
  fi
  shopt -s nullglob
  local f
  for f in "${OUTDIR}"/*.png; do
    echo "--- $(basename "$f") ---"
    verify_one "$f" || ok=1
  done
  exit "$ok"
}

# sips -z hauteur largeur (portrait)
cmd_resize() {
  [[ -n "${2:-}" ]] || {
    echo "usage: $0 resize <fichier_source.png> <nom_sans_extension> [1242|1284]" >&2
    echo "  1242 (défaut) → 1242×2688 px ; 1284 → 1284×2778 px." >&2
    exit 1
  }
  local src="$1"
  local base="$2"
  local mode="${3:-1242}"
  [[ -f "$src" ]] || { echo "Fichier introuvable : $src" >&2; exit 1; }
  mkdir -p "$OUTDIR"
  local dest="${OUTDIR}/${base}.png"
  case "$mode" in
    1242) sips -z 2688 1242 "$src" --out "$dest" >/dev/null ;;
    1284) sips -z 2778 1284 "$src" --out "$dest" >/dev/null ;;
    *)
      echo "Mode inconnu : $mode (utilisez 1242 ou 1284)." >&2
      exit 1
      ;;
  esac
  echo "Écrit : $dest"
  verify_one "$dest"
}

case "${1:-}" in
  boot)   cmd_boot ;;
  capture)
    [[ -n "${2:-}" ]] || { echo "usage: $0 capture <nom_sans_extension>" >&2; exit 1; }
    cmd_capture "$2"
    ;;
  verify) cmd_verify ;;
  resize)
    shift
    cmd_resize "$@"
    ;;
  *)
    echo "usage: $0 boot | capture <nom> | verify | resize <src.png> <nom> [1242|1284]" >&2
    exit 1
    ;;
esac
