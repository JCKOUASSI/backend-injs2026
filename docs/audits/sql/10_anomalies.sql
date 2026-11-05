-- =====================================================================
-- AUDIT COMPARATIF INJS — ÉTAPE 2 : ANOMALIES (INTÉGRITÉ RÉFÉRENTIELLE)
-- Lecture seule garantie (transaction READ ONLY annulée à la fin).
-- Aucune donnée nominative : uniquement des COMPTEURS par contrainte.
-- Usage : psql -f 10_anomalies.sql  (une fois par base)
--
-- LIMITE MÉTHODOLOGIQUE À GARDER EN TÊTE :
-- une FK déclarée et VALIDÉE empêche physiquement l'orphelin : la détection
-- ci-dessous ne remonte donc que les anomalies autorisées par des FK
-- ajoutées en NOT VALID, ou des colonnes de liaison sans contrainte
-- (cas fréquent dans les anciennes bases). Les orphelins « métier »
-- (ex. inscription sans année) se mesurent en plus par jointures explicites,
-- listées en section F.
-- =====================================================================
\pset pager off
SET default_transaction_read_only = on;
BEGIN TRANSACTION READ ONLY;

\echo '===== A. INTEGRITE PHYSIQUE DES CONTRAINTES ====='
-- 0 = toutes les FK sont validées par PostgreSQL ; > 0 = anomalie à examiner.
SELECT conrelid::regclass AS table,
       conname           AS contrainte,
       convalidated      AS validee
FROM pg_constraint
WHERE contype = 'f' AND NOT convalidated
ORDER BY 1, 2;

\echo '===== B. REFERENCES ORPHELINES — detection generique sur toutes les FK ====='
WITH fk AS (
  SELECT c.conname         AS conname,
         ns.nspname        AS child_schema,
         cl.relname        AS child_tbl,
         a.attname         AS child_col,
         pn.nspname        AS parent_schema,
         pcl.relname       AS parent_tbl,
         pa.attname        AS parent_col
  FROM pg_constraint c
  JOIN pg_class cl     ON cl.oid = c.conrelid
  JOIN pg_namespace ns ON ns.oid = cl.relnamespace
  JOIN pg_class pcl    ON pcl.oid = c.confrelid
  JOIN pg_namespace pn ON pn.oid = pcl.relnamespace
  JOIN pg_attribute a  ON a.attrelid = c.conrelid  AND a.attnum = c.conkey[1]
  JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = c.confkey[1]
  WHERE c.contype = 'f'
    AND array_length(c.conkey, 1) = 1
    AND ns.nspname NOT IN ('pg_catalog','information_schema')
)
SELECT format(
  'SELECT %L AS contrainte, count(*) AS orphelins FROM %I.%I ch WHERE ch.%I IS NOT NULL AND NOT EXISTS (SELECT 1 FROM %I.%I pa WHERE pa.%I = ch.%I) HAVING count(*) > 0;',
  conname, child_schema, child_tbl, child_col, parent_schema, parent_tbl, parent_col, child_col)
FROM fk
ORDER BY conname
\gexec

\echo '===== C. COLONNES TEXTE NOT NULL VIDES ====='
WITH t AS (
  SELECT c.oid, n.nspname, c.relname
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
)
SELECT format('SELECT %L AS table, %L AS colonne, count(*) AS vides FROM %I.%I WHERE %I = %L HAVING count(*) > 0;',
              t.relname, a.attname, t.nspname, t.relname, a.attname, '')
FROM t
JOIN pg_attribute a ON a.attrelid = t.oid
JOIN pg_type ty ON ty.oid = a.atttypid
WHERE a.attnum > 0 AND NOT a.attisdropped AND ty.typname IN ('varchar','text','bpchar')
ORDER BY t.relname, a.attname
\gexec

\echo '===== D. DATES INCOHERENTES (modification anterieure a la creation) ====='
WITH pairs AS (
  SELECT n.nspname,
         c.relname,
         max(CASE WHEN a.attname = 'created_at' THEN a.attname
                  WHEN a.attname = 'cree_le'   THEN a.attname END) AS col_cree,
         max(CASE WHEN a.attname = 'updated_at' THEN a.attname
                  WHEN a.attname = 'modifie_le' THEN a.attname END) AS col_maj
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
  WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
    AND a.attname IN ('created_at','cree_le','updated_at','modifie_le')
  GROUP BY 1, 2
)
SELECT format('SELECT %L AS table, count(*) AS maj_avant_creation FROM %I.%I WHERE %I > %I HAVING count(*) > 0;',
              relname, nspname, relname, col_maj, col_cree)
FROM pairs
WHERE col_cree IS NOT NULL AND col_maj IS NOT NULL
ORDER BY 1
\gexec

\echo '===== E. DOUBLONS SUR CLES NATURELLES (matricule, code, numero) ====='
WITH nat AS (
  SELECT n.nspname, c.relname, a.attname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
  WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
    AND a.attname IN ('matricule','code','numero')
)
SELECT format('SELECT %L AS table, %L AS cle, count(*) AS groupes_doublons, coalesce(sum(n),0) AS lignes_en_cause FROM (SELECT %I, count(*) n FROM %I.%I WHERE %I IS NOT NULL GROUP BY %I HAVING count(*) > 1) s;',
              relname, attname, attname, nspname, relname, attname, attname)
FROM nat
ORDER BY 1
\gexec

\echo '===== F. ORPHELINS METIER SUR LA BASE CIBLE ====='
-- Exécuté uniquement si les tables cibles existent ; sans effet sinon.
DO $$
DECLARE
  v bigint;
  cible boolean := to_regclass('public.scolarite_dossieretudiant') IS NOT NULL;
