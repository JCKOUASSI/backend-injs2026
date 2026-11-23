#!/usr/bin/env bash
# =============================================================================
# Aperçu MOBILE (Flutter web) — port 3001.
#
# Le SDK Flutter n'est pas installé dans le bac à sable et ne peut pas être
# téléchargé (storage.googleapis.com et pub.dev sont bloqués par le proxy :
# erreur TLS « SSL_ERROR_SYSCALL »). Ce script est donc écrit pour fonctionner
# dès qu'une archive ou un SDK est présent dans le workspace, et pour échouer
# AVEC UN MESSAGE UTILE sinon — jamais en silence.
#
# Emplacements reconnus, dans cet ordre :
#   .sdk/flutter/                     (SDK déjà extrait)
#   .sdk/flutter_linux_*.tar.xz       (archive officielle, extraite ici)
#   flutter_linux_*.tar.xz            (archive déposée à la racine)
#   $FLUTTER_SDK / un `flutter` déjà dans le PATH
#
#   ./arena/lancer-mobile.sh              # build + serveur 3001
#   ./arena/lancer-mobile.sh --sans-build # réutilise build/web existant
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/qr_badge_mobile"
SDK_DIR="$ROOT/.sdk"
PORT="${PORT:-3001}"
SANS_BUILD=0
[ "${1:-}" = "--sans-build" ] && SANS_BUILD=1

log() { printf '\033[1;36m[mobile]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[mobile]\033[0m %s\n' "$*" >&2; exit 2; }

# ── 1. Localiser le SDK ──────────────────────────────────────────────────────
FLUTTER=""
if [ -n "${FLUTTER_SDK:-}" ] && [ -x "$FLUTTER_SDK/bin/flutter" ]; then
  FLUTTER="$FLUTTER_SDK/bin/flutter"
elif [ -x "$SDK_DIR/flutter/bin/flutter" ]; then
  FLUTTER="$SDK_DIR/flutter/bin/flutter"
elif command -v flutter >/dev/null 2>&1; then
  FLUTTER="$(command -v flutter)"
else
  ARCHIVE="$(ls -1 "$SDK_DIR"/flutter_linux_*.tar.xz "$ROOT"/flutter_linux_*.tar.xz 2>/dev/null | head -1 || true)"
  if [ -n "$ARCHIVE" ]; then
    log "Archive trouvée : $ARCHIVE — extraction (peut prendre 1 à 2 minutes)…"
    mkdir -p "$SDK_DIR"
    tar -xJf "$ARCHIVE" -C "$SDK_DIR"
    [ -x "$SDK_DIR/flutter/bin/flutter" ] || die "Archive inattendue : bin/flutter absent après extraction."
    FLUTTER="$SDK_DIR/flutter/bin/flutter"
  fi
fi

if [ -z "$FLUTTER" ]; then
  cat >&2 <<'MSG'
[mobile] SDK Flutter ABSENT — l'aperçu mobile ne peut pas démarrer.

Aucun SDK trouvé, et le téléchargement automatique est impossible ici :
  - storage.googleapis.com (archives du SDK) : TLS refusé (SSL_ERROR_SYSCALL)
  - pub.dev (dépendances)                     : TLS refusé
  - api.github.com / codeload.github.com      : joignables, mais flutter/flutter
    est un dépôt de SOURCE (le SDK se construit avec des artefacts téléchargés
    depuis storage.googleapis.com) — donc inutilisable hors ligne.

Pour activer l'aperçu, déposer dans le workspace l'un de ces éléments :

  A. l'archive officielle du SDK
       <dépôt>/.sdk/flutter_linux_<version>-stable.tar.xz
     (https://docs.flutter.dev/release/archive → « Linux », ~1 Go)

  B. un SDK déjà extrait
       <dépôt>/.sdk/flutter/bin/flutter

  C. si l'archive ne contient pas les paquets Dart, le cache pub de votre
     machine, décompressé dans  <dépôt>/.sdk/pub-cache  (issu de ~/.pub-cache) ;
     le script l'utilisera via PUB_CACHE pour un `flutter pub get --offline`.

Dès que l'un de ces éléments est présent, relancer :
       ./arena/lancer-mobile.sh
MSG
  exit 2
fi

export PATH="$(dirname "$FLUTTER"):$PATH"
log "SDK : $FLUTTER"
"$FLUTTER" --version | head -2 || die "SDK inutilisable (flutter --version en échec)."

# Cache pub hors ligne si fourni par l'utilisateur.
if [ -d "$SDK_DIR/pub-cache" ]; then
  export PUB_CACHE="$SDK_DIR/pub-cache"
  log "PUB_CACHE hors ligne : $PUB_CACHE"
fi

cd "$APP"

# ── 2. Dépendances ───────────────────────────────────────────────────────────
if [ ! -f ".dart_tool/package_config.json" ]; then
  log "Résolution des dépendances…"
  if [ -n "${PUB_CACHE:-}" ]; then
    "$FLUTTER" pub get --offline || die "pub get --offline a échoué (cache incomplet)."
  else
    "$FLUTTER" pub get || die "pub get a échoué (pub.dev inaccessible : fournir .sdk/pub-cache)."
  fi
fi

# ── 3. Build web ─────────────────────────────────────────────────────────────
if [ "$SANS_BUILD" -eq 0 ]; then
  log "Build web (API_BASE_URL vide → appels /api sur la même origine)…"
  "$FLUTTER" build web --release --dart-define=API_BASE_URL= \
    || die "flutter build web a échoué (voir la sortie ci-dessus)."
fi

[ -f "$APP/build/web/index.html" ] || die "build/web/index.html absent : build non effectué."

# ── 4. Serveur (statique + relais /api vers Django) ─────────────────────────
log "Serveur mobile sur 0.0.0.0:$PORT (relais /api → 127.0.0.1:8000)"
exec python3 "$ROOT/arena/serveur_mobile.py" --port "$PORT" --racine "$APP/build/web"
