/**
 * GET INJS APP — Présences QR + Géolocalisation
 * Schéma Drizzle aligné sur le référentiel réel de backend-injs2026 :
 *   scolarite.* (chaîne LMD) · edts.AffectationCreneau (séance) ·
 *   formations.QRToken (session QR) · presences.Pointage / AuditLog /
 *   DeviceBinding · formations.RefSite (geofence).
 * Aucune table CPFAE / Sygepcpfae. Aucune table Promotion.
 */
import {
  boolean,
  date,
  doublePrecision,
  index,
  integer,
  jsonb,
  pgTable,
  serial,
  text,
  time,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";

/* ------------------------------------------------------------------ */
/* Géofence — formations.RefSite                                       */
/* ------------------------------------------------------------------ */

export const refSites = pgTable("ref_sites", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(),
  nom: text("nom").notNull(),
  actif: boolean("actif").notNull().default(true),
  geofenceLatitude: doublePrecision("geofence_latitude"),
  geofenceLongitude: doublePrecision("geofence_longitude"),
  geofenceRayonM: integer("geofence_rayon_m"),
  precisionMaxM: integer("precision_max_m").notNull().default(50),
  noteConfiguration: text("note_configuration"),
  majLe: timestamp("maj_le", { withTimezone: true }).notNull().defaultNow(),
});

/* ------------------------------------------------------------------ */
/* Chaîne LMD — scolarite.*                                            */
/* ------------------------------------------------------------------ */

export const anneesAcademiques = pgTable("annees_academiques", {
  id: serial("id").primaryKey(),
  libelle: text("libelle").notNull().unique(),
  dateDebut: date("date_debut").notNull(),
  dateFin: date("date_fin").notNull(),
  active: boolean("active").notNull().default(false),
});

export const formations = pgTable("formations", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(),
  nom: text("nom").notNull(),
  sigle: text("sigle"),
});

export const parcours = pgTable("parcours", {
  id: serial("id").primaryKey(),
  formationId: integer("formation_id")
    .notNull()
    .references(() => formations.id),
  code: text("code").notNull(),
  nom: text("nom").notNull(),
});

export const niveaux = pgTable("niveaux", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(),
  nom: text("nom").notNull(),
  ordre: integer("ordre").notNull(),
});

export const semestres = pgTable("semestres", {
  id: serial("id").primaryKey(),
  niveauId: integer("niveau_id")
    .notNull()
    .references(() => niveaux.id),
  anneeId: integer("annee_id")
    .notNull()
    .references(() => anneesAcademiques.id),
  code: text("code").notNull(),
  nom: text("nom").notNull(),
});

export const groupes = pgTable("groupes", {
  id: serial("id").primaryKey(),
  parcoursId: integer("parcours_id")
    .notNull()
    .references(() => parcours.id),
  niveauId: integer("niveau_id")
    .notNull()
    .references(() => niveaux.id),
  code: text("code").notNull().unique(),
  nom: text("nom").notNull(),
});

export const maquettes = pgTable("maquettes", {
  id: serial("id").primaryKey(),
  semestreId: integer("semestre_id")
    .notNull()
    .references(() => semestres.id),
  parcoursId: integer("parcours_id")
    .notNull()
    .references(() => parcours.id),
  libelle: text("libelle").notNull(),
  version: text("version").notNull().default("v1"),
});

export const ues = pgTable("ues", {
  id: serial("id").primaryKey(),
  maquetteId: integer("maquette_id")
    .notNull()
    .references(() => maquettes.id),
  code: text("code").notNull(),
  intitule: text("intitule").notNull(),
  credits: integer("credits").notNull().default(6),
  volumeHoraire: integer("volume_horaire").notNull().default(30),
});

export const ecues = pgTable("ecues", {
  id: serial("id").primaryKey(),
  ueId: integer("ue_id")
    .notNull()
    .references(() => ues.id),
  code: text("code").notNull(),
  intitule: text("intitule").notNull(),
  volumeHoraire: integer("volume_horaire").notNull().default(15),
});

/* ------------------------------------------------------------------ */
/* Acteurs                                                             */
/* ------------------------------------------------------------------ */

export const utilisateurs = pgTable(
  "utilisateurs",
  {
    id: serial("id").primaryKey(),
    matricule: text("matricule").notNull(),
    nom: text("nom").notNull(),
    prenom: text("prenom").notNull(),
    role: text("role").notNull(), // ETUDIANT | ENSEIGNANT | ENCADRANT | ADMIN
    email: text("email"),
  },
  (t) => [uniqueIndex("utilisateurs_matricule_idx").on(t.matricule)],
);

