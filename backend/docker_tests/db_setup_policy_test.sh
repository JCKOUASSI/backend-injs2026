#!/bin/sh
# =============================================================================
# INJS-LMD — Tests du blocage B2 (préparation de base au démarrage).
#
# Exécution :  sh backend/docker_tests/db_setup_policy_test.sh
# Aucune dépendance : ni Django, ni base, ni Docker. Les interpréteurs Python et
# gunicorn sont remplacés par des stubs qui journalisent leurs appels, ce qui
# permet de PROUVER qu'aucune migration n'est lancée au démarrage.
#
# Couverture exigée par la mission :
#   1. démarrage avec SKIP_DB_SETUP=true        -> aucune migration
#   2. démarrage sans variable                  -> aucune migration (défaut sûr)
#   3. démarrage avec variable invalide         -> refus, code 64
#   4. exécution explicite des migrations       -> migrate_explicit.sh
#   5. aucune migration implicite en production -> vérifié sur le journal d'appels
# =============================================================================
set -u

RACINE=$(cd "$(dirname "$0")/../.." && pwd)
ENTRY="$RACINE/backend/entrypoint.sh"
POLITIQUE="$RACINE/backend/scripts/db_setup_policy.sh"
MIGRATE="$RACINE/backend/scripts/migrate_explicit.sh"

ECHECS=0
REUSSIS=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

ok()   { REUSSIS=$((REUSSIS + 1)); printf '  PASS  %s\n' "$1"; }
ko()   { ECHECS=$((ECHECS + 1));  printf '  FAIL  %s\n' "$1"; }
titre(){ printf '\n== %s ==\n' "$1"; }

# --- Stubs : enregistrent chaque appel dans "$JOURNAL" ------------------------
mkdir -p "$TMP/bin"
for prog in python python3 gunicorn; do
    cat > "$TMP/bin/$prog" <<'STUB'
#!/bin/sh
printf '%s\n' "$(basename "$0") $*" >> "$JOURNAL"
exit 0
STUB
    chmod +x "$TMP/bin/$prog"
done

# Environnement minimal et reproductible pour exécuter l'entrypoint hors image.
export PATH="$TMP/bin:$PATH"
export JOURNAL="$TMP/appels.log"
export INJS_MEDIA_DIR="$TMP/media"
export INJS_STATIC_DIR="$TMP/static"
export INJS_DB_SETUP_POLICY="$POLITIQUE"
export INJS_ENTRYPOINT_PATH="$ENTRY"
export USE_POSTGRES=false
export DJANGO_SUPERUSER_EMAIL=""
export DJANGO_SUPERUSER_PASSWORD=""

# =============================================================================
titre "1. Démarrage avec SKIP_DB_SETUP=true"
: > "$JOURNAL"
env SKIP_DB_SETUP=true sh "$ENTRY" gunicorn config.wsgi:application >/dev/null 2>&1
CODE=$?
[ "$CODE" -eq 0 ] && ok "code retour 0" || ko "code retour $CODE (attendu 0)"
if grep -q "gunicorn" "$JOURNAL"; then ok "la commande fournie est exécutée"; else ko "commande non exécutée"; fi
if grep -q "migrate" "$JOURNAL"; then ko "migrate appelé alors que SKIP_DB_SETUP=true"; else ok "aucune migration lancée"; fi
if grep -q "collectstatic" "$JOURNAL"; then ko "collectstatic appelé"; else ok "aucun collectstatic"; fi

# =============================================================================
titre "2. Démarrage SANS variable (défaut sûr)"
: > "$JOURNAL"
env -u SKIP_DB_SETUP sh "$ENTRY" gunicorn config.wsgi:application >/dev/null 2>&1
CODE=$?
[ "$CODE" -eq 0 ] && ok "code retour 0" || ko "code retour $CODE (attendu 0)"
if grep -q "migrate" "$JOURNAL"; then ko "MIGRATION IMPLICITE sans variable : défaut non sûr"; else ok "aucune migration sans variable"; fi
if grep -q "gunicorn" "$JOURNAL"; then ok "la commande fournie est exécutée"; else ko "commande non exécutée"; fi

# Variantes considérées comme « skip »
for valeur in true 1 yes on TRUE " true "; do
    : > "$JOURNAL"
    env SKIP_DB_SETUP="$valeur" sh "$ENTRY" gunicorn x >/dev/null 2>&1
    if [ $? -eq 0 ] && ! grep -q migrate "$JOURNAL"; then
        ok "valeur '$valeur' -> aucune migration"
    else
        ko "valeur '$valeur' -> comportement inattendu"
    fi
