-- GET INJS APP — jeu de données de DÉMONSTRATION.
-- Ces données ne sont pas des données métier INJS réelles : elles servent
-- uniquement à exercer le parcours de badgeage. Les coordonnées du site sont
-- marquées "DÉMONSTRATION" et doivent être remplacées par la configuration
-- officielle (commande set_geofence_site du référentiel).

TRUNCATE TABLE heartbeats, pointages, sessions_qr, audit_logs, motifs_manuels,
  missions_encadrants, affectations_pedagogiques, inscriptions, utilisateurs,
  seances, ecues, ues, maquettes, groupes, semestres, niveaux, parcours,
  formations, annees_academiques, ref_sites RESTART IDENTITY CASCADE;

/* ----------------------------- Site / geofence --------------------------- */
INSERT INTO ref_sites (id, code, nom, actif, geofence_latitude, geofence_longitude, geofence_rayon_m, precision_max_m, note_configuration) VALUES
(1, 'SITE-INJS-ABJ', 'Campus INJS Abidjan', true, 5.360000, -4.008200, 200, 50,
 'DÉMONSTRATION — coordonnées à remplacer par la configuration officielle du site (set_geofence_site).');

/* ----------------------------- Chaîne LMD -------------------------------- */
INSERT INTO annees_academiques (id, libelle, date_debut, date_fin, active) VALUES
(1, '2026-2027', '2026-09-01', '2027-07-31', true);

INSERT INTO formations (id, code, nom, sigle) VALUES
(1, 'LSI', 'Licence en Sciences Infirmières', 'LSI'),
(2, 'LSC', 'Licence en Santé Communautaire', 'LSC');

INSERT INTO parcours (id, formation_id, code, nom) VALUES
(1, 1, 'SGN', 'Soins généraux'),
(2, 1, 'SAN', 'Soins anesthésiques'),
(3, 2, 'SAC', 'Santé communautaire');

INSERT INTO niveaux (id, code, nom, ordre) VALUES
(1, 'L1', 'Licence 1', 1), (2, 'L2', 'Licence 2', 2), (3, 'L3', 'Licence 3', 3),
(4, 'M1', 'Master 1', 4), (5, 'M2', 'Master 2', 5);

INSERT INTO semestres (id, niveau_id, annee_id, code, nom) VALUES
(1, 2, 1, 'S3', 'Semestre 3'), (2, 2, 1, 'S4', 'Semestre 4'),
(3, 3, 1, 'S5', 'Semestre 5'), (4, 3, 1, 'S6', 'Semestre 6');

INSERT INTO groupes (id, parcours_id, niveau_id, code, nom) VALUES
(1, 1, 2, 'L2-SGN-A', 'L2 Soins généraux — Groupe A'),
(2, 1, 2, 'L2-SGN-B', 'L2 Soins généraux — Groupe B'),
(3, 3, 2, 'L2-SAC-A', 'L2 Santé communautaire — Groupe A'),
(4, 1, 3, 'L3-SGN-A', 'L3 Soins généraux — Groupe A');

INSERT INTO maquettes (id, semestre_id, parcours_id, libelle, version) VALUES
(1, 2, 1, 'Maquette L2 SGN — Semestre 4', 'v2026.1'),
(2, 2, 3, 'Maquette L2 SAC — Semestre 4', 'v2026.1');

INSERT INTO ues (id, maquette_id, code, intitule, credits, volume_horaire) VALUES
(1, 1, 'UE-S4-11', 'Sciences fondamentales appliquées', 6, 42),
(2, 1, 'UE-S4-12', 'Soins infirmiers et procédures', 8, 56),
(3, 1, 'UE-S4-13', 'Communication et éthique professionnelle', 4, 24),
(4, 2, 'UE-S4-21', 'Santé communautaire et terrain', 6, 36);

INSERT INTO ecues (id, ue_id, code, intitule, volume_horaire) VALUES
(1, 1, 'ECUE-ANA2', 'Anatomie et physiologie II', 21),
(2, 1, 'ECUE-MIC1', 'Microbiologie générale', 21),
(3, 2, 'ECUE-PRI2', 'Procédures de soins II', 28),
(4, 2, 'ECUE-PHA1', 'Pharmacologie clinique', 28),
(5, 3, 'ECUE-COM1', 'Communication thérapeutique', 24),
(6, 4, 'ECUE-EPV1', 'Épidémiologie et promotion de la santé', 36);

