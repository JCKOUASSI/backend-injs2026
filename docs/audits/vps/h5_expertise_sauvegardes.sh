#!/bin/sh
# =====================================================================
# H5 — EXPERTISE DES SAUVEGARDES (LECTURE SEULE EXCLUSIVE)
#
# Ce script n'exécute JAMAIS de restauration :
#   - pg_restore n'est utilisé QU'AVEC --list (inventaire du sommaire)
#   - aucune création de base, aucun DROP/CREATE/ALTER/DELETE/INSERT/UPDATE
#   - les archives ne sont jamais modifiées : seules des lectures (cat,
#     gzip -dc, sha256sum, ls) et des analyses en tube sont effectuées
#   - aucune donnée nominative n'est affichée : uniquement des nombres,
#     des noms de tables et des types d'objets
#   - aucun mot de passe, jeton ou hash n'est affiché
#
# MODES :
#   MODE=docker (défaut) : interroge pg_restore/psql du conteneur injs-db
#   MODE=local           : utilise pg_restore/psql du PATH (tests, poste local)
#
# Usage :
#   sh h5_expertise_sauvegardes.sh
#   MODE=local S1_DUMP=... S2_GZ=... sh h5_expertise_sauvegardes.sh
# =====================================================================
set -u

MODE="${MODE:-docker}"
PG_CONTAINER="${PG_CONTAINER:-injs-db}"
S1_DUMP="${S1_DUMP:-/home/almalinux/injs-db-backups/injs_lmd_20261026-133624.dump}"
S2_GZ="${S2_GZ:-/home/almalinux/injs-predeploy-20261026-124700/postgres-all.sql.gz}"
S3_SQL_A="${S3_SQL_A:-/home/almalinux/backups/injs-lmd/postgres-20261023-025115.sql}"
S3_SQL_B="${S3_SQL_B:-/home/almalinux/backup_injs_production_20261023_170117.sql}"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/h5.XXXXXX") || exit 2
trap 'rm -rf "$TMP"' EXIT INT TERM

titre() { printf '\n\n========== %s ==========\n' "$1"; }
sous()  { printf '\n--- %s ---\n' "$1"; }

# --- outils SQL : via conteneur (défaut) ou binaires locaux ------------
sql_tool() {   # $@ = commande + args, sans stdin
  if [ "$MODE" = "docker" ]; then
    docker exec "$PG_CONTAINER" "$@"
  else
    "$@"
  fi
}
sql_tool_stdin() {  # $@ = commande + args, stdin transmis
  if [ "$MODE" = "docker" ]; then
    docker exec -i "$PG_CONTAINER" "$@"
  else
    "$@"
  fi
}

# --- analyse d'un flux SQL texte (sans extraction disque) -------------
# $1 = fichier (ou - pour stdin)
flux() { case "$1" in *.gz) gzip -dc "$1" 2>/dev/null ;; *) cat "$1" ;; esac; }

compte() {  # $1=fichier  $2=motif grep étendu  -> nombre de lignes
  flux "$1" | grep -cE "$2" 2>/dev/null || true
}

tables_du_flux() {  # noms de tables (CREATE TABLE ...), triés, dédoublonnés
  flux "$1" \
    | grep -E '^CREATE TABLE ' \
    | sed -E \
        -e 's/^CREATE TABLE (IF NOT EXISTS )?//' \
        -e 's/ \([^)]*$/ /' \
        -e 's/;.*//' \
        -e 's/^"//' -e 's/"//g' \
    | awk '{print $1}' | sort -u
}

# nombre de lignes d'un bloc COPY pour une table donnée
lignes_copy() {  # $1=fichier  $2=table
  flux "$1" | awk -v t="$2" '
    $0 ~ ("^COPY [\"a-z0-9_.]*" t "[ (\"]") {enc=1; next}
    enc==1 && $0 == "\\." {enc=0; next}
    enc==1 {n++}
    END {print n+0}'
}

# =====================================================================
echo "H5 — expertise des sauvegardes (lecture seule)"
echo "hôte      : $(hostname 2>/dev/null)"
echo "date UTC  : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "mode      : $MODE (conteneur: $PG_CONTAINER)"

