#!/usr/bin/env bash
# =============================================================================
# Sauvegarde des DONNÉES de l'aperçu (base SQLite du bac à sable).
#
# Pourquoi : le bac à sable d'aperçu est ÉPHÉMÈRE. À sa réinitialisation, seuls
# les fichiers commités sur GitHub survivent ; `backend/db.sqlite3` est ignoré
# par Git et disparaît. Les données officielles et de démonstration sont
# reproductibles (seed_data.py + importer_referentiels_injs, voir
# arena/reconstruire.sh), mais les données SAISIES dans l'application ne le
# sont pas : ce script les exporte pour pouvoir les restaurer
# (arena/restaurer-donnees.sh).
#
# Produit, dans backups/apercu-<horodatage>/ (dossier ignoré par Git) :
#   - donnees.json   : dumpdata portable (restaurable sur SQLite ou PostgreSQL)
#   - db.sqlite3     : copie cohérente de la base (API sqlite3 backup)
#   - media.tar.gz   : fichiers téléversés, si backend/media/ est non vide
#   - MANIFESTE.txt  : date, commit Git, compteurs de contrôle
#   - SHA256SUMS.txt : empreintes SHA-256 (vérification : sha256sum -c)
#
# ⚠ Le dépôt GitHub est PUBLIC : ne commitez JAMAIS ces fichiers (ils
# contiennent les comptes et leurs empreintes de mot de passe). `backups/`
# est déjà dans .gitignore. Téléchargez la sauvegarde hors du bac à sable.
#
#   ./arena/sauvegarder-donnees.sh
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
HORODATAGE="$(date '+%Y%m%d-%H%M%S')"
DEST="$ROOT/backups/apercu-$HORODATAGE"

log() { printf '\033[1;36m[sauvegarde]\033[0m %s\n' "$*"; }

if [ ! -x "$VENV/bin/python" ]; then
  echo "Environnement virtuel absent : lancez d'abord ./arena/reconstruire.sh" >&2
  exit 1
fi
if [ ! -f "$BACKEND/db.sqlite3" ]; then
  echo "Base $BACKEND/db.sqlite3 absente : rien à sauvegarder." >&2
  exit 1
fi

mkdir -p "$DEST"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-arena.settings_sandbox}"
export USE_SQLITE=1

# ── 1. Export portable (JSON) ────────────────────────────────────────────────
# Même périmètre que docs/SAUVEGARDE_RESTAURATION.md §3.3 : les tables exclues
# sont recréées par `migrate`. --natural-foreign permet de résoudre les clés
# vers ces tables (contenttypes, permissions) à la restauration.
log "Export des données (dumpdata)…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py dumpdata \
  --natural-foreign \
  --exclude contenttypes \
  --exclude auth.permission \
  --exclude sessions \
  --exclude admin.logentry \
  --indent 2 -o "$DEST/donnees.json")

# ── 2. Copie cohérente de la base SQLite (même serveur en cours) ───────────
log "Copie de la base SQLite…"
"$VENV/bin/python" - "$BACKEND/db.sqlite3" "$DEST/db.sqlite3" <<'PY'
import sqlite3, sys
source = sqlite3.connect(sys.argv[1])
cible = sqlite3.connect(sys.argv[2])
with cible:
    source.backup(cible)
PY

# ── 3. Fichiers téléversés ───────────────────────────────────────────────────
if [ -d "$BACKEND/media" ] && [ -n "$(ls -A "$BACKEND/media" 2>/dev/null)" ]; then
  log "Archivage de backend/media/…"
  tar -czf "$DEST/media.tar.gz" -C "$BACKEND" media
fi

# ── 4. Manifeste + empreintes ────────────────────────────────────────────────
log "Manifeste et empreintes SHA-256…"
{
  echo "Sauvegarde des données INJS-LMD (aperçu)"
  echo "Date    : $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Commit  : $(cd "$ROOT" && git rev-parse --short HEAD 2>/dev/null || echo inconnu)"
  echo "Branche : $(cd "$ROOT" && git branch --show-current 2>/dev/null || echo inconnue)"
  (cd "$BACKEND" && "$VENV/bin/python" - <<'PY' 2>/dev/null || true
import django
django.setup()
from django.contrib.auth import get_user_model
from referentiels.models import RefEcole, RefFiliere, RefMention
from formations.models import RefFormation
print(f"Comptes utilisateurs : {get_user_model().objects.count()}")
print(f"Écoles / mentions    : {RefEcole.objects.count()} / {RefMention.objects.count()}")
print(f"Filières             : {RefFiliere.objects.count()}")
print(f"Formations (cycles)  : {RefFormation.objects.count()}")
PY
  )
} > "$DEST/MANIFESTE.txt"

(
  cd "$DEST"
  fichiers="donnees.json db.sqlite3 MANIFESTE.txt"
  [ -f media.tar.gz ] && fichiers="$fichiers media.tar.gz"
  # Noms de fichiers sans espace : le découpage de $fichiers est volontaire.
  if command -v sha256sum >/dev/null; then
    sha256sum $fichiers > SHA256SUMS.txt
  else
    shasum -a 256 $fichiers > SHA256SUMS.txt
  fi
)

log "Sauvegarde terminée : $DEST"
ls -lh "$DEST"
echo
echo "Restauration : ./arena/restaurer-donnees.sh $DEST"
echo "⚠ Pensez à télécharger cette sauvegarde hors du bac à sable :"
echo "  elle n'est pas versionnée (dépôt GitHub public, backups/ ignoré par Git)."
