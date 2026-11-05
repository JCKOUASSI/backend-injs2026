#!/bin/sh
# =====================================================================
# H5 — harnais de tests du kit d'expertise des sauvegardes
# =====================================================================
# Objet : rejouer les 8 tests nominaux et dégradés du LOT H5, et
#         démontrer par mesure — et non par lecture du code — que le kit
#         n'analyse jamais partiellement une archive gzip corrompue.
#
# Nature : LECTURE SEULE. Le harnais ne lit que les fichiers de test
#          qu'il fabrique lui-même dans un répertoire temporaire, et
#          n'exécute jamais pg_restore autrement qu'avec --list.
#          Aucun accès réseau, aucun VPS, aucune base de données.
#
# Usage :
#   sh h5_tests.sh [chemin/vers/h5_expertise_sauvegardes.sh]
#   H5_DUMP_FIXTURE=/chemin/vers/archive.dump sh h5_tests.sh   # active T2
#
# Sortie : une ligne PASS/FAIL/SKIP par test, puis un bilan.
#          Code de retour 0 si aucun FAIL, 1 sinon.
# =====================================================================

set -u

KIT="${1:-$(dirname "$0")/../h5_expertise_sauvegardes.sh}"
KIT=$(cd "$(dirname "$KIT")" && pwd)/$(basename "$KIT")

TMP=$(mktemp -d "${TMPDIR:-/tmp}/h5tests.XXXXXX") || exit 1
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0; FAIL=0; SKIP=0
SHIM="$TMP/shim"; mkdir -p "$SHIM"
REAL_GZIP=$(command -v gzip 2>/dev/null || true)

ok()   { PASS=$((PASS+1)); printf '  PASS  %-6s %s\n' "$1" "$2"; }
ko()   { FAIL=$((FAIL+1)); printf '  FAIL  %-6s %s\n' "$1" "$2"; }
skip() { SKIP=$((SKIP+1)); printf '  SKIP  %-6s %s\n' "$1" "$2"; }

# assertion simple : verite d'une condition shell
verifie() {  # $1=id $2=libelle $3..=commande/test
  _id="$1"; _lib="$2"; shift 2
  if "$@" >/dev/null 2>&1; then ok "$_id" "$_lib"; else ko "$_id" "$_lib"; fi
}

echo "====================================================================="
echo " H5 — TESTS DU KIT D'EXPERTISE DES SAUVEGARDES"
echo "====================================================================="
echo " kit    : $KIT"
echo " bac    : $TMP"
[ -n "$REAL_GZIP" ] || { echo " gzip introuvable — impossible de continuer"; exit 1; }

# ---------------------------------------------------------------------
# Fabrique de jeux d'essai (aucune base de données, aucun pg_dump requis)
# ---------------------------------------------------------------------
TABLES_LMD="referentiels_reffiliere scolarite_semestre scolarite_ue scolarite_ecue
jurys_decisionjury edts_emploidutemps edts_affectationcreneau presences_pointage
habilitations_rolemetier formations_participant django_migrations authentication_user"

fabrique_sql() {  # $1=cible  $2=marqueur de table supplémentaire (optionnel)  $3=remplissage
  _cible="$1"; _extra="${2:-}"; _pad="${3:-0}"
  {
    echo "--"
    echo "-- PostgreSQL database dump"
    echo "--"
    echo "SET statement_timeout = 0;"
    [ -n "$_extra" ] && echo "CREATE TABLE public.$_extra (id integer);"
    for t in $TABLES_LMD; do
      echo "CREATE TABLE public.$t ("
      echo "    id integer NOT NULL,"
      echo "    code character varying(20)"
      echo ");"
      echo "CREATE SEQUENCE public.${t}_id_seq START WITH 1 INCREMENT BY 1;"
      echo "ALTER TABLE ONLY public.$t ALTER COLUMN id SET DEFAULT nextval('public.${t}_id_seq'::regclass);"
      echo "ALTER TABLE ONLY public.$t ADD CONSTRAINT ${t}_pkey PRIMARY KEY (id);"
      echo "COPY public.$t (id, code) FROM stdin;"
      echo "1	ENSEP-S1"
      echo "2	S2"
      echo "3	ECTS"
      echo "\\."
    done
    _i=0
    while [ "$_i" -lt "$_pad" ]; do echo "-- remplissage $_i ECTS S3 S10"; _i=$((_i+1)); done
  } > "$_cible"
}