# =====================================================================
titre "ÉTAPE 1 — DISPONIBILITÉ DES OUTILS"
# =====================================================================
sous "1.1 pg_restore et psql (côté $MODE)"
sql_tool pg_restore --version 2>&1 | sed 's/^/  /' || echo "  ÉCHEC : pg_restore indisponible"
sql_tool psql --version 2>&1 | sed 's/^/  /' || echo "  ÉCHEC : psql indisponible"
sous "1.2 Outils hôte"
for outil in gzip awk grep sha256sum sort comm; do
  if command -v "$outil" >/dev/null 2>&1; then
    printf '  %-10s présent (%s)\n' "$outil" "$(command -v "$outil")"
  else
    printf '  %-10s ABSENT\n' "$outil"
  fi
done
gzip --version 2>/dev/null | head -1 | sed 's/^/  /'

# =====================================================================
titre "ÉTAPE 2 — ARCHIVE CUSTOM : $S1_DUMP"
# =====================================================================
if [ -f "$S1_DUMP" ]; then
  sous "2.1 Fiche du fichier"
  ls -l "$S1_DUMP" | sed 's/^/  /'
  printf '  sha256 : %s\n' "$(sha256sum "$S1_DUMP" | cut -d' ' -f1)"
  command -v file >/dev/null 2>&1 && file -b "$S1_DUMP" | sed 's/^/  type   : /'

  sous "2.2 Sommaire (pg_restore --list, SANS restauration)"
  if cat "$S1_DUMP" | sql_tool_stdin pg_restore --list > "$TMP/s1.list" 2>"$TMP/s1.err"; then
    echo "  lecture du sommaire : OK"
  else
    echo "  ÉCHEC de lecture du sommaire :"; sed 's/^/    /' "$TMP/s1.err"
  fi

  if [ -s "$TMP/s1.list" ]; then
    # Sommaire normalisé : on retire l'en-tête « ; » et le préfixe « id; oid oid »
    grep -v '^;' "$TMP/s1.list" | sed -E 's/^[0-9]+; [0-9]+ [0-9]+ //' > "$TMP/s1.norm"

    sous "2.3 En-tête d'archive"
    grep -E '^;.*(Format|Dump Version|Dumped from database version|Dumped by pg_dump version|Archive created|TOC Entries|Compression)' \
      "$TMP/s1.list" | sed 's/^; */  /'

    printf '  objets listés : %s\n' "$(wc -l < "$TMP/s1.norm" | tr -d ' ')"

    sous "2.4 Répartition par type d'objet"
    awk '{t=$1; if ($2=="DATA" || $2=="BLOB" || $2=="ATTACH" || $2=="CONSTRAINT") t=t" "$2; print t}' "$TMP/s1.norm" \
      | sort | uniq -c | sort -rn | sed 's/^/  /'

    sous "2.5 Schémas présents"
    awk '$1=="SCHEMA" {print $(NF-1)}' "$TMP/s1.norm" | sort -u | sed 's/^/  /'

    sous "2.6 Tables (noms uniquement)"
    awk '$1=="TABLE" && $2!="DATA" {print $(NF-2)"."$(NF-1)}' "$TMP/s1.norm" | sort -u > "$TMP/s1.tables"
    printf '  nombre de tables : %s\n' "$(wc -l < "$TMP/s1.tables" | tr -d ' ')"
    head -40 "$TMP/s1.tables" | sed 's/^/    /'
    [ "$(wc -l < "$TMP/s1.tables")" -gt 40 ] && echo "    … (liste tronquée à 40)"

    sous "2.7 Séquences, index, contraintes"
    printf '  %-16s : %s\n' "SEQUENCE" "$(awk '$1=="SEQUENCE"{c++} END{print c+0}' "$TMP/s1.norm")"
    printf '  %-16s : %s\n' "INDEX" "$(awk '$1=="INDEX"{c++} END{print c+0}' "$TMP/s1.norm")"
    printf '  %-16s : %s\n' "CONSTRAINT" "$(awk '$1=="CONSTRAINT"{c++} END{print c+0}' "$TMP/s1.norm")"
    printf '  %-16s : %s\n' "FK CONSTRAINT" "$(awk '$1=="FK" && $2=="CONSTRAINT"{c++} END{print c+0}' "$TMP/s1.norm")"
    printf '  %-16s : %s\n' "DEFAULT" "$(awk '$1=="DEFAULT"{c++} END{print c+0}' "$TMP/s1.norm")"

    sous "2.8 Django, utilisateurs et habilitations (présence d'objets)"
    for motif in django_migrations authentication_user auth_permission auth_group habilitations_ presences_ edts_ scolarite_ referentiels_ formations_; do
      n=$(grep -cE "$motif" "$TMP/s1.tables" 2>/dev/null || true)
      printf '  %-22s objet(s) table : %s\n' "$motif" "${n:-0}"
    done
  fi
