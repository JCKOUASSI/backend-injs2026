-- =====================================================================
-- AUDIT INJS — EMPREINTE FONCTIONNELLE DES MODULES
--   GET INJS APP (emplois du temps, référentiels LMD, maquettes, séances)
--   PRÉSENCES QR  (sessions, pointages, géolocalisation, justificatifs, audit)
--
-- Objectif : déterminer quelle base PEUT porter ces deux modules.
-- Le volume de données n'est jamais un critère : seule la présence des
-- tables structurantes l'est, complétée par leur alimentation réelle.
--
-- Ce script ne fait AUCUN inventaire exhaustif : il se limite aux tables
-- structurantes listées ci-dessous.
--
-- Lecture seule garantie : transaction READ ONLY + ROLLBACK.
-- Aucune donnée nominative affichée : présence et compteurs uniquement.
-- =====================================================================
\pset pager off
SET default_transaction_read_only = on;
BEGIN TRANSACTION READ ONLY;

\echo '===== 1. APPLICATIONS RÉELLEMENT MIGRÉES DANS CETTE BASE ====='
DO $$
BEGIN
  IF to_regclass('public.django_migrations') IS NULL THEN
    RAISE NOTICE 'django_migrations absente : base non gérée par Django';
    RETURN;
  END IF;
END $$;

SELECT app, count(*) AS migrations, max(applied) AS derniere
FROM django_migrations
GROUP BY app
ORDER BY app;

\echo '===== 2. PRÉSENCE DES TABLES STRUCTURANTES (par module) ====='
WITH attendu(module, tbl) AS (
  VALUES
  -- ── GET INJS APP : emplois du temps, génération, simulation ─────────
  ('GET INJS APP','edts_emploidutemps'),
  ('GET INJS APP','edts_affectationcreneau'),
  ('GET INJS APP','edts_creneautemplate'),
  ('GET INJS APP','edts_campagnegeneration'),
  ('GET INJS APP','edts_executioncampagne'),
  ('GET INJS APP','edts_conflitcreneau'),
  ('GET INJS APP','edts_disponibilitehoraire'),
  ('GET INJS APP','edts_inscriptionimportee'),
  ('GET INJS APP','edts_politiquecontraintessouples'),
  -- ── GET INJS APP : référentiels LMD, maquettes, UE/ECUE, groupes ────
  ('GET INJS APP','referentiels_reffiliere'),
  ('GET INJS APP','scolarite_anneeacademique'),
  ('GET INJS APP','scolarite_niveau'),
  ('GET INJS APP','scolarite_semestre'),
  ('GET INJS APP','scolarite_parcours'),
  ('GET INJS APP','scolarite_maquette'),
  ('GET INJS APP','scolarite_ue'),
  ('GET INJS APP','scolarite_ecue'),
  ('GET INJS APP','scolarite_groupe'),
  ('GET INJS APP','scolarite_affectationpedagogique'),
  -- ── GET INJS APP : socle formations/salles/enseignants ──────────────
  ('GET INJS APP','formations_refformation'),
  ('GET INJS APP','formations_refsalle'),
  ('GET INJS APP','formations_refsite'),
  ('GET INJS APP','formations_formateur'),
  ('GET INJS APP','formations_refmodule'),
  -- ── PRÉSENCES QR : pointages, encadrement, appareils, audit ─────────
  ('PRÉSENCES QR','presences_pointage'),
  ('PRÉSENCES QR','presences_encadrantseance'),
  ('PRÉSENCES QR','presences_devicebinding'),
  ('PRÉSENCES QR','presences_auditlog'),
  ('PRÉSENCES QR','presences_rattrapage'),
  ('PRÉSENCES QR','presences_notificationabsence'),
  -- ── PRÉSENCES QR : QR, géolocalisation, registre de séance ──────────
  ('PRÉSENCES QR','formations_qrtoken'),
  ('PRÉSENCES QR','gi_salle_geolocalisation'),
  ('PRÉSENCES QR','gi_seance_registre'),
  ('PRÉSENCES QR','gi_seance_evenement'),
  ('PRÉSENCES QR','gi_seance_historique'),
  ('PRÉSENCES QR','gi_seance_instantane'),
  -- ── PRÉSENCES QR : rattachement pédagogique et étudiant ─────────────
  ('PRÉSENCES QR','edts_affectationcreneau'),
  ('PRÉSENCES QR','formations_participant'),
  ('PRÉSENCES QR','formations_sessionmodule'),
  ('PRÉSENCES QR','scolarite_dossieretudiant'),
  ('PRÉSENCES QR','scolarite_groupe'),
  ('PRÉSENCES QR','scolarite_ecue'),
  ('PRÉSENCES QR','scolarite_inscriptionpedagogique')
)
SELECT module,
       tbl AS table_attendue,
       CASE WHEN to_regclass('public.' || tbl) IS NULL THEN 'ABSENTE' ELSE 'présente' END AS etat