/* ----------------------------- Acteurs ----------------------------------- */
INSERT INTO utilisateurs (id, matricule, nom, prenom, role, email) VALUES
(1, 'ADM-001', 'KOUASSI', 'Aya', 'ADMIN', 'aya.kouassi@injs.example'),
(2, 'ENS-1041', 'N''GUESSAN', 'Marcel', 'ENSEIGNANT', 'm.nguessan@injs.example'),
(3, 'ENS-1042', 'TRAORÉ', 'Fatoumata', 'ENSEIGNANT', 'f.traore@injs.example'),
(4, 'ENS-1043', 'DIABATÉ', 'Séverin', 'ENSEIGNANT', 's.diabate@injs.example'),
(5, 'ENC-2201', 'KONÉ', 'Aminata', 'ENCADRANT', 'a.kone@injs.example'),
(6, 'ENC-2202', 'YAO', 'Prosper', 'ENCADRANT', 'p.yao@injs.example'),
(10, 'ETU-L2-0001', 'AKÉ', 'Léonora', 'ETUDIANT', 'l.ake@injs.example'),
(11, 'ETU-L2-0002', 'BAMBA', 'Idrissa', 'ETUDIANT', 'i.bamba@injs.example'),
(12, 'ETU-L2-0003', 'CISSE', 'Mariam', 'ETUDIANT', 'm.cisse@injs.example'),
(13, 'ETU-L2-0004', 'DIOMANDÉ', 'Yann', 'ETUDIANT', 'y.diomande@injs.example'),
(14, 'ETU-L2-0005', 'EHOUMAN', 'Grâce', 'ETUDIANT', 'g.ehouman@injs.example'),
(15, 'ETU-L2-0006', 'FOFANA', 'Moussa', 'ETUDIANT', 'm.fofana@injs.example'),
(16, 'ETU-L2-0007', 'GNAHORÉ', 'Estelle', 'ETUDIANT', 'e.gnahore@injs.example'),
(17, 'ETU-L2-0008', 'HOUNKPATIN', 'Sylvain', 'ETUDIANT', 's.hounkpatin@injs.example'),
(18, 'ETU-L2-0009', 'ISSOUF', 'Rachelle', 'ETUDIANT', 'r.issouf@injs.example'),
(19, 'ETU-L2-0010', 'JEAUX', 'Cédric', 'ETUDIANT', 'c.jeaux@injs.example'),
(20, 'ETU-L2-0011', 'KOUADJO', 'Bernadette', 'ETUDIANT', 'b.kouadjo@injs.example'),
(21, 'ETU-L2-0012', 'LOBA', 'Ange', 'ETUDIANT', 'a.loba@injs.example'),
(22, 'ETU-L2-0013', 'MOUSSA', 'Clarisse', 'ETUDIANT', 'c.moussa@injs.example'),
(23, 'ETU-L2-0014', 'N''DRI', 'Olivier', 'ETUDIANT', 'o.ndri@injs.example');