# Dump « complet » : 12 tables LMD, valeurs ENSEP / S1..S10 / ECTS présentes
fabrique_sql "$TMP/a.sql" "" 40
# Dump « partiel » : sous-ensemble, sans jurys ni habilitations ni migrations
grep -vE 'jurys_decisionjury|habilitations_rolemetier|django_migrations|authentication_user' \
     "$TMP/a.sql" > "$TMP/b.sql"
# gzip sain du dump complet
"$REAL_GZIP" -c "$TMP/a.sql" > "$TMP/sain.sql.gz"

# gzip corrompu MAIS dont la partie décompressable contient un marqueur :
# c'est ce qui rend le test non vacant — une analyse partielle le verrait.
MARQUEUR="zzz_marqueur_analyse_partielle"
fabrique_sql "$TMP/marque.sql" "$MARQUEUR" 2000
"$REAL_GZIP" -c "$TMP/marque.sql" > "$TMP/complet.sql.gz"
_taille=$(wc -c < "$TMP/complet.sql.gz" | tr -d ' ')
head -c $((_taille * 3 / 4)) "$TMP/complet.sql.gz" > "$TMP/corrompu.sql.gz"

# ---------------------------------------------------------------------
# Shim gzip : compte chaque invocation et son mode
# ---------------------------------------------------------------------
printf '%s\n' '#!/bin/sh' \
  'printf "%s\n" "$*" >> "$GZIP_CALLS"' \
  "exec \"$REAL_GZIP\" \"\$@\"" > "$SHIM/gzip"
chmod +x "$SHIM/gzip"

execute_kit() {  # $1=log  $@=arguments supplementaires sous forme VAR=valeur
  _log="$1"; shift
  env PATH="$SHIM:$PATH" GZIP_CALLS="$TMP/gzip.calls" "$@" \
      sh "$KIT" > "$_log" 2>&1
  return $?
}

# =====================================================================
echo
echo "--- T1 — validation syntaxique ---------------------------------------"
if sh -n "$KIT" 2>"$TMP/t1.err"; then ok T1 "sh -n sur le kit"; else ko T1 "sh -n : $(cat "$TMP/t1.err")"; fi

echo
echo "--- T2 — archive custom réelle (pg_restore --list) -------------------"
if [ -n "${H5_DUMP_FIXTURE:-}" ] && [ -f "${H5_DUMP_FIXTURE:-}" ]; then
  execute_kit "$TMP/t2.log" MODE=local \
    S1_DUMP="$H5_DUMP_FIXTURE" S2_GZ="$TMP/sain.sql.gz" \
    S3_SQL_A="$TMP/a.sql" S3_SQL_B="$TMP/b.sql"
  if grep -q '^s1_custom=lue' "$TMP/t2.log"; then
    _t=$(sed -n 's/^s1_custom=lue objets=[0-9]* tables=\([0-9]*\)$/\1/p' "$TMP/t2.log")
    if [ "${_t:-0}" -gt 0 ]; then ok T2 "sommaire lu, ${_t} tables détectées"; else ko T2 "sommaire lu mais 0 table"; fi
  else
    ko T2 "archive custom non lue : $(grep -m1 'ÉCHEC' "$TMP/t2.log" || echo 'cause inconnue')"
  fi
else
  skip T2 "aucune archive custom fournie (H5_DUMP_FIXTURE non défini)"
fi

echo
echo "--- T3 — gzip sain : intégrité et contenu ----------------------------"
execute_kit "$TMP/t3.log" MODE=local \
  S1_DUMP="${H5_DUMP_FIXTURE:-$TMP/absent.dump}" S2_GZ="$TMP/sain.sql.gz" \
  S3_SQL_A="$TMP/a.sql" S3_SQL_B="$TMP/b.sql"
verifie T3a "gzip -t annoncé OK"        grep -q 'intégrité gzip : OK' "$TMP/t3.log"
verifie T3b "12 tables détectées"       grep -q 'nombre de tables : 12' "$TMP/t3.log"
verifie T3c "synthèse s2_gzip=lue"      grep -q '^s2_gzip=lue tables=12' "$TMP/t3.log"