FROM attendu
ORDER BY module, tbl;

\echo '===== 3. SCORE PAR MODULE (tables structurantes présentes) ====='
WITH attendu(module, tbl) AS (
  VALUES
  ('GET INJS APP','edts_emploidutemps'),('GET INJS APP','edts_affectationcreneau'),
  ('GET INJS APP','edts_creneautemplate'),('GET INJS APP','edts_campagnegeneration'),
  ('GET INJS APP','edts_executioncampagne'),('GET INJS APP','edts_conflitcreneau'),
  ('GET INJS APP','edts_disponibilitehoraire'),('GET INJS APP','edts_inscriptionimportee'),
  ('GET INJS APP','edts_politiquecontraintessouples'),('GET INJS APP','referentiels_reffiliere'),
  ('GET INJS APP','scolarite_anneeacademique'),('GET INJS APP','scolarite_niveau'),
  ('GET INJS APP','scolarite_semestre'),('GET INJS APP','scolarite_parcours'),
  ('GET INJS APP','scolarite_maquette'),('GET INJS APP','scolarite_ue'),
  ('GET INJS APP','scolarite_ecue'),('GET INJS APP','scolarite_groupe'),
  ('GET INJS APP','scolarite_affectationpedagogique'),('GET INJS APP','formations_refformation'),
  ('GET INJS APP','formations_refsalle'),('GET INJS APP','formations_refsite'),
  ('GET INJS APP','formations_formateur'),('GET INJS APP','formations_refmodule'),
  ('PRÉSENCES QR','presences_pointage'),('PRÉSENCES QR','presences_encadrantseance'),
  ('PRÉSENCES QR','presences_devicebinding'),('PRÉSENCES QR','presences_auditlog'),
  ('PRÉSENCES QR','presences_rattrapage'),('PRÉSENCES QR','presences_notificationabsence'),
  ('PRÉSENCES QR','formations_qrtoken'),('PRÉSENCES QR','gi_salle_geolocalisation'),
  ('PRÉSENCES QR','gi_seance_registre'),('PRÉSENCES QR','gi_seance_evenement'),
  ('PRÉSENCES QR','gi_seance_historique'),('PRÉSENCES QR','gi_seance_instantane'),
  ('PRÉSENCES QR','edts_affectationcreneau'),('PRÉSENCES QR','formations_participant'),
  ('PRÉSENCES QR','formations_sessionmodule'),('PRÉSENCES QR','scolarite_dossieretudiant'),
  ('PRÉSENCES QR','scolarite_groupe'),('PRÉSENCES QR','scolarite_ecue'),
  ('PRÉSENCES QR','scolarite_inscriptionpedagogique')
)
SELECT module,
       count(*) FILTER (WHERE to_regclass('public.' || tbl) IS NOT NULL) AS presentes,
       count(*) AS attendues,
       round(100.0 * count(*) FILTER (WHERE to_regclass('public.' || tbl) IS NOT NULL) / count(*), 1) AS pct
FROM attendu
GROUP BY module
ORDER BY module;