done

# =============================================================================
titre "3. Démarrage avec variable invalide"
for valeur in oui ture FALSE_ TRU "2" "-1"; do
    : > "$JOURNAL"
    env SKIP_DB_SETUP="$valeur" sh "$ENTRY" gunicorn x >/dev/null 2>&1
    CODE=$?
    if [ "$CODE" -eq 64 ]; then ok "valeur '$valeur' -> refus (code 64)"; else ko "valeur '$valeur' -> code $CODE (attendu 64)"; fi
    if [ -s "$JOURNAL" ]; then ko "valeur '$valeur' -> une commande a été exécutée malgré le refus"; else ok "valeur '$valeur' -> aucune commande exécutée"; fi
done

# =============================================================================
titre "4. Préparation explicitement demandée (SKIP_DB_SETUP=false)"
for valeur in false 0 no off FALSE; do
    : > "$JOURNAL"
    env SKIP_DB_SETUP="$valeur" sh "$ENTRY" gunicorn x >/dev/null 2>&1
    if grep -q "manage.py migrate" "$JOURNAL"; then
        ok "valeur '$valeur' -> migrate exécuté explicitement"
    else
        ko "valeur '$valeur' -> migrate NON exécuté"
    fi
done

# =============================================================================
titre "5. Exécution explicite des migrations (migrate_explicit.sh)"
: > "$JOURNAL"
sh "$MIGRATE" --plan >/dev/null 2>&1
CODE=$?
[ "$CODE" -eq 0 ] && ok "--plan code retour 0" || ko "--plan code retour $CODE"
if grep -q "showmigrations" "$JOURNAL"; then ok "--plan affiche l'état"; else ko "--plan n'affiche pas l'état"; fi
if grep -q "migrate --noinput" "$JOURNAL"; then ko "--plan a appliqué des migrations"; else ok "--plan n'applique rien"; fi

: > "$JOURNAL"
env -u INJS_MIGRATE_ALLOW_APPLY sh "$MIGRATE" --apply >/dev/null 2>&1
CODE=$?
[ "$CODE" -eq 3 ] && ok "--apply sans autorisation -> refus (code 3)" || ko "--apply sans autorisation -> code $CODE (attendu 3)"
if grep -q "migrate --noinput" "$JOURNAL"; then ko "--apply non autorisé a appliqué des migrations"; else ok "--apply non autorisé n'applique rien"; fi

: > "$JOURNAL"
env INJS_MIGRATE_ALLOW_APPLY=1 sh "$MIGRATE" --apply >/dev/null 2>&1
CODE=$?
[ "$CODE" -eq 0 ] && ok "--apply autorisé code retour 0" || ko "--apply autorisé code retour $CODE"
if grep -q "migrate --noinput" "$JOURNAL"; then ok "--apply autorisé applique les migrations"; else ko "--apply autorisé n'a rien appliqué"; fi

# =============================================================================
titre "6. Aucune migration implicite en configuration de production"
# Configuration identique à deploy/production/compose.yml : SKIP_DB_SETUP=true
# explicite + commande gunicorn. Le journal ne doit contenir que gunicorn.
: > "$JOURNAL"
env SKIP_DB_SETUP=true USE_POSTGRES=true sh "$ENTRY" \
    gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers auto >/dev/null 2>&1
CODE=$?
[ "$CODE" -eq 0 ] && ok "démarrage production code 0" || ko "démarrage production code $CODE"
LIGNES=$(wc -l < "$JOURNAL" | tr -d ' ')
[ "$LIGNES" -eq 1 ] && ok "un seul processus lancé (gunicorn)" || ko "$LIGNES processus lancés (attendu 1)"
if grep -Eq "migrate|collectstatic" "$JOURNAL"; then
    ko "préparation de base exécutée en production"
else
    ok "aucune migration, aucun collectstatic en production"
fi

titre "7. SKIP_DB_SETUP actif sans commande"
: > "$JOURNAL"
env SKIP_DB_SETUP=true sh "$ENTRY" >/dev/null 2>&1
CODE=$?
[ "$CODE" -eq 1 ] && ok "refus explicite (code 1)" || ko "code $CODE (attendu 1)"

# =============================================================================
printf '\n=============================================\n'
printf 'RESULTAT B2 : %d réussis, %d échecs\n' "$REUSSIS" "$ECHECS"
printf '=============================================\n'
[ "$ECHECS" -eq 0 ] || exit 1