else
  echo "  FICHIER ABSENT : $S1_DUMP"
fi

# =====================================================================
titre "ÉTAPE 3 — ARCHIVE GZIP : $S2_GZ"
# =====================================================================
if [ -f "$S2_GZ" ]; then
  sous "3.1 Fiche et intégrité"
  ls -l "$S2_GZ" | sed 's/^/  /'
  printf '  sha256 : %s\n' "$(sha256sum "$S2_GZ" | cut -d' ' -f1)"
  if gzip -t "$S2_GZ" 2>"$TMP/gz.err"; then
    echo "  intégrité gzip : OK (gzip -t)"; GZ_OK=1
  else
    echo "  intégrité gzip : ÉCHEC — fichier corrompu ou tronqué"; sed 's/^/    /' "$TMP/gz.err"; GZ_OK=0
  fi
  if [ "${GZ_OK:-0}" = "1" ]; then
    printf '  taille décompressée : %s octets\n' "$(flux "$S2_GZ" | wc -c | tr -d ' ')"
  else
    echo "  taille décompressée : NON MESURABLE — archive illisible, aucune valeur partielle n'est publiée"
  fi

  if [ "${GZ_OK:-0}" = "1" ]; then
  sous "3.2 Nature du contenu (pg_dump ? dumpall ?)"
  flux "$S2_GZ" | head -40 | grep -E '^--|^\\connect|^SET ' | head -8 | sed 's/^/  /'
  for motif in '^CREATE DATABASE' '^\\connect' '^CREATE ROLE' '^CREATE SCHEMA' '^CREATE TABLE' '^CREATE SEQUENCE' \
               '^COPY ' '^INSERT INTO' '^ALTER TABLE' '^GRANT ' '^CREATE INDEX' '^CREATE EXTENSION'; do
    printf '  %-20s : %s\n' "$motif" "$(compte "$S2_GZ" "$motif")"
  done

  sous "3.3 Bases et schémas"
  flux "$S2_GZ" | grep -E '^CREATE DATABASE|^\\connect' | sed -E 's/ (OWNER|TEMPLATE|ENCODING|LC_[A-Z]+|WITH).*//' | sort -u | head -20 | sed 's/^/  /'
  flux "$S2_GZ" | grep -E '^CREATE SCHEMA' | sed -E 's/^CREATE SCHEMA //; s/;.*//' | sort -u | head -20 | sed 's/^/  /'

  sous "3.4 Tables (noms uniquement)"
  tables_du_flux "$S2_GZ" > "$TMP/s2.tables"
  printf '  nombre de tables : %s\n' "$(wc -l < "$TMP/s2.tables" | tr -d ' ')"
  head -30 "$TMP/s2.tables" | sed 's/^/    /'
  [ "$(wc -l < "$TMP/s2.tables")" -gt 30 ] && echo "    … (liste tronquée à 30)"

  sous "3.5 Migrations et volumes"
  printf '  table django_migrations présente : %s\n' "$(grep -cx 'django_migrations\|public.django_migrations' "$TMP/s2.tables" 2>/dev/null || echo 0)"
  printf '  lignes django_migrations (COPY)   : %s\n' "$(lignes_copy "$S2_GZ" django_migrations)"
  printf '  lignes authentication_user (COPY) : %s\n' "$(lignes_copy "$S2_GZ" authentication_user)"
  printf '  lignes formations_participant      : %s\n' "$(lignes_copy "$S2_GZ" formations_participant)"

  sous "3.6 Erreurs visibles dans le flux"
  printf '  lignes contenant ERROR/FATAL : %s\n' "$(compte "$S2_GZ" '^(ERROR|FATAL):')"
  printf '  avertissements pg_dump       : %s\n' "$(compte "$S2_GZ" '^pg_dump: (warning|WARNING)')"
  else
    echo "  ANALYSE IGNORÉE : archive gzip illisible — aucune conclusion n'en est tirée"
  fi