echo
echo "--- T4 — comparaison des deux dumps SQL ------------------------------"
verifie T4a "A : 12 tables"             grep -q 'tables       : 12' "$TMP/t3.log"
verifie T4b "B : 8 tables"              grep -q 'tables       : 8' "$TMP/t3.log"
verifie T4c "8 tables communes"         grep -q 'tables communes        : 8' "$TMP/t3.log"
verifie T4d "4 seulement dans A"        grep -q 'seulement dans A       : 4' "$TMP/t3.log"

echo
echo "--- T5 — matrice de conformité INJS ----------------------------------"
# colonne 1 = objet, 2 = custom, 3 = gzip, 4 = sql A, 5 = sql B
awk '/OBJET ATTENDU/{f=1;next} /5\.2 Indices/{f=0} f && NF==5 {
       print $1"|custom="$2"|gzip="$3"|sqlA="$4"|sqlB="$5 }' \
  "$TMP/t3.log" > "$TMP/t5.matrice"
verifie T5a "gzip : referentiels_reffiliere=1" grep -q '^referentiels_reffiliere|custom=[0-9]*|gzip=1|' "$TMP/t5.matrice"
verifie T5b "sql B : jurys_decisionjury=0"      grep -q '^jurys_decisionjury|.*|sqlB=0$' "$TMP/t5.matrice"
verifie T5c "15 objets attendus évalués"        test "$(wc -l < "$TMP/t5.matrice" | tr -d ' ')" = "15"
verifie T5d "indices de valeurs : ENSEP détecté" grep -q 'ENSEP=1' "$TMP/t3.log"

echo
echo "--- T6 — fichiers absents -------------------------------------------"
execute_kit "$TMP/t6.log" MODE=local \
  S1_DUMP="$TMP/absent.dump" S2_GZ="$TMP/absent.gz" \
  S3_SQL_A="$TMP/absent_a.sql" S3_SQL_B="$TMP/absent_b.sql"
verifie T6a "4 messages FICHIER ABSENT"  test "$(grep -c 'FICHIER ABSENT' "$TMP/t6.log")" = "4"
verifie T6b "synthèse : tout non_lue"    grep -q '^s1_custom=non_lue' "$TMP/t6.log"
verifie T6c "sortie sans plantage"       grep -q 'SYNTHESE_H5_END' "$TMP/t6.log"

echo
echo "--- T7 — archive custom tronquée ------------------------------------"
if [ -n "${H5_DUMP_FIXTURE:-}" ] && [ -f "${H5_DUMP_FIXTURE:-}" ]; then
  head -c 4000 "$H5_DUMP_FIXTURE" > "$TMP/tronque.dump"
  execute_kit "$TMP/t7.log" MODE=local \
    S1_DUMP="$TMP/tronque.dump" S2_GZ="$TMP/sain.sql.gz" \
    S3_SQL_A="$TMP/a.sql" S3_SQL_B="$TMP/b.sql"
  verifie T7a "échec de lecture signalé" grep -q 'ÉCHEC de lecture du sommaire' "$TMP/t7.log"
  verifie T7b "synthèse s1_custom=non_lue" grep -q '^s1_custom=non_lue' "$TMP/t7.log"
  verifie T7c "le reste de l'audit continue" grep -q '^s2_gzip=lue' "$TMP/t7.log"
else
  skip T7 "dépend de l'archive custom (H5_DUMP_FIXTURE non défini)"
fi

echo
echo "--- T8 — gzip corrompu : statut et absence de fuite ------------------"
execute_kit "$TMP/t8.log" MODE=local \
  S1_DUMP="${H5_DUMP_FIXTURE:-$TMP/absent.dump}" S2_GZ="$TMP/corrompu.sql.gz" \
  S3_SQL_A="$TMP/a.sql" S3_SQL_B="$TMP/b.sql"
verifie T8a "intégrité annoncée en échec" grep -q 'intégrité gzip : ÉCHEC' "$TMP/t8.log"
verifie T8b "synthèse s2_gzip=corrompue"  grep -q '^s2_gzip=corrompue' "$TMP/t8.log"
verifie T8c "message d'erreur gzip confiné" grep -q 'unexpected end of file' "$TMP/t8.log"
verifie T8d "aucune ligne parasite dans la synthèse" \
  test -z "$(awk '/SYNTHESE_H5_BEGIN/,/SYNTHESE_H5_END/' "$TMP/t8.log" | grep -vE '^(SYNTHESE_H5|date_utc=|mode=|s[123][ab]?_?[a-z]*=)')"