\echo '===== 4. VOLUMES DES SEULES TABLES STRUCTURANTES PRÉSENTES ====='
WITH attendu(tbl) AS (
  VALUES ('edts_emploidutemps'),('edts_affectationcreneau'),('edts_creneautemplate'),
         ('edts_campagnegeneration'),('edts_executioncampagne'),('edts_conflitcreneau'),
         ('edts_disponibilitehoraire'),('edts_inscriptionimportee'),('edts_politiquecontraintessouples'),
         ('referentiels_reffiliere'),('scolarite_anneeacademique'),('scolarite_niveau'),
         ('scolarite_semestre'),('scolarite_parcours'),('scolarite_maquette'),
         ('scolarite_ue'),('scolarite_ecue'),('scolarite_groupe'),
         ('scolarite_affectationpedagogique'),('formations_refformation'),('formations_refsalle'),
         ('formations_refsite'),('formations_formateur'),('formations_refmodule'),
         ('presences_pointage'),('presences_encadrantseance'),('presences_devicebinding'),
         ('presences_auditlog'),('presences_rattrapage'),('presences_notificationabsence'),
         ('formations_qrtoken'),('gi_salle_geolocalisation'),('gi_seance_registre'),
         ('gi_seance_evenement'),('gi_seance_historique'),('gi_seance_instantane'),
         ('formations_participant'),('formations_sessionmodule'),('scolarite_dossieretudiant'),
         ('scolarite_inscriptionpedagogique')
)
SELECT format('SELECT %L AS table, count(*) AS lignes FROM public.%I;', tbl, tbl)
FROM attendu
WHERE to_regclass('public.' || tbl) IS NOT NULL
ORDER BY tbl
\gexec

\echo '===== 5. COHÉRENCE DES LIAISONS ENTRE MODULES ====='
DO $$
DECLARE v bigint;
BEGIN
  IF to_regclass('public.edts_affectationcreneau') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM edts_affectationcreneau WHERE affectation_pedagogique_id IS NULL' INTO v;
    RAISE NOTICE 'séances EDT sans affectation pédagogique : %', v;
    EXECUTE 'SELECT count(*) FROM edts_affectationcreneau WHERE salle_id IS NULL' INTO v;
    RAISE NOTICE 'séances EDT sans salle : %', v;
    EXECUTE 'SELECT count(*) FROM edts_affectationcreneau WHERE groupe_id IS NULL' INTO v;
    RAISE NOTICE 'séances EDT sans groupe : %', v;
  ELSE
    RAISE NOTICE 'edts_affectationcreneau absente : module EDT non déployé dans cette base';
  END IF;

  IF to_regclass('public.presences_pointage') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM presences_pointage WHERE seance_edt_id IS NULL AND session_id IS NULL' INTO v;
    RAISE NOTICE 'pointages sans support (ni séance EDT ni session) : %', v;
    EXECUTE 'SELECT count(*) FROM presences_pointage WHERE participant_id IS NULL' INTO v;
    RAISE NOTICE 'pointages sans participant identifié : %', v;
  ELSE
    RAISE NOTICE 'presences_pointage absente : module Présences QR non déployé dans cette base';
  END IF;

  IF to_regclass('public.gi_seance_registre') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM gi_seance_registre' INTO v;
    RAISE NOTICE 'séances enregistrées au registre QR : %', v;
    EXECUTE 'SELECT count(*) FROM gi_seance_registre WHERE affectation_id IS NULL' INTO v;
    RAISE NOTICE 'séances du registre non rattachées à une séance EDT : %', v;
  ELSE
    RAISE NOTICE 'gi_seance_registre absente : registre de séance QR non déployé';
  END IF;

  IF to_regclass('public.gi_salle_geolocalisation') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM gi_salle_geolocalisation' INTO v;
    RAISE NOTICE 'salles géolocalisées : %', v;
  ELSE
    RAISE NOTICE 'gi_salle_geolocalisation absente : géolocalisation non déployée';
  END IF;

  IF to_regclass('public.formations_qrtoken') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM formations_qrtoken' INTO v;
    RAISE NOTICE 'jetons QR émis : %', v;
  ELSE
    RAISE NOTICE 'formations_qrtoken absente : émission de QR non déployée';
  END IF;
END $$;

ROLLBACK;
\echo '=== TRANSACTION ANNULEE — AUCUNE ECRITURE EFFECTUEE ==='