export const inscriptions = pgTable(
  "inscriptions",
  {
    id: serial("id").primaryKey(),
    utilisateurId: integer("utilisateur_id")
      .notNull()
      .references(() => utilisateurs.id),
    anneeId: integer("annee_id")
      .notNull()
      .references(() => anneesAcademiques.id),
    formationId: integer("formation_id")
      .notNull()
      .references(() => formations.id),
    parcoursId: integer("parcours_id")
      .notNull()
      .references(() => parcours.id),
    niveauId: integer("niveau_id")
      .notNull()
      .references(() => niveaux.id),
    groupeId: integer("groupe_id")
      .notNull()
      .references(() => groupes.id),
    // Admission != inscription administrative validée != inscription pédagogique
    statut: text("statut").notNull().default("INSCRIPTION_VALIDEE"),
    dateEffet: date("date_effet").notNull(),
  },
  (t) => [index("inscriptions_utilisateur_idx").on(t.utilisateurId)],
);

export const affectationsPedagogiques = pgTable(
  "affectations_pedagogiques",
  {
    id: serial("id").primaryKey(),
    utilisateurId: integer("utilisateur_id")
      .notNull()
      .references(() => utilisateurs.id),
    ecueId: integer("ecue_id")
      .notNull()
      .references(() => ecues.id),
    groupeId: integer("groupe_id")
      .notNull()
      .references(() => groupes.id),
    anneeId: integer("annee_id")
      .notNull()
      .references(() => anneesAcademiques.id),
    role: text("role").notNull().default("RESPONSABLE"), // RESPONSABLE | CO_ENSEIGNANT
  },
  (t) => [index("affectations_utilisateur_idx").on(t.utilisateurId)],
);

export const missionsEncadrants = pgTable("missions_encadrants", {
  id: serial("id").primaryKey(),
  utilisateurId: integer("utilisateur_id")
    .notNull()
    .references(() => utilisateurs.id),
  anneeId: integer("annee_id")
    .notNull()
    .references(() => anneesAcademiques.id),
  intitule: text("intitule").notNull(),
  typeActivite: text("type_activite").notNull().default("ENCADREMENT"),
  groupeId: integer("groupe_id").references(() => groupes.id),
  dateDebut: date("date_debut").notNull(),
  dateFin: date("date_fin").notNull(),
  actif: boolean("actif").notNull().default(true),
});

/* ------------------------------------------------------------------ */
/* Séance — edts.AffectationCreneau (identité permanente)              */
/* ------------------------------------------------------------------ */