echo
echo "--- T9 — NON-RÉGRESSION : aucune analyse partielle du gzip corrompu --"
# 9.0 le jeu d'essai doit être réellement corrompu, sinon le test est vacant
if "$REAL_GZIP" -t "$TMP/corrompu.sql.gz" >/dev/null 2>&1; then
  ko T9.0 "le jeu d'essai n'est pas corrompu — test invalide"
else
  ok T9.0 "jeu d'essai corrompu (gzip -t échoue)"
fi
# 9.1 et le marqueur doit être visible dans la partie décompressable,
#     sinon l'absence de marqueur dans le log ne prouverait rien
if "$REAL_GZIP" -dc "$TMP/corrompu.sql.gz" 2>/dev/null | grep -q "$MARQUEUR"; then
  ok T9.1 "le marqueur est présent dans la partie lisible (test non vacant)"
else
  ko T9.1 "marqueur absent de la partie lisible — test non concluant"
fi

: > "$TMP/gzip.calls"
execute_kit "$TMP/t9.log" MODE=local \
  S1_DUMP="${H5_DUMP_FIXTURE:-$TMP/absent.dump}" S2_GZ="$TMP/corrompu.sql.gz" \
  S3_SQL_A="$TMP/a.sql" S3_SQL_B="$TMP/b.sql"
_code=$?

_decompressions=$(grep -c -- '-dc' "$TMP/gzip.calls" 2>/dev/null || true)
_tests=$(grep -c -- '-t ' "$TMP/gzip.calls" 2>/dev/null || true)
verifie T9.2 "aucune décompression de l'archive corrompue (0 attendu, obtenu ${_decompressions:-?})" \
  test "${_decompressions:-1}" = "0"
verifie T9.3 "exactement 1 contrôle d'intégrité (obtenu ${_tests:-?})" test "${_tests:-0}" = "1"
verifie T9.4 "le marqueur n'apparaît nulle part dans le journal" \
  test "$(grep -c "$MARQUEUR" "$TMP/t9.log" 2>/dev/null || true)" = "0"
verifie T9.5 "colonne « gzip » de la matrice entièrement à 0" \
  test "$(awk '/OBJET ATTENDU/{f=1;next} /5\.2 Indices/{f=0} f && NF==5 && $3!=0' "$TMP/t9.log" | wc -l | tr -d ' ')" = "0"
verifie T9.6 "section 3 : analyse explicitement ignorée" grep -q 'ANALYSE IGNORÉE' "$TMP/t9.log"
verifie T9.7 "taille décompressée non publiée"           grep -q 'NON MESURABLE' "$TMP/t9.log"
verifie T9.8 "5.2 : archive illisible non analysée"      grep -q 'archive illisible — non analysée' "$TMP/t9.log"
verifie T9.9 "statut conservé s2_gzip=corrompue"         grep -q '^s2_gzip=corrompue' "$TMP/t9.log"
verifie T9.10 "code de retour 0 malgré l'archive corrompue" test "$_code" = "0"

# 9.11 contrôle de non-vacuité du compteur : sur un gzip sain, -dc DOIT être appelé
: > "$TMP/gzip.calls"
execute_kit "$TMP/t9nominal.log" MODE=local \
  S1_DUMP="${H5_DUMP_FIXTURE:-$TMP/absent.dump}" S2_GZ="$TMP/sain.sql.gz" \
  S3_SQL_A="$TMP/a.sql" S3_SQL_B="$TMP/b.sql"
_decompressions_saines=$(grep -c -- '-dc' "$TMP/gzip.calls" 2>/dev/null || true)
verifie T9.11 "le compteur détecte bien les lectures quand l'archive est saine (${_decompressions_saines:-0} appels)" \
  test "${_decompressions_saines:-0}" -gt 0

# =====================================================================
echo
echo "====================================================================="
printf ' BILAN : %d PASS, %d FAIL, %d SKIP\n' "$PASS" "$FAIL" "$SKIP"
if [ "$FAIL" -eq 0 ]; then
  echo " AUCUNE ANALYSE PARTIELLE D'ARCHIVE CORROMPUE — INTÉGRITÉ TECHNIQUE ET CONFORMITÉ MÉTIER DISTINGUÉES"
  echo "====================================================================="
  exit 0
else
  echo " ÉCHEC : au moins une garantie du kit n'est pas tenue"
  echo "====================================================================="
  exit 1
fi