else
  echo "  FICHIER ABSENT : $S2_GZ"
fi

# =====================================================================
titre "ÉTAPE 4 — COMPARAISON DES DEUX SAUVEGARDES SQL"
# =====================================================================
for f in "$S3_SQL_A" "$S3_SQL_B"; do
  sous "4.x Fiche : $f"
  if [ -f "$f" ]; then
    ls -l "$f" | sed 's/^/  /'
    printf '  sha256       : %s\n' "$(sha256sum "$f" | cut -d' ' -f1)"
    printf '  tables       : %s\n' "$(tables_du_flux "$f" | wc -l | tr -d ' ')"
    printf '  sections COPY: %s\n' "$(compte "$f" '^COPY ')"
    printf '  INSERT       : %s\n' "$(compte "$f" '^INSERT INTO')"
    printf '  migrations   : %s\n' "$(lignes_copy "$f" django_migrations)"
    printf '  lignes auth_user : %s\n' "$(lignes_copy "$f" authentication_user)"
    printf '  GRANT/REVOKE : %s / %s\n' "$(compte "$f" '^GRANT ')" "$(compte "$f" '^REVOKE ')"
    tables_du_flux "$f" > "$TMP/$(basename "$f").tables"
  else
    echo "  FICHIER ABSENT"
  fi
done

A="$TMP/$(basename "$S3_SQL_A").tables"
B="$TMP/$(basename "$S3_SQL_B").tables"
if [ -s "$A" ] && [ -s "$B" ]; then
  sous "4.3 Comparaison des structures (noms de tables)"
  comm -12 "$A" "$B" > "$TMP/communes"
  comm -23 "$A" "$B" > "$TMP/seulement_a"
  comm -13 "$A" "$B" > "$TMP/seulement_b"
  printf '  tables communes        : %s\n' "$(wc -l < "$TMP/communes" | tr -d ' ')"
  printf '  seulement dans A       : %s\n' "$(wc -l < "$TMP/seulement_a" | tr -d ' ')"
  printf '  seulement dans B       : %s\n' "$(wc -l < "$TMP/seulement_b" | tr -d ' ')"
  printf '  tables seulement dans A :\n'; head -20 "$TMP/seulement_a" | sed 's/^/    /'
  printf '  tables seulement dans B :\n'; head -20 "$TMP/seulement_b" | sed 's/^/    /'
fi

# =====================================================================
titre "ÉTAPE 5 — INDICES DE CONFORMITÉ INJS 2026"
# =====================================================================
# Présence des objets structurants dans chaque source. Aucune valeur métier
# n'est affichée ; seul le nombre d'objets correspondants est indiqué.
if [ -f "$S1_DUMP" ] && [ -s "$TMP/s1.tables" ]; then cp "$TMP/s1.tables" "$TMP/t_s1"; else : > "$TMP/t_s1"; fi
if [ -f "$S2_GZ" ] && [ "${GZ_OK:-0}" = "1" ]; then
  if [ -s "$TMP/s2.tables" ]; then cp "$TMP/s2.tables" "$TMP/t_s2"; else tables_du_flux "$S2_GZ" > "$TMP/t_s2"; fi
else
  : > "$TMP/t_s2"
  [ -f "$S2_GZ" ] && echo "  [gzip] archive illisible : colonne « gzip » volontairement vide, aucune lecture de l'archive"
fi
[ -f "$A" ] && cp "$A" "$TMP/t_s3a" || : > "$TMP/t_s3a"
[ -f "$B" ] && cp "$B" "$TMP/t_s3b" || : > "$TMP/t_s3b"

