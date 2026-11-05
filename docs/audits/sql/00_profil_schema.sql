-- =====================================================================
-- AUDIT COMPARATIF INJS — ÉTAPE 1 : PROFIL DE SCHÉMA ET VOLUMES
-- Cible : PostgreSQL 15 du VPS (base injectée par -v ? non nécessaire)
-- Lecture seule garantie : la transaction est ouverte en READ ONLY,
-- toute écriture échouerait, et la transaction est annulée à la fin.
-- Aucune donnée nominative n'est affichée : uniquement des compteurs.
-- Usage : psql -f 00_profil_schema.sql  (à exécuter une fois par base)
-- =====================================================================
\timing off
\pset pager off
SET default_transaction_read_only = on;
BEGIN TRANSACTION READ ONLY;

\echo '===== 1. CONTEXTE ====='
SELECT current_database()                                   AS base,
       current_setting('server_version')                     AS version_pg,
       pg_size_pretty(pg_database_size(current_database()))  AS taille,
       (SELECT count(*) FROM pg_stat_activity
         WHERE datname = current_database())                 AS connexions_actives;

\echo '===== 2. VOLUME PAR SCHÉMA ====='
SELECT n.nspname                                    AS schema,
       count(*) FILTER (WHERE c.relkind IN ('r','p')) AS nb_tables,
       count(*) FILTER (WHERE c.relkind = 'v')        AS nb_vues,
       count(*) FILTER (WHERE c.relkind = 'S')        AS nb_sequences
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
GROUP BY 1 ORDER BY 2 DESC;

\echo '===== 3. TABLES (nom, type, estimation de lignes) ====='
SELECT n.nspname                        AS schema,
       c.relname                        AS table,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'partitionnee' ELSE c.relkind::text END AS genre,
       c.reltuples::bigint              AS lignes_estimees
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
ORDER BY 1, 2;

\echo '===== 4. COMPTAGE EXACT (toutes les tables, lecture seule) ====='
SELECT format('SELECT %L AS table, count(*) AS lignes FROM %I.%I;',
              n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
ORDER BY 1
\gexec

\echo '===== 5. COLONNES (nom, type, nullabilité, défaut) ====='
SELECT table_schema  AS schema,
       table_name    AS table,
       ordinal_position AS pos,
       column_name   AS colonne,
       data_type || coalesce('(' || character_maximum_length || ')', '') AS type,
       is_nullable   AS nullable,
       coalesce(column_default, '')  AS defaut
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog','information_schema')
ORDER BY 1, 2, 3;

\echo '===== 6. CLES PRIMAIRES ET UNICITE ====='
SELECT tc.table_schema AS schema,
       tc.table_name   AS table,
       tc.constraint_type AS type,
       tc.constraint_name AS contrainte,
       string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS colonnes
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = tc.constraint_name
 AND kcu.table_schema = tc.table_schema
WHERE tc.constraint_type IN ('PRIMARY KEY','UNIQUE')
  AND tc.table_schema NOT IN ('pg_catalog','information_schema')
GROUP BY 1,2,3,4
ORDER BY 1,2,3;

\echo '===== 7. CLES ETRANGERES (graphe de dependances) ====='
SELECT ns.nspname  AS schema_enfant,
       cl.relname  AS table_enfant,
       a.attname   AS colonne_enfant,
       pn.nspname  AS schema_parent,
       pcl.relname AS table_parent,
       pa.attname  AS colonne_parent,
       c.confdeltype AS on_delete
FROM pg_constraint c
JOIN pg_class cl   ON cl.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = cl.relnamespace
JOIN pg_class pcl  ON pcl.oid = c.confrelid
JOIN pg_namespace pn ON pn.oid = pcl.relnamespace
JOIN pg_attribute a  ON a.attrelid = c.conrelid  AND a.attnum = ANY (c.conkey)
JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = ANY (c.conkey)
WHERE c.contype = 'f'
  AND array_length(c.conkey, 1) = 1
  AND ns.nspname NOT IN ('pg_catalog','information_schema')
ORDER BY 1,2,3;

\echo '===== 8. CONTRAINTES CHECK (regles metier encodees en base) ====='
SELECT ns.nspname AS schema, cl.relname AS table, c.conname AS contrainte,
       pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
JOIN pg_class cl ON cl.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = cl.relnamespace
WHERE c.contype = 'c'
  AND ns.nspname NOT IN ('pg_catalog','information_schema')
ORDER BY 1,2,3;

\echo '===== 9. INDEX ====='
SELECT schemaname AS schema, tablename AS table, indexname AS index, indexdef AS definition
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog','information_schema')
ORDER BY 1,2,3;

\echo '===== 10. HISTORIQUE DES MIGRATIONS DJANGO ====='
SELECT to_regclass('public.django_migrations') IS NOT NULL AS table_migrations_presente;

SELECT app, count(*) AS nb_migrations,
       min(applied) AS premiere, max(applied) AS derniere
FROM django_migrations
GROUP BY app ORDER BY app;

\echo '===== 11. TABLES SANS CLE PRIMAIRE (anomalie structurelle) ====='
SELECT n.nspname AS schema, c.relname AS table
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND NOT EXISTS (SELECT 1 FROM pg_constraint p
                  WHERE p.conrelid = c.oid AND p.contype = 'p')
ORDER BY 1,2;

\echo '===== 12. SEQUENCES EN DEPASSEMENT (risque sur les PK BigAuto) ====='
SELECT schemaname AS schema, sequencename AS sequence,
       last_value AS prochaine_valeur
FROM pg_sequences
WHERE schemaname NOT IN ('pg_catalog','information_schema')
ORDER BY 1,2;

ROLLBACK;
\echo '=== TRANSACTION ANNULEE — AUCUNE ECRITURE EFFECTUEE ==='