export const seances = pgTable(
  "seances",
  {
    id: serial("id").primaryKey(),
    // Identifiant technique permanent, indépendant de la date/salle/enseignant
    identifiantPermanent: text("identifiant_permanent").notNull().unique(),
    ecueId: integer("ecue_id")
      .notNull()
      .references(() => ecues.id),
    groupeId: integer("groupe_id")
      .notNull()
      .references(() => groupes.id),
    affectationId: integer("affectation_id").references(
      () => affectationsPedagogiques.id,
    ),
    enseignantId: integer("enseignant_id").references(() => utilisateurs.id),
    encadrantId: integer("encadrant_id").references(() => utilisateurs.id),
    siteId: integer("site_id").references(() => refSites.id),
    typeSeance: text("type_seance").notNull().default("CM"),
    dateSeance: date("date_seance").notNull(),
    heureDebut: time("heure_debut").notNull(),
    heureFin: time("heure_fin").notNull(),
    salle: text("salle"),
    statut: text("statut").notNull().default("PUBLIEE"),
    statutValidation: text("statut_validation").notNull().default("VALIDEE"),
    statutPublication: text("statut_publication").notNull().default("PUBLIEE"),
    datePublication: timestamp("date_publication", { withTimezone: true }),
    version: integer("version").notNull().default(1),
    annuleeDeId: integer("annulee_de_id"),
    motifAnnulation: text("motif_annulation"),
    creePar: text("cree_par"),
    modifiePar: text("modifie_par"),
    majLe: timestamp("maj_le", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    index("seances_date_idx").on(t.dateSeance),
    index("seances_groupe_idx").on(t.groupeId),
    index("seances_ecue_idx").on(t.ecueId),
  ],
);

/* ------------------------------------------------------------------ */
/* Session QR — formations.QRToken (jeton temporaire signé)            */
/* ------------------------------------------------------------------ */

export const sessionsQr = pgTable(
  "sessions_qr",
  {
    id: serial("id").primaryKey(),
    seanceId: integer("seance_id")
      .notNull()
      .references(() => seances.id),
    jeton: text("jeton").notNull(),
    jetonHash: text("jeton_hash").notNull(),
    nonce: text("nonce").notNull(),
    ouverteLe: timestamp("ouverte_le", { withTimezone: true })
      .notNull()
      .defaultNow(),
    expireLe: timestamp("expire_le", { withTimezone: true }).notNull(),
    statut: text("statut").notNull().default("OUVERTE"), // OUVERTE | EXPIREE | CLOTUREE
    rotation: integer("rotation").notNull().default(1),
    emisPar: text("emis_par"),
  },
  (t) => [
    uniqueIndex("sessions_qr_jeton_idx").on(t.jeton),
    index("sessions_qr_seance_idx").on(t.seanceId),
  ],
);

/* ------------------------------------------------------------------ */
/* Pointage — presences.Pointage                                       */
/* ------------------------------------------------------------------ */

export const pointages = pgTable(
  "pointages",
  {
    id: serial("id").primaryKey(),
    seanceId: integer("seance_id")
      .notNull()
      .references(() => seances.id),
    utilisateurId: integer("utilisateur_id")
      .notNull()
      .references(() => utilisateurs.id),
    typeParticipant: text("type_participant").notNull(), // ETUDIANT|ENSEIGNANT|ENCADRANT
    sessionIdQr: integer("session_id_qr").references(() => sessionsQr.id),

    // Processus de badgeage (référentiel réel presences.Pointage.Statut)
    statut: text("statut").notNull().default("EN_COURS"),
    // Résultat pédagogique (presences.Pointage.StatutAssiduite)
    statutAssiduite: text("statut_assiduite"),
    mode: text("mode").notNull().default("QR_AUTOMATIQUE"), // QR_AUTOMATIQUE | MANUEL
    sourceEntree: text("source_entree").notNull().default("BADGE_ENTREE"),
    sourceSortie: text("source_sortie"),

    timestampEntree: timestamp("timestamp_entree", { withTimezone: true })
      .notNull()
      .defaultNow(),
    timestampSortie: timestamp("timestamp_sortie", { withTimezone: true }),
    timestampClient: timestamp("timestamp_client", { withTimezone: true }),
    dureeMinutes: integer("duree_minutes"),

    // Mesure de position audible (jamais un simple gps_ok)
    latitude: doublePrecision("latitude"),
    longitude: doublePrecision("longitude"),
    accuracyM: doublePrecision("accuracy_m"),
    distanceM: doublePrecision("distance_m"),
    verdictGeofence: text("verdict_geofence"),
    precisionPosition: text("precision_position"),
    deviceId: text("device_id"),

    lastHeartbeatAt: timestamp("last_heartbeat_at", { withTimezone: true }),
    outsideGeofenceCount: integer("outside_geofence_count").notNull().default(0),
    anomalies: jsonb("anomalies").$type<string[]>().default([]),

    // Badgeage manuel — exception tracée
    motifManuel: text("motif_manuel"),
    commentaire: text("commentaire"),
    auteurManuelId: integer("auteur_manuel_id").references(() => utilisateurs.id),
    auteurManuelNom: text("auteur_manuel_nom"),
    corrigeDeId: integer("corrige_de_id"),
  },
  (t) => [
    index("pointages_seance_idx").on(t.seanceId),
    index("pointages_utilisateur_idx").on(t.utilisateurId),
    // Un seul pointage OUVERT par (séance, participant) : contrôlé par
    // verrou transactionnel + détection DOUBLE_ENTREE côté service, une
    // correction (corrige_de_id) devant rester possible sur la même paire.
    index("pointages_seance_utilisateur_idx").on(t.seanceId, t.utilisateurId),
  ],
);

export const heartbeats = pgTable(
  "heartbeats",
  {
    id: serial("id").primaryKey(),
    pointageId: integer("pointage_id")
      .notNull()
      .references(() => pointages.id),
    seanceId: integer("seance_id")
      .notNull()
      .references(() => seances.id),
    utilisateurId: integer("utilisateur_id")
      .notNull()
      .references(() => utilisateurs.id),
    horodatage: timestamp("horodatage", { withTimezone: true })
      .notNull()
      .defaultNow(),
    latitude: doublePrecision("latitude"),
    longitude: doublePrecision("longitude"),
    accuracyM: doublePrecision("accuracy_m"),
    distanceM: doublePrecision("distance_m"),
    verdict: text("verdict").notNull(),
  },
  (t) => [index("heartbeats_pointage_idx").on(t.pointageId)],
);

/* ------------------------------------------------------------------ */
/* Audit — presences.AuditLog (non destructif)                         */
/* ------------------------------------------------------------------ */

export const auditLogs = pgTable(
  "audit_logs",
  {
    id: serial("id").primaryKey(),
    horodatage: timestamp("horodatage", { withTimezone: true })
      .notNull()
      .defaultNow(),
    auteurId: integer("auteur_id"),
    auteurNom: text("auteur_nom").notNull(),
    entite: text("entite").notNull(),
    entiteId: integer("entite_id"),
    action: text("action").notNull(),
    ancienneValeur: jsonb("ancienne_valeur"),
    nouvelleValeur: jsonb("nouvelle_valeur"),
    motif: text("motif"),
  },
  (t) => [index("audit_logs_entite_idx").on(t.entite, t.entiteId)],
);

export const motifsManuels = pgTable("motifs_manuels", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(),
  libelle: text("libelle").notNull(),
  actif: boolean("actif").notNull().default(true),
  exigeCommentaire: boolean("exige_commentaire").notNull().default(false),
});