printf '\n%-34s %8s %8s %8s %8s\n' "OBJET ATTENDU (INJS 2026)" "custom" "gzip" "sql A" "sql B"
printf '%s\n' "---------------------------------------------------------------------"
for objet in \
  'referentiels_reffiliere:filières et codes dossier' \
  'scolarite_semestre:semestres S1 à S10' \
  'scolarite_ue:unités d'"'"'enseignement' \
  'scolarite_ecue:ECUE' \
  'scolarite_inscriptionadministrative:inscriptions administratives' \
  'scolarite_inscriptionpedagogique:inscriptions pédagogiques' \
  'jurys_decisionjury:décisions de jury' \
  'edts_emploidutemps:emplois du temps' \
  'edts_affectationcreneau:créneaux affectés' \
  'presences_pointage:pointages de présence' \
  'habilitations_rolemetier:habilitations / rôles' \
  'formations_participant:étudiants (participants)' \
  'academics_:socle hérité (academics)' \
  'students_:socle hérité (students)' \
  'faculty_:socle hérité (faculty)' ; do
  motif=${objet%%:*}
  c1=$(grep -c "$motif" "$TMP/t_s1" 2>/dev/null || true)
  c2=$(grep -c "$motif" "$TMP/t_s2" 2>/dev/null || true)
  c3=$(grep -c "$motif" "$TMP/t_s3a" 2>/dev/null || true)
  c4=$(grep -c "$motif" "$TMP/t_s3b" 2>/dev/null || true)
  printf '%-34s %8s %8s %8s %8s\n' "$motif" "${c1:-0}" "${c2:-0}" "${c3:-0}" "${c4:-0}"
done

sous "5.2 Indices de valeurs (comptage uniquement, aucune donnée affichée)"
for src in "$S1_DUMP" "$S2_GZ" "$S3_SQL_A" "$S3_SQL_B"; do
  [ -f "$src" ] || continue
  case "$src" in
    *.dump) printf '  %-46s : archive custom (valeurs non inspectées par ce script)\n' "$(basename "$src")"; continue ;;
  esac
  if [ "$src" = "$S2_GZ" ] && [ "${GZ_OK:-0}" != "1" ]; then
    printf '  %-46s : archive illisible — non analysée (aucune valeur partielle)\n' "$(basename "$src")"
    continue
  fi
  printf '  %-46s : ENSEP=%s  S1..S10=%s  ECTS=%s\n' "$(basename "$src")" \
    "$(compte "$src" 'ENSEP')" \
    "$(compte "$src" '\bS([1-9]|10)\b')" \
    "$(compte "$src" 'ECTS')"
done

# =====================================================================
titre "SYNTHÈSE H5"
# =====================================================================
echo "SYNTHESE_H5_BEGIN"
echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "mode=$MODE"
if [ -f "$S1_DUMP" ] && [ -s "$TMP/s1.list" ]; then
  echo "s1_custom=lue objets=$(grep -vc '^;' "$TMP/s1.list") tables=$(wc -l < "$TMP/s1.tables" | tr -d ' ')"
else echo "s1_custom=non_lue"; fi
if [ -f "$S2_GZ" ]; then
  if [ "${GZ_OK:-0}" = "1" ]; then
    echo "s2_gzip=lue tables=$(wc -l < "$TMP/t_s2" | tr -d ' ') copies=$(compte "$S2_GZ" '^COPY ')"
  else
    echo "s2_gzip=corrompue"
  fi
else echo "s2_gzip=non_lue"; fi
[ -f "$S3_SQL_A" ] && echo "s3a=lue tables=$(wc -l < "$TMP/t_s3a" | tr -d ' ')" || echo "s3a=non_lue"
[ -f "$S3_SQL_B" ] && echo "s3b=lue tables=$(wc -l < "$TMP/t_s3b" | tr -d ' ')" || echo "s3b=non_lue"
echo "SYNTHESE_H5_END"
echo
echo "AUCUNE RESTAURATION — AUCUNE MODIFICATION — LECTURE SEULE"