INSERT INTO inscriptions (utilisateur_id, annee_id, formation_id, parcours_id, niveau_id, groupe_id, statut, date_effet) VALUES
(10, 1, 1, 1, 2, 1, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(11, 1, 1, 1, 2, 1, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(12, 1, 1, 1, 2, 1, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(13, 1, 1, 1, 2, 1, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(14, 1, 1, 1, 2, 1, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(15, 1, 1, 1, 2, 1, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(16, 1, 1, 1, 2, 1, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(17, 1, 1, 1, 2, 2, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(18, 1, 1, 1, 2, 2, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(19, 1, 1, 1, 2, 2, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(20, 1, 1, 1, 2, 3, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(21, 1, 1, 1, 2, 3, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(22, 1, 2, 3, 2, 3, 'INSCRIPTION_VALIDEE', '2025-09-15'),
(23, 1, 2, 3, 2, 3, 'INSCRIPTION_VALIDEE', '2025-09-15');

INSERT INTO affectations_pedagogiques (id, utilisateur_id, ecue_id, groupe_id, annee_id, role) VALUES
(1, 2, 1, 1, 1, 'RESPONSABLE'),
(2, 3, 3, 1, 1, 'RESPONSABLE'),
(3, 4, 5, 1, 1, 'RESPONSABLE'),
(4, 2, 2, 3, 1, 'RESPONSABLE'),
(5, 3, 4, 2, 1, 'CO_ENSEIGNANT');

INSERT INTO missions_encadrants (id, utilisateur_id, annee_id, intitule, type_activite, groupe_id, date_debut, date_fin, actif) VALUES
(1, 5, 1, 'Encadrement des travaux pratiques de soins — Groupe L2-SGN-A', 'ENCADREMENT_TP', 1, '2026-09-01', '2027-07-31', true),
(2, 6, 1, 'Suivi de terrain communautaire — Groupe L2-SAC-A', 'SUIVI_TERRAIN', 3, '2026-09-01', '2027-07-31', true);

/* ----------------------------- Séances ----------------------------------- */
INSERT INTO seances (id, identifiant_permanent, ecue_id, groupe_id, affectation_id, enseignant_id, encadrant_id, site_id,
                     type_seance, date_seance, heure_debut, heure_fin, salle, statut, statut_validation, statut_publication,
                     date_publication, version, annulee_de_id, motif_annulation, cree_par, modifie_par) VALUES
(1, 'INJS-S-000001', 1, 1, 1, 2, 5, 1, 'CM', CURRENT_DATE, '08:00', '10:00', 'Amphi A',
 'PUBLIEE', 'VALIDEE', 'PUBLIEE', now() - interval '7 days', 2, NULL, NULL, 'ADM-001', 'ADM-001'),
(2, 'INJS-S-000002', 3, 1, 2, 3, 5, 1, 'TD', CURRENT_DATE, '10:15', '12:15', 'Salle B03',
 'PUBLIEE', 'VALIDEE', 'PUBLIEE', now() - interval '7 days', 1, NULL, NULL, 'ADM-001', NULL),
(3, 'INJS-S-000003', 5, 1, 3, 4, 5, 1, 'TP', CURRENT_DATE, '14:00', '16:00', 'Laboratoire L2',
 'PUBLIEE', 'VALIDEE', 'PUBLIEE', now() - interval '7 days', 1, NULL, NULL, 'ADM-001', NULL),
(4, 'INJS-S-000004', 6, 3, 4, 2, 6, 1, 'CM', CURRENT_DATE, '08:00', '10:00', 'Salle C01',
 'PUBLIEE', 'VALIDEE', 'PUBLIEE', now() - interval '7 days', 1, NULL, NULL, 'ADM-001', NULL),
(5, 'INJS-S-000005', 1, 1, 1, 2, 5, 1, 'CM', CURRENT_DATE - 1, '08:00', '10:00', 'Amphi A',
 'TERMINEE', 'VALIDEE', 'PUBLIEE', now() - interval '8 days', 3, NULL, NULL, 'ADM-001', 'ADM-001'),
(6, 'INJS-S-000006', 3, 1, 2, 3, NULL, 1, 'TD', CURRENT_DATE + 2, '10:15', '12:15', 'Salle B03',
 'ANNULEE', 'VALIDEE', 'PUBLIEE', now() - interval '6 days', 2, NULL, 'Indisponibilité de l''enseignante', 'ADM-001', 'ADM-001'),
(7, 'INJS-S-000007', 3, 1, 2, 3, NULL, 1, 'TD', CURRENT_DATE + 4, '10:15', '12:15', 'Salle B05',
 'PUBLIEE', 'VALIDEE', 'PUBLIEE', now() - interval '1 day', 1, 6, NULL, 'ADM-001', NULL),
(8, 'INJS-S-000008', 4, 1, NULL, 2, NULL, 1, 'CM', CURRENT_DATE + 7, '08:00', '10:00', 'Amphi A',
 'SIMULATION', 'BROUILLON', 'NON_PUBLIEE', NULL, 1, NULL, NULL, 'ADM-001', NULL);

/* ----------------------------- Sessions QR ------------------------------- */
INSERT INTO sessions_qr (id, seance_id, jeton, jeton_hash, nonce, ouverte_le, expire_le, statut, rotation, emis_par) VALUES
(1, 1, 'INJS1.1.1.demo-nonce-0001.9999999999.signature-demo', md5('demo-1'), 'demo-nonce-0001',
 now() - interval '20 minutes', now() + interval '10 minutes', 'OUVERTE', 1, 'ENS-1041'),
(2, 5, 'INJS1.5.2.demo-nonce-0002.9999999999.signature-demo', md5('demo-2'), 'demo-nonce-0002',
 now() - interval '1 day', now() - interval '1 day' + interval '2 hours', 'CLOTUREE', 2, 'ENS-1041');

/* ----------------------------- Pointages --------------------------------- */
INSERT INTO pointages (id, seance_id, utilisateur_id, type_participant, session_id_qr, statut, statut_assiduite, mode,
                       source_entree, source_sortie, timestamp_entree, timestamp_sortie, duree_minutes,
                       latitude, longitude, accuracy_m, distance_m, verdict_geofence, precision_position, device_id,
                       last_heartbeat_at, outside_geofence_count, anomalies, motif_manuel, commentaire, auteur_manuel_id, auteur_manuel_nom) VALUES
(1, 5, 10, 'ETUDIANT', 2, 'TERMINE', 'PRESENT', 'QR_AUTOMATIQUE', 'BADGE_ENTREE', 'BADGE_SORTIE',
 now() - interval '1 day' + interval '55 minutes', now() - interval '1 day' + interval '2 hours', 125,
 5.360100, -4.008100, 8, 15.4, 'DANS_PERIMETRE', 'POSITION_ACCEPTABLE', 'PWA-8842', now() - interval '1 day' + interval '2 hours', 0, '[]', NULL, NULL, NULL, NULL),
(2, 5, 11, 'ETUDIANT', 2, 'TERMINE', 'RETARD', 'QR_AUTOMATIQUE', 'BADGE_ENTREE', 'BADGE_SORTIE',
 now() - interval '1 day' + interval '28 minutes', now() - interval '1 day' + interval '2 hours', 92,
 5.360200, -4.008000, 12, 22.7, 'DANS_PERIMETRE', 'POSITION_ACCEPTABLE', 'PWA-1120', now() - interval '1 day' + interval '2 hours', 0, '["RETARD_ENTREE"]', NULL, NULL, NULL, NULL),
(3, 5, 12, 'ETUDIANT', 2, 'TERMINE', 'PRESENT', 'MANUEL', 'EMARGEMENT_MANUEL', 'BADGE_SORTIE',
 now() - interval '1 day' + interval '5 minutes', now() - interval '1 day' + interval '2 hours', 115,
 NULL, NULL, NULL, NULL, 'POSITION_ABSENTE', 'POSITION_ABSENTE', NULL, now() - interval '1 day' + interval '2 hours', 0, '["EMARGEMENT_MANUEL"]',
 'QR_NON_LISIBLE', 'Lecture du QR impossible sur l''écran de l''amphi.', 2, 'N''GUESSAN Marcel'),
(4, 5, 13, 'ETUDIANT', 2, 'TERMINE', 'PRESENT', 'QR_AUTOMATIQUE', 'BADGE_ENTREE', 'SORTIE_AUTOMATIQUE_FIN_SEANCE',
 now() - interval '1 day' + interval '3 minutes', now() - interval '1 day' + interval '2 hours', 117,
 5.361500, -4.009000, 34, 178.2, 'DANS_PERIMETRE', 'POSITION_IMPRECISE', 'PWA-3391', now() - interval '1 day' + interval '2 hours', 1, '["HEARTBEAT_HORS_GEOFENCE","POSITION_IMPRECISE"]', NULL, NULL, NULL, NULL),
(5, 5, 14, 'ETUDIANT', 2, 'ABSENT_NON_BADGE', 'ABSENT', 'QR_AUTOMATIQUE', 'BADGE_ENTREE', NULL,
 now() - interval '1 day' + interval '2 minutes', NULL, NULL,
 5.360000, -4.008300, 9, 6.1, 'DANS_PERIMETRE', 'POSITION_ACCEPTABLE', 'PWA-5510', now() - interval '1 day' + interval '30 minutes', 0, '["SORTIE_NON_BADGEE"]', NULL, NULL, NULL, NULL),
(6, 5, 15, 'ETUDIANT', 2, 'TERMINE', 'PRESENT', 'QR_AUTOMATIQUE', 'BADGE_ENTREE', 'BADGE_SORTIE',
 now() - interval '1 day' + interval '1 minute', now() - interval '1 day' + interval '2 hours', 119,
 5.359900, -4.008400, 7, 12.8, 'DANS_PERIMETRE', 'POSITION_ACCEPTABLE', 'PWA-7781', now() - interval '1 day' + interval '2 hours', 0, '[]', NULL, NULL, NULL, NULL),
(7, 5, 2, 'ENSEIGNANT', 2, 'TERMINE', 'PRESENT', 'QR_AUTOMATIQUE', 'BADGE_ENTREE', 'BADGE_SORTIE',
 now() - interval '1 day' + interval '45 minutes', now() - interval '1 day' + interval '2 hours', 135,
 5.360050, -4.008150, 6, 8.2, 'DANS_PERIMETRE', 'POSITION_ACCEPTABLE', 'PWA-2041', now() - interval '1 day' + interval '2 hours', 0, '[]', NULL, NULL, NULL, NULL),
(8, 5, 5, 'ENCADRANT', 2, 'TERMINE', 'PRESENT', 'QR_AUTOMATIQUE', 'BADGE_ENTREE', 'BADGE_SORTIE',
 now() - interval '1 day' + interval '50 minutes', now() - interval '1 day' + interval '2 hours', 130,
 5.360300, -4.007900, 11, 31.5, 'DANS_PERIMETRE', 'POSITION_ACCEPTABLE', 'PWA-9012', now() - interval '1 day' + interval '2 hours', 0, '[]', NULL, NULL, NULL, NULL),
(9, 1, 16, 'ETUDIANT', 1, 'EN_COURS', NULL, 'QR_AUTOMATIQUE', 'BADGE_ENTREE', NULL,
 now() - interval '12 minutes', NULL, NULL,
 5.360020, -4.008180, 8, 4.7, 'DANS_PERIMETRE', 'POSITION_ACCEPTABLE', 'PWA-4477', now() - interval '1 minute', 0, '[]', NULL, NULL, NULL, NULL),
(10, 1, 17, 'ETUDIANT', 1, 'EN_COURS', NULL, 'QR_AUTOMATIQUE', 'BADGE_ENTREE', NULL,
 now() - interval '9 minutes', NULL, NULL,
 5.358900, -4.010100, 22, 243.6, 'HORS_PERIMETRE', 'POSITION_ACCEPTABLE', 'PWA-6621', now() - interval '30 seconds', 2, '["HORS_GEOFENCE_ENTREE_TOLEREE"]', NULL, NULL, NULL, NULL),
(11, 1, 2, 'ENSEIGNANT', 1, 'EN_COURS', NULL, 'QR_AUTOMATIQUE', 'BADGE_ENTREE', NULL,
 now() - interval '25 minutes', NULL, NULL,
 5.360010, -4.008120, 5, 3.2, 'DANS_PERIMETRE', 'POSITION_ACCEPTABLE', 'PWA-2041', now() - interval '2 minutes', 0, '[]', NULL, NULL, NULL, NULL),
(12, 1, 10, 'ETUDIANT', 1, 'EN_COURS', NULL, 'MANUEL', 'EMARGEMENT_MANUEL', NULL,
 now() - interval '6 minutes', NULL, NULL,
 NULL, NULL, NULL, NULL, 'POSITION_ABSENTE', 'POSITION_ABSENTE', NULL, NULL, 0, '["EMARGEMENT_MANUEL"]',
 'GPS_INDISPONIBLE', 'Terminal sans module GPS.', 2, 'N''GUESSAN Marcel');

INSERT INTO heartbeats (pointage_id, seance_id, utilisateur_id, horodatage, latitude, longitude, accuracy_m, distance_m, verdict) VALUES
(9, 1, 16, now() - interval '12 minutes', 5.360020, -4.008180, 8, 4.7, 'DANS_PERIMETRE'),
(9, 1, 16, now() - interval '6 minutes', 5.360040, -4.008200, 9, 6.9, 'DANS_PERIMETRE'),
(9, 1, 16, now() - interval '1 minute', 5.360030, -4.008210, 8, 5.8, 'DANS_PERIMETRE'),
(10, 1, 17, now() - interval '8 minutes', 5.360010, -4.008100, 14, 12.1, 'DANS_PERIMETRE'),
(10, 1, 17, now() - interval '4 minutes', 5.358900, -4.010100, 22, 243.6, 'HORS_PERIMETRE'),
(10, 1, 17, now() - interval '30 seconds', 5.359400, -4.009500, 19, 171.2, 'DANS_PERIMETRE'),
(11, 1, 2, now() - interval '10 minutes', 5.360010, -4.008120, 5, 3.2, 'DANS_PERIMETRE'),
(11, 1, 2, now() - interval '2 minutes', 5.360015, -4.008130, 6, 4.1, 'DANS_PERIMETRE');

/* ----------------------------- Motifs & audit ---------------------------- */
INSERT INTO motifs_manuels (code, libelle, actif, exige_commentaire) VALUES
('QR_NON_LISIBLE', 'QR non lisible', true, false),
('GPS_INDISPONIBLE', 'GPS indisponible', true, false),
('PANNE_RESEAU', 'Panne réseau', true, false),
('PROBLEME_TECHNIQUE', 'Problème technique', true, false),
('PARTICIPANT_PRESENT_SANS_BADGE', 'Participant présent sans badge', true, false),
('AUTRE', 'Autre', true, true);

INSERT INTO audit_logs (horodatage, auteur_id, auteur_nom, entite, entite_id, action, ancienne_valeur, nouvelle_valeur, motif) VALUES
(now() - interval '1 day', 2, 'N''GUESSAN Marcel', 'pointage', 3, 'CREATION_EMARGEMENT_MANUEL', NULL,
 '{"utilisateur":12,"mode":"MANUEL","motif":"QR_NON_LISIBLE"}', 'QR non lisible'),
(now() - interval '1 day', 1, 'KOUASSI Aya', 'seance', 5, 'CLOTURE_SEANCE', '{"statut":"PUBLIEE"}', '{"statut":"TERMINEE"}', 'Fin de séance automatique'),
(now() - interval '18 hours', 1, 'KOUASSI Aya', 'pointage', 4, 'CORRECTION_STATUT_ASSIDUITE', '{"statut_assiduite":"NON_RENSEIGNE"}', '{"statut_assiduite":"PRESENT"}', 'Sortie automatique de fin de séance, présence attestée par heartbeat'),
(now() - interval '6 days', 1, 'KOUASSI Aya', 'seance', 6, 'ANNULATION_SEANCE', '{"statut":"PUBLIEE"}', '{"statut":"ANNULEE"}', 'Indisponibilité de l''enseignante');

SELECT setval('ref_sites_id_seq', (SELECT max(id) FROM ref_sites));
SELECT setval('annees_academiques_id_seq', (SELECT max(id) FROM annees_academiques));
SELECT setval('formations_id_seq', (SELECT max(id) FROM formations));
SELECT setval('parcours_id_seq', (SELECT max(id) FROM parcours));
SELECT setval('niveaux_id_seq', (SELECT max(id) FROM niveaux));
SELECT setval('semestres_id_seq', (SELECT max(id) FROM semestres));
SELECT setval('groupes_id_seq', (SELECT max(id) FROM groupes));
SELECT setval('maquettes_id_seq', (SELECT max(id) FROM maquettes));
SELECT setval('ues_id_seq', (SELECT max(id) FROM ues));
SELECT setval('ecues_id_seq', (SELECT max(id) FROM ecues));
SELECT setval('utilisateurs_id_seq', (SELECT max(id) FROM utilisateurs));
SELECT setval('inscriptions_id_seq', (SELECT max(id) FROM inscriptions));
SELECT setval('affectations_pedagogiques_id_seq', (SELECT max(id) FROM affectations_pedagogiques));
SELECT setval('missions_encadrants_id_seq', (SELECT max(id) FROM missions_encadrants));
SELECT setval('seances_id_seq', (SELECT max(id) FROM seances));
SELECT setval('sessions_qr_id_seq', (SELECT max(id) FROM sessions_qr));
SELECT setval('pointages_id_seq', (SELECT max(id) FROM pointages));
SELECT setval('heartbeats_id_seq', (SELECT max(id) FROM heartbeats));
SELECT setval('audit_logs_id_seq', (SELECT max(id) FROM audit_logs));
SELECT setval('motifs_manuels_id_seq', (SELECT max(id) FROM motifs_manuels));