BEGIN
  IF NOT cible THEN
    RAISE NOTICE 'base sans tables cible LMD — section F ignorée';
    RETURN;
  END IF;

  EXECUTE 'SELECT count(*) FROM scolarite_dossieretudiant d
            WHERE NOT EXISTS (SELECT 1 FROM scolarite_inscriptionadministrative i
                               WHERE i.etudiant_id = d.id)' INTO v;
  RAISE NOTICE 'etudiants sans inscription administrative : %', v;

  EXECUTE 'SELECT count(*) FROM scolarite_inscriptionadministrative
            WHERE admission_id IS NULL' INTO v;
  RAISE NOTICE 'inscriptions sans admission rattachee : %', v;

  EXECUTE 'SELECT count(*) FROM scolarite_inscriptionpedagogique
            WHERE inscription_id IS NULL OR ecue_id IS NULL' INTO v;
  RAISE NOTICE 'inscriptions pedagogiques incompletes : %', v;

  EXECUTE 'SELECT count(*) FROM presences_pointage
            WHERE session_id IS NULL AND seance_edt_id IS NULL' INTO v;
  RAISE NOTICE 'pointages sans support pedagogique : %', v;

  EXECUTE 'SELECT count(*) FROM evaluations_evaluationparticipant ep
            WHERE NOT EXISTS (SELECT 1 FROM scolarite_inscriptionpedagogique ip
                               WHERE ip.id = ep.inscription_pedagogique_id)' INTO v;
  RAISE NOTICE 'participants evaluation hors inscription pedagogique : %', v;

  EXECUTE 'SELECT count(*) FROM scolarite_ue WHERE semestre_id IS NULL' INTO v;
  RAISE NOTICE 'UE sans semestre : %', v;

  EXECUTE 'SELECT count(*) FROM scolarite_ecue WHERE ue_id IS NULL' INTO v;
  RAISE NOTICE 'ECUE sans UE : %', v;
END $$;

\echo '===== G. COMPTES : REPARTITION PAR ROLE (compteurs uniquement) ====='
DO $$
DECLARE
  t text;
  v bigint;
BEGIN
  SELECT c.table_name INTO t
  FROM information_schema.columns c
  WHERE c.column_name = 'role'
    AND c.table_name IN ('accounts_user','authentication_user')
  LIMIT 1;

  IF t IS NULL THEN
    RAISE NOTICE 'table de comptes non identifiee — section G ignoree';
    RETURN;
  END IF;

  EXECUTE format('SELECT count(*) FROM %I', t) INTO v;
  RAISE NOTICE 'comptes au total (%): %', t, v;

  EXECUTE format('SELECT count(*) FROM %I WHERE role IS NULL OR role = %L', t, '') INTO v;
  RAISE NOTICE 'comptes sans role renseigne : %', v;

  EXECUTE format('SELECT count(DISTINCT role) FROM %I', t) INTO v;
  RAISE NOTICE 'roles distincts (a mapper sur habilitations.RoleMetier) : %', v;

  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = t AND column_name = 'is_active') THEN
    EXECUTE format('SELECT count(*) FROM %I WHERE is_active = false', t) INTO v;
    RAISE NOTICE 'comptes desactives : %', v;
  END IF;
END $$;

\echo '===== H. MOTS DE PASSE : ALGORITHME SEULEMENT (aucun hash affiche) ====='
-- Repartition par prefixe d'algorithme Django (pbkdf2_sha256$..., argon2$...,
-- md5$..., sha1$...) : determine si les hashes sont reutilisables tels quels.
DO $$
DECLARE
  t text;
  r record;
BEGIN
  SELECT c.table_name INTO t
  FROM information_schema.columns c
  WHERE c.column_name = 'password'
    AND c.table_name IN ('accounts_user','authentication_user')
  LIMIT 1;

  IF t IS NULL THEN
    RAISE NOTICE 'table de comptes non identifiee — section H ignoree';
    RETURN;
  END IF;

  FOR r IN EXECUTE format(
      'SELECT split_part(password, %L, 1) AS algorithme, count(*) AS comptes
         FROM %I GROUP BY 1 ORDER BY 2 DESC', '$', t)
  LOOP
    RAISE NOTICE 'algorithme % : % compte(s)', r.algorithme, r.comptes;
  END LOOP;
END $$;

\echo '===== I. DISTRIBUTION DES CODES DE STATUT (valeurs courtes uniquement) ====='
-- Colonnes nommees statut/status/etat/type ET de longueur <= 32 : ce sont des
-- codes, jamais du texte libre. Sortie limitee aux 15 valeurs les plus frein.
-- Sert a reperer les « statuts non reconnus » exigés par l'audit metier.
WITH cols AS (
  SELECT n.nspname, c.relname, a.attname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
  JOIN information_schema.columns ic
    ON ic.table_schema = n.nspname AND ic.table_name = c.relname AND ic.column_name = a.attname
  WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
    AND a.attname IN ('statut','status','etat','type')
    AND coalesce(ic.character_maximum_length, 0) BETWEEN 1 AND 32
)
SELECT format('SELECT %L AS table, %L AS colonne, %I AS valeur, count(*) AS nb FROM %I.%I GROUP BY 3 ORDER BY 4 DESC LIMIT 15;',
              relname, attname, attname, nspname, relname)
FROM cols
ORDER BY 1
\gexec

ROLLBACK;
\echo '=== TRANSACTION ANNULEE — AUCUNE ECRITURE EFFECTUEE ==='
