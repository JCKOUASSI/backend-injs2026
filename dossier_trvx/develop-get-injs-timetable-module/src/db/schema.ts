import {
  boolean,
  date,
  index,
  integer,
  jsonb,
  pgTable,
  serial,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";

/**
 * GET INJS APP — schéma de gestion des emplois du temps LMD de l'INJS d'Abidjan.
 * Toutes les tables du module sont préfixées par "gi_" (get-injs) sauf les
 * référentiels partagés, afin de rester intégrable dans le backend-injs2026.
 */

export const appMeta = pgTable("gi_app_meta", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const academicYears = pgTable("gi_academic_years", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(),
  label: text("label").notNull(),
  dateDebut: date("date_debut"),
  dateFin: date("date_fin"),
  statut: text("statut").notNull().default("preparation"),
  active: boolean("active").notNull().default(false),
});

export const filieres = pgTable("gi_filieres", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(),
  nom: text("nom").notNull(),
  ecole: text("ecole").notNull().default("INJS"),
  actif: boolean("actif").notNull().default(true),
});

export const formations = pgTable(
  "gi_formations",
  {
    id: serial("id").primaryKey(),
    filiereId: integer("filiere_id")
      .notNull()
      .references(() => filieres.id, { onDelete: "cascade" }),
    code: text("code").notNull(),
    nom: text("nom").notNull(),
    cycle: text("cycle").notNull().default("Licence-Master"),
    maquette: text("maquette").notNull().default("maquette_publiee_injs"),
    actif: boolean("actif").notNull().default(true),
  },
  (table) => [uniqueIndex("gi_formations_code_uq").on(table.code)],
);

export const batiments = pgTable("gi_batiments", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(),
  nom: text("nom").notNull(),
  zone: text("zone").notNull().default("enseignement"),
});

export const salles = pgTable(
  "gi_salles",
  {
    id: serial("id").primaryKey(),
    batimentId: integer("batiment_id").references(() => batiments.id, { onDelete: "set null" }),
    code: text("code").notNull(),
    nom: text("nom").notNull(),
    type: text("type").notNull().default("cours"),
    capacite: integer("capacite").notNull().default(30),
    equipements: text("equipements").notNull().default(""),
    schedulable: boolean("schedulable").notNull().default(true),
  },
  (table) => [uniqueIndex("gi_salles_code_uq").on(table.code)],
);

export const vagues = pgTable(
  "gi_vagues",
  {
    id: serial("id").primaryKey(),
    code: text("code").notNull(),
    label: text("label").notNull(),
    niveau: text("niveau").notNull(),
    anneeId: integer("annee_id")
      .notNull()
      .references(() => academicYears.id, { onDelete: "cascade" }),
    dateDebut: date("date_debut"),
    dateFin: date("date_fin"),
    statut: text("statut").notNull().default("ouverte"),
    effectifPrevu: integer("effectif_prevu").notNull().default(0),
    effectifReel: integer("effectif_reel").notNull().default(0),
  },
  (table) => [uniqueIndex("gi_vagues_code_annee_uq").on(table.code, table.anneeId)],
);

export const groupes = pgTable(
  "gi_groupes",
  {
    id: serial("id").primaryKey(),
    code: text("code").notNull(),
    label: text("label").notNull(),
    formationId: integer("formation_id")
      .notNull()
      .references(() => formations.id, { onDelete: "cascade" }),
    vagueId: integer("vague_id").references(() => vagues.id, { onDelete: "set null" }),
    anneeId: integer("annee_id")
      .notNull()
      .references(() => academicYears.id, { onDelete: "cascade" }),
    niveau: text("niveau").notNull(),
    effectifCible: integer("effectif_cible").notNull().default(40),
    effectif: integer("effectif").notNull().default(0),
    source: text("source").notNull().default("referentiel"),
    actif: boolean("actif").notNull().default(true),
  },
  (table) => [uniqueIndex("gi_groupes_code_annee_uq").on(table.code, table.anneeId)],
);

export const enseignants = pgTable("gi_enseignants", {
  id: serial("id").primaryKey(),
  matricule: text("matricule").notNull().unique(),
  nom: text("nom").notNull(),
  prenom: text("prenom").notNull(),
  grade: text("grade").notNull().default("Assistant"),
  specialite: text("specialite").notNull().default("EM"),
  email: text("email"),
  maxHeures: integer("max_heures").notNull().default(22),
  actif: boolean("actif").notNull().default(true),
});

