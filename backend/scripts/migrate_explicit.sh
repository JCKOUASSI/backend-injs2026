#!/bin/sh
# =============================================================================
# INJS-LMD — Application EXPLICITE et contrôlée des migrations.
#
# MISSION 02 / BLOCAGE B2. Les migrations ne partent plus au démarrage : ce
# script est le seul chemin recommandé pour les appliquer, et il le fait en
# deux temps, sous contrôle humain.
#
# Usage (dans le conteneur backend, ou en local avec le venv actif) :
#   /app/scripts/migrate_explicit.sh --plan     affiche le plan, n'applique rien
#   /app/scripts/migrate_explicit.sh --apply    applique le plan affiché
#
# Variables :
#   INJS_MIGRATE_ALLOW_APPLY=1   requis pour --apply (garde-fou anti-inadvertance)
#
# Ce script n'exécute AUCUNE opération destructive : ni flush, ni reset, ni
# suppression de base. Il ne fait qu'appeler `migrate`.
# =============================================================================
set -eu

ACTION="${1:-}"
DG_MANAGE="${INJS_MANAGE:-python manage.py}"

usage() {
    cat >&2 <<'EOF'
Usage : migrate_explicit.sh --plan | --apply

  --plan   affiche `showmigrations --plan` et le plan détaillé, n'applique rien
  --apply  applique les migrations non appliquées (exige INJS_MIGRATE_ALLOW_APPLY=1)
EOF
    exit 2
}

case "$ACTION" in
    --plan|--apply) ;;
    *) usage ;;
esac

echo "[injs-be] Etat des migrations non appliquees :"
${DG_MANAGE} showmigrations --plan | grep -E '^\s*\[ \]' || echo "  (aucune migration en attente)"

echo
echo "[injs-be] Plan detaille :"
${DG_MANAGE} migrate --plan

if [ "$ACTION" = "--plan" ]; then
    echo
    echo "[injs-be] Mode --plan : aucune migration appliquee."
    exit 0
fi

if [ "${INJS_MIGRATE_ALLOW_APPLY:-0}" != "1" ]; then
    echo "[injs-be] --apply refuse : definir INJS_MIGRATE_ALLOW_APPLY=1 apres revue du plan." >&2
    exit 3
fi

echo
echo "[injs-be] Application des migrations (--noinput)..."
${DG_MANAGE} migrate --noinput
echo "[injs-be] Migrations appliquees."