export const modules = pgTable(
  "gi_modules",
  {
    id: serial("id").primaryKey(),
    code: text("code").notNull(),
    formationId: integer("formation_id")
      .notNull()
      .references(() => formations.id, { onDelete: "cascade" }),
    semestre: integer("semestre").notNull(),
    titre: text("titre").notNull(),
    ects: integer("ects").notNull().default(3),
    nature: text("nature").notNull().default("mixte"),
    heuresCm: integer("heures_cm").notNull().default(20),
    heuresTd: integer("heures_td").notNull().default(20),
    heuresTp: integer("heures_tp").notNull().default(0),
    roomNeedCm: text("room_need_cm").notNull().default("amphi"),
    roomNeedTd: text("room_need_td").notNull().default("td"),
    roomNeedTp: text("room_need_tp").notNull().default("gym"),
    source: text("source").notNull().default("maquette_publiee_injs"),
    actif: boolean("actif").notNull().default(true),
  },
  (table) => [
    uniqueIndex("gi_modules_code_uq").on(table.code),
    index("gi_modules_formation_semestre_idx").on(table.formationId, table.semestre),
  ],
);

export const moduleEnseignants = pgTable(
  "gi_module_enseignants",
  {
    id: serial("id").primaryKey(),
    moduleId: integer("module_id")
      .notNull()
      .references(() => modules.id, { onDelete: "cascade" }),
    enseignantId: integer("enseignant_id")
      .notNull()
      .references(() => enseignants.id, { onDelete: "cascade" }),
    typeSeance: text("type_seance").notNull().default("CM"),
    chargeHoraire: integer("charge_horaire").notNull().default(2),
  },
  (table) => [
    uniqueIndex("gi_module_enseignants_uq").on(table.moduleId, table.enseignantId, table.typeSeance),
  ],
);

export const etudiants = pgTable(
  "gi_etudiants",
  {
    id: serial("id").primaryKey(),
    matricule: text("matricule").notNull(),
    nom: text("nom").notNull(),
    prenom: text("prenom").notNull(),
    sexe: text("sexe").notNull().default("F"),
    dateNaissance: date("date_naissance"),
    email: text("email"),
    telephone: text("telephone"),
    anneeId: integer("annee_id").references(() => academicYears.id, { onDelete: "set null" }),
    formationId: integer("formation_id").references(() => formations.id, { onDelete: "set null" }),
    groupeId: integer("groupe_id").references(() => groupes.id, { onDelete: "set null" }),
    vagueId: integer("vague_id").references(() => vagues.id, { onDelete: "set null" }),
    niveau: text("niveau"),
    statut: text("statut").notNull().default("inscrit"),
    source: text("source").notNull().default("app"),
    importeLe: timestamp("importe_le", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => [
    uniqueIndex("gi_etudiants_matricule_uq").on(table.matricule),
    index("gi_etudiants_formation_idx").on(table.formationId),
    index("gi_etudiants_groupe_idx").on(table.groupeId),
  ],
);

export const inscriptions = pgTable(
  "gi_inscriptions",
  {
    id: serial("id").primaryKey(),
    etudiantId: integer("etudiant_id")
      .notNull()
      .references(() => etudiants.id, { onDelete: "cascade" }),
    anneeId: integer("annee_id")
      .notNull()
      .references(() => academicYears.id, { onDelete: "cascade" }),
    filiereId: integer("filiere_id").references(() => filieres.id, { onDelete: "set null" }),
    formationId: integer("formation_id").references(() => formations.id, { onDelete: "set null" }),
    groupeId: integer("groupe_id").references(() => groupes.id, { onDelete: "set null" }),
    vagueId: integer("vague_id").references(() => vagues.id, { onDelete: "set null" }),
    niveau: text("niveau").notNull(),
    semestre: integer("semestre").notNull(),
    statut: text("statut").notNull().default("inscrit"),
    source: text("source").notNull().default("app"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => [
    uniqueIndex("gi_inscriptions_uq").on(table.etudiantId, table.anneeId, table.semestre),
    index("gi_inscriptions_groupe_idx").on(table.groupeId, table.anneeId, table.semestre),
  ],
);

export const emploisDuTemps = pgTable(
  "gi_emplois_du_temps",
  {
    id: serial("id").primaryKey(),
    code: text("code").notNull(),
    libelle: text("libelle").notNull(),
    anneeId: integer("annee_id")
      .notNull()
      .references(() => academicYears.id, { onDelete: "cascade" }),
    version: integer("version").notNull().default(1),
    statut: text("statut").notNull().default("brouillon"),
    params: jsonb("params").$type<Record<string, unknown>>().notNull().default({}),
    stats: jsonb("stats").$type<Record<string, unknown>>().notNull().default({}),
    genereLe: timestamp("genere_le", { withTimezone: true }).defaultNow().notNull(),
    publieLe: timestamp("publie_le", { withTimezone: true }),
  },
  (table) => [uniqueIndex("gi_edt_code_uq").on(table.code)],
);

export const seances = pgTable(
  "gi_seances",
  {
    id: serial("id").primaryKey(),
    edtId: integer("edt_id")
      .notNull()
      .references(() => emploisDuTemps.id, { onDelete: "cascade" }),
    anneeId: integer("annee_id")
      .notNull()
      .references(() => academicYears.id, { onDelete: "cascade" }),
    formationId: integer("formation_id")
      .notNull()
      .references(() => formations.id, { onDelete: "cascade" }),
    moduleId: integer("module_id")
      .notNull()
      .references(() => modules.id, { onDelete: "cascade" }),
    groupeId: integer("groupe_id").references(() => groupes.id, { onDelete: "cascade" }),
    vagueId: integer("vague_id").references(() => vagues.id, { onDelete: "set null" }),
    enseignantId: integer("enseignant_id").references(() => enseignants.id, { onDelete: "set null" }),
    salleId: integer("salle_id").references(() => salles.id, { onDelete: "set null" }),
    niveau: text("niveau").notNull(),
    semestre: integer("semestre").notNull(),
    typeSeance: text("type_seance").notNull(),
    jour: integer("jour").notNull(),
    slotCode: text("slot_code").notNull(),
    heureDebut: text("heure_debut").notNull(),
    heureFin: text("heure_fin").notNull(),
    effectif: integer("effectif").notNull().default(0),
    verrouille: boolean("verrouille").notNull().default(false),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => [
    index("gi_seances_scope_idx").on(table.anneeId, table.semestre, table.formationId),
    index("gi_seances_groupe_idx").on(table.groupeId, table.semestre),
    index("gi_seances_salle_idx").on(table.salleId, table.semestre),
  ],
);

export const generationRuns = pgTable("gi_generation_runs", {
  id: serial("id").primaryKey(),
  anneeId: integer("annee_id")
    .notNull()
    .references(() => academicYears.id, { onDelete: "cascade" }),
  edtId: integer("edt_id").references(() => emploisDuTemps.id, { onDelete: "set null" }),
  scope: jsonb("scope").$type<Record<string, unknown>>().notNull().default({}),
  options: jsonb("options").$type<Record<string, unknown>>().notNull().default({}),
  statut: text("statut").notNull().default("en_cours"),
  stats: jsonb("stats").$type<Record<string, unknown>>().notNull().default({}),
  logs: jsonb("logs").$type<string[]>().notNull().default([]),
  dureeMs: integer("duree_ms").notNull().default(0),
  demarreLe: timestamp("demarre_le", { withTimezone: true }).defaultNow().notNull(),
  termineLe: timestamp("termine_le", { withTimezone: true }),
});

export const importJobs = pgTable("gi_import_jobs", {
  id: serial("id").primaryKey(),
  fichier: text("fichier").notNull(),
  anneeId: integer("annee_id").references(() => academicYears.id, { onDelete: "set null" }),
  statut: text("statut").notNull().default("en_cours"),
  lignes: integer("lignes").notNull().default(0),
  importes: integer("importes").notNull().default(0),
  ignores: integer("ignores").notNull().default(0),
  referentielsCrees: jsonb("referentiels_crees").$type<Record<string, unknown>>().notNull().default({}),
  erreurs: jsonb("erreurs").$type<string[]>().notNull().default([]),
  dureeMs: integer("duree_ms").notNull().default(0),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});
