/**
 * Requêtes de lecture — registres et tableaux de bord.
 * Toutes les agrégations sont faites en SQL corrélé : aucun N+1 sur les
 * présences, séances, étudiants, groupes ou enseignants.
 */
import { and, desc, eq, sql } from "drizzle-orm";
import { alias, type AnyPgColumn } from "drizzle-orm/pg-core";

import { db } from "@/db";
import {
  affectationsPedagogiques,
  auditLogs,
  ecues,
  formations,
  groupes,
  heartbeats,
  inscriptions,
  maquettes,
  missionsEncadrants,
  motifsManuels,
  niveaux,
  parcours,
  pointages,
  refSites,
  semestres,
  seances,
  sessionsQr,
  ues,
  utilisateurs,
} from "@/db/schema";

/* ------------------------------------------------------------------ */
/* Contexte LMD                                                        */
/* ------------------------------------------------------------------ */

const contexteLmd = {
  ecueCode: ecues.code,
  ecueIntitule: ecues.intitule,
  ueCode: ues.code,
  ueIntitule: ues.intitule,
  maquette: maquettes.libelle,
  semestre: semestres.code,
  niveau: niveaux.code,
  niveauNom: niveaux.nom,
  parcours: parcours.code,
  parcoursNom: parcours.nom,
  formation: formations.code,
  formationNom: formations.nom,
  groupe: groupes.code,
  groupeNom: groupes.nom,
};

function jointuresLmd() {
  return {
    ecue: ecues,
    ue: ues,
    maquette: maquettes,
    semestre: semestres,
    niveau: niveaux,
    parcours: parcours,
    formation: formations,
    groupe: groupes,
  };
}

export interface LigneSeance {
  id: number;
  identifiantPermanent: string;
  dateSeance: string;
  heureDebut: string;
  heureFin: string;
  salle: string | null;
  typeSeance: string;
  statut: string;
  statutValidation: string;
  statutPublication: string;
  version: number;
  motifAnnulation: string | null;
  annuleeDeId: number | null;
  ecueCode: string;
  ecueIntitule: string;
  ueCode: string;
  ueIntitule: string;
  maquette: string;
  semestre: string;
  niveau: string;
  niveauNom: string;
  parcours: string;
  parcoursNom: string;
  formation: string;
  formationNom: string;
  groupe: string;
  groupeNom: string;
  enseignant: string | null;
  encadrant: string | null;
  site: string | null;
  attendus: number;
  nbPointages: number;
  presents: number;
  manuels: number;
  anomalies: number;
}

const compteursSeance = {
  attendus: sql<number>`(select count(*) from inscriptions i
      where i.groupe_id = ${seances.groupeId}
        and i.statut = 'INSCRIPTION_VALIDEE'
        and i.date_effet <= ${seances.dateSeance})`,
  nbPointages: sql<number>`(select count(*) from pointages p where p.seance_id = ${seances.id})`,
  presents: sql<number>`(select count(*) from pointages p
      where p.seance_id = ${seances.id} and p.statut <> 'ABSENT_NON_BADGE')`,
  manuels: sql<number>`(select count(*) from pointages p
      where p.seance_id = ${seances.id} and p.mode = 'MANUEL')`,
  anomalies: sql<number>`(select count(*) from pointages p
      where p.seance_id = ${seances.id}
        and (p.verdict_geofence in ('HORS_PERIMETRE','POSITION_IMPRECISE','POSITION_INEXPLOITABLE')
             or p.mode = 'MANUEL'
             or p.statut = 'ABSENT_NON_BADGE'))`,
};

function nomComplet(t: { prenom: AnyPgColumn; nom: AnyPgColumn }) {
  return sql<string | null>`(${t.prenom} || ' ' || ${t.nom})`;
}

/* ------------------------------------------------------------------ */
/* Séances                                                             */
/* ------------------------------------------------------------------ */

export async function chargerSeances(filtres?: {
  date?: string;
  statut?: string;
  groupeId?: number;
  q?: string;
}): Promise<LigneSeance[]> {
  const ens = utilisateurs;
  // Deux acteurs distincts sur la même table : alias obligatoire côté SQL.
  const enc = alias(utilisateurs, "encadrant_u");

  const conditions = sql`true`;
  const where = filtres?.statut
    ? and(conditions, eq(seances.statut, filtres.statut))
    : conditions;
  const whereDate = filtres?.date ? and(where, eq(seances.dateSeance, filtres.date)) : where;

  const rows = await db
    .select({
      id: seances.id,
      identifiantPermanent: seances.identifiantPermanent,
      dateSeance: seances.dateSeance,
      heureDebut: seances.heureDebut,
      heureFin: seances.heureFin,
      salle: seances.salle,
      typeSeance: seances.typeSeance,
      statut: seances.statut,
      statutValidation: seances.statutValidation,
      statutPublication: seances.statutPublication,
      version: seances.version,
      motifAnnulation: seances.motifAnnulation,
      annuleeDeId: seances.annuleeDeId,
      ...contexteLmd,
      enseignant: nomComplet(ens),
      encadrant: nomComplet(enc),
      site: refSites.nom,
      ...compteursSeance,
    })
    .from(seances)
    .innerJoin(ecues, eq(seances.ecueId, ecues.id))
    .innerJoin(ues, eq(ecues.ueId, ues.id))
    .innerJoin(maquettes, eq(ues.maquetteId, maquettes.id))
    .innerJoin(semestres, eq(maquettes.semestreId, semestres.id))
    .innerJoin(niveaux, eq(semestres.niveauId, niveaux.id))
    .innerJoin(parcours, eq(maquettes.parcoursId, parcours.id))
    .innerJoin(formations, eq(parcours.formationId, formations.id))
    .innerJoin(groupes, eq(seances.groupeId, groupes.id))
    .leftJoin(ens, eq(seances.enseignantId, ens.id))
    .leftJoin(enc, eq(seances.encadrantId, enc.id))
    .leftJoin(refSites, eq(seances.siteId, refSites.id))
    .where(whereDate)
    .orderBy(seances.dateSeance, seances.heureDebut);

  return rows as unknown as LigneSeance[];
}

export type SeanceDetail = LigneSeance & {
  enseignantId: number | null;
  encadrantId: number | null;
  siteId: number | null;
  sessionQr: {
    id: number;
    jeton: string;
    expireLe: Date;
    rotation: number;
    statut: string;
  } | null;
  attendusListe: {
    utilisateurId: number;
    matricule: string;
    nom: string;
    role: string;
    groupe: string | null;
    dejaBadge: boolean;
    pointageId: number | null;
  }[];
  pointages: {
    id: number;
    utilisateurId: number;
    matricule: string;
    nom: string;
    typeParticipant: string;
    statut: string;
    statutAssiduite: string | null;
    mode: string;
    sourceSortie: string | null;
    timestampEntree: Date;
    timestampSortie: Date | null;
    dureeMinutes: number | null;
    distanceM: number | null;
    accuracyM: number | null;
    verdictGeofence: string | null;
    precisionPosition: string | null;
    motifManuel: string | null;
    commentaire: string | null;
    auteurManuelNom: string | null;
    anomalies: string[];
    heartbeats: number;
    lastHeartbeatAt: Date | null;
    outsideGeofenceCount: number;
  }[];
  metriques: {
    attendus: number;
    presents: number;
    absents: number;
    retards: number;
    sortiesAnticipees: number;
    manuels: number;
    anomaliesGps: number;
    anomaliesQr: number;
    enCours: number;
  };
};

export async function chargerSeanceDetail(id: number): Promise<SeanceDetail | null> {
  const base = await chargerSeances();
  const seance = base.find((s) => s.id === id);
  if (!seance) return null;

  const [ligne] = await db
    .select({
      enseignantId: seances.enseignantId,
      encadrantId: seances.encadrantId,
      siteId: seances.siteId,
      groupeId: seances.groupeId,
    })
    .from(seances)
    .where(eq(seances.id, id));

  const [session] = await db
    .select({
      id: sessionsQr.id,
      jeton: sessionsQr.jeton,
      expireLe: sessionsQr.expireLe,
      rotation: sessionsQr.rotation,
      statut: sessionsQr.statut,
    })
    .from(sessionsQr)
    .where(eq(sessionsQr.seanceId, id))
    .orderBy(desc(sessionsQr.rotation))
    .limit(1);

  // Étudiants théoriquement attendus : inscription administrative validée et
  // en vigueur à la date de la séance (jamais une liste figée).
  const inscrits = await db
    .select({
      utilisateurId: inscriptions.utilisateurId,
      matricule: utilisateurs.matricule,
      nom: sql<string>`${utilisateurs.prenom} || ' ' || ${utilisateurs.nom}`,
      role: utilisateurs.role,
      groupe: groupes.code,
    })
    .from(inscriptions)
    .innerJoin(utilisateurs, eq(inscriptions.utilisateurId, utilisateurs.id))
    .innerJoin(groupes, eq(inscriptions.groupeId, groupes.id))
    .where(
      and(
        eq(inscriptions.groupeId, ligne?.groupeId ?? -1),
        eq(inscriptions.statut, "INSCRIPTION_VALIDEE"),
        sql`${inscriptions.dateEffet} <= ${seance.dateSeance}`,
      ),
    );

  const listePointages = await db
    .select({
      id: pointages.id,
      utilisateurId: pointages.utilisateurId,
      matricule: utilisateurs.matricule,
      nom: sql<string>`${utilisateurs.prenom} || ' ' || ${utilisateurs.nom}`,
      typeParticipant: pointages.typeParticipant,
      statut: pointages.statut,
      statutAssiduite: pointages.statutAssiduite,
      mode: pointages.mode,
      sourceSortie: pointages.sourceSortie,
      timestampEntree: pointages.timestampEntree,
      timestampSortie: pointages.timestampSortie,
      dureeMinutes: pointages.dureeMinutes,
      distanceM: pointages.distanceM,
      accuracyM: pointages.accuracyM,
      verdictGeofence: pointages.verdictGeofence,
      precisionPosition: pointages.precisionPosition,
      motifManuel: pointages.motifManuel,
      commentaire: pointages.commentaire,
      auteurManuelNom: pointages.auteurManuelNom,
      anomalies: pointages.anomalies,
      lastHeartbeatAt: pointages.lastHeartbeatAt,
      outsideGeofenceCount: pointages.outsideGeofenceCount,
      heartbeats: sql<number>`(select count(*) from heartbeats h where h.pointage_id = ${pointages.id})`,
    })
    .from(pointages)
    .innerJoin(utilisateurs, eq(pointages.utilisateurId, utilisateurs.id))
    .where(eq(pointages.seanceId, id))
    .orderBy(pointages.timestampEntree);

  const parUtilisateur = new Map(listePointages.map((p) => [p.utilisateurId, p]));

  const attendusListe = [
    ...inscrits.map((i) => ({
      utilisateurId: i.utilisateurId,
      matricule: i.matricule,
      nom: i.nom,
      role: i.role,
      groupe: i.groupe,
      dejaBadge: parUtilisateur.has(i.utilisateurId),
      pointageId: parUtilisateur.get(i.utilisateurId)?.id ?? null,
    })),
    ...(seance.enseignant
      ? [
          {
            utilisateurId: ligne?.enseignantId ?? -1,
            matricule: "ENS",
            nom: seance.enseignant,
            role: "ENSEIGNANT",
            groupe: seance.groupe,
            dejaBadge: listePointages.some((p) => p.typeParticipant === "ENSEIGNANT"),
            pointageId:
              listePointages.find((p) => p.typeParticipant === "ENSEIGNANT")?.id ?? null,
          },
        ]
      : []),
    ...(seance.encadrant
      ? [
          {
            utilisateurId: ligne?.encadrantId ?? -2,
            matricule: "ENC",
            nom: seance.encadrant,
            role: "ENCADRANT",
            groupe: seance.groupe,
            dejaBadge: listePointages.some((p) => p.typeParticipant === "ENCADRANT"),
            pointageId:
              listePointages.find((p) => p.typeParticipant === "ENCADRANT")?.id ?? null,
          },
        ]
      : []),
  ];

  const presents = listePointages.filter((p) => p.statut !== "ABSENT_NON_BADGE").length;
  const retards = listePointages.filter((p) => p.statutAssiduite === "RETARD").length;
  const sortiesAnticipees = listePointages.filter(
    (p) =>
      p.timestampSortie !== null &&
      `${seance.dateSeance}T${seance.heureFin}:00` &&
      new Date(p.timestampSortie).getTime() <
        new Date(`${seance.dateSeance}T${seance.heureFin}:00`).getTime(),
  ).length;
  const manuels = listePointages.filter((p) => p.mode === "MANUEL").length;
  const anomaliesGps = listePointages.filter(
    (p) =>
      p.verdictGeofence === "HORS_PERIMETRE" ||
      p.verdictGeofence === "POSITION_IMPRECISE" ||
      p.verdictGeofence === "POSITION_INEXPLOITABLE" ||
      (p.anomalies ?? []).some((a) => a.includes("GEOFENCE") || a.includes("PRECISION")),
  ).length;
  const anomaliesQr = listePointages.filter(
    (p) => p.mode === "MANUEL" || (p.anomalies ?? []).some((a) => a.includes("QR")),
  ).length;

  return {
    ...seance,
    enseignantId: ligne?.enseignantId ?? null,
    encadrantId: ligne?.encadrantId ?? null,
    siteId: ligne?.siteId ?? null,
    sessionQr: session ?? null,
    attendusListe,
    pointages: listePointages.map((p) => ({
      ...p,
      anomalies: (p.anomalies ?? []) as string[],
    })),
    metriques: {
      attendus: attendusListe.length,
      presents,
      absents: Math.max(0, attendusListe.length - presents),
      retards,
      sortiesAnticipees,
      manuels,
      anomaliesGps,
      anomaliesQr,
      enCours: listePointages.filter((p) => p.statut === "EN_COURS").length,
    },
  };
}

/* ------------------------------------------------------------------ */
/* Tableau de bord                                                     */
/* ------------------------------------------------------------------ */

export interface TableauDeBord {
  kpis: {
    seancesJour: number;
    presentsJour: number;
    attendusJour: number;
    tauxPresence: number;
    anomalies: number;
    manuels: number;
    heartbeatsJour: number;
    sessionsQrOuvertes: number;
  };
  parRole: { role: string; presents: number; total: number }[];
  seancesJour: LigneSeance[];
  anomalies: {
    id: number;
    seance: string;
    nom: string;
    typeParticipant: string;
    anomalies: string[];
    verdict: string | null;
    horodatage: Date;
  }[];
}

export async function chargerTableauDeBord(): Promise<TableauDeBord> {
  const aujourdhui = new Date().toISOString().slice(0, 10);
  const seancesJour = (await chargerSeances({ date: aujourdhui })) as LigneSeance[];

  const [agg] = await db.select({
    pointages: sql<number>`count(*)`,
    presents: sql<number>`count(*) filter (where ${pointages.statut} <> 'ABSENT_NON_BADGE')`,
    manuels: sql<number>`count(*) filter (where ${pointages.mode} = 'MANUEL')`,
    anomalies: sql<number>`count(*) filter (where ${pointages.verdictGeofence} in ('HORS_PERIMETRE','POSITION_IMPRECISE','POSITION_INEXPLOITABLE') or ${pointages.mode} = 'MANUEL' or ${pointages.statut} = 'ABSENT_NON_BADGE')`,
  }).from(pointages);

  const [hb] = await db.select({ n: sql<number>`count(*)` }).from(heartbeats);

  const [sessions] = await db
    .select({ n: sql<number>`count(*)` })
    .from(sessionsQr)
    .where(eq(sessionsQr.statut, "OUVERTE"));

  const parRole = await db
    .select({
      role: pointages.typeParticipant,
      presents: sql<number>`count(*) filter (where ${pointages.statut} <> 'ABSENT_NON_BADGE')`,
      total: sql<number>`count(*)`,
    })
    .from(pointages)
    .groupBy(pointages.typeParticipant);

  const attendusJour = seancesJour.reduce((t, s) => t + Number(s.attendus), 0);
  const presentsJour = seancesJour.reduce((t, s) => t + Number(s.presents), 0);

  const anomalies = await db
    .select({
      id: pointages.id,
      seance: sql<string>`${ecues.code} || ' · ' || ${groupes.code}`,
      nom: sql<string>`${utilisateurs.prenom} || ' ' || ${utilisateurs.nom}`,
      typeParticipant: pointages.typeParticipant,
      anomalies: pointages.anomalies,
      verdict: pointages.verdictGeofence,
      horodatage: pointages.timestampEntree,
    })
    .from(pointages)
    .innerJoin(utilisateurs, eq(pointages.utilisateurId, utilisateurs.id))
    .innerJoin(seances, eq(pointages.seanceId, seances.id))
    .innerJoin(ecues, eq(seances.ecueId, ecues.id))
    .innerJoin(groupes, eq(seances.groupeId, groupes.id))
    .where(
      sql`(${pointages.verdictGeofence} in ('HORS_PERIMETRE','POSITION_IMPRECISE','POSITION_INEXPLOITABLE')
           or ${pointages.mode} = 'MANUEL' or ${pointages.statut} = 'ABSENT_NON_BADGE')`,
    )
    .orderBy(desc(pointages.timestampEntree))
    .limit(12);

  return {
    kpis: {
      seancesJour: seancesJour.length,
      presentsJour,
      attendusJour,
      tauxPresence: attendusJour
        ? Math.round((presentsJour / attendusJour) * 1000) / 10
        : 0,
      anomalies: Number(agg?.anomalies ?? 0),
      manuels: Number(agg?.manuels ?? 0),
      heartbeatsJour: Number(hb?.n ?? 0),
      sessionsQrOuvertes: Number(sessions?.n ?? 0),
    },
    parRole: parRole.map((r) => ({
      role: r.role,
      presents: Number(r.presents),
      total: Number(r.total),
    })),
    seancesJour,
    anomalies: anomalies.map((a) => ({
      ...a,
      anomalies: (a.anomalies ?? []) as string[],
    })),
  };
}

/* ------------------------------------------------------------------ */
/* Historique des présences                                            */
/* ------------------------------------------------------------------ */

export interface LignePresence {
  id: number;
  seanceId: number;
  seance: string;
  dateSeance: string;
  heureDebut: string;
  heureFin: string;
  groupe: string;
  matricule: string;
  nom: string;
  typeParticipant: string;
  statut: string;
  statutAssiduite: string | null;
  mode: string;
  timestampEntree: Date;
  timestampSortie: Date | null;
  dureeMinutes: number | null;
  verdictGeofence: string | null;
  precisionPosition: string | null;
  accuracyM: number | null;
  motifManuel: string | null;
  commentaire: string | null;
  auteurManuelNom: string | null;
  anomalies: string[];
  heartbeats: number;
}

export async function chargerPresences(filtres?: {
  typeParticipant?: string;
  seanceId?: number;
  groupe?: string;
  ecue?: string;
  mode?: string;
  nom?: string;
}): Promise<LignePresence[]> {
  const where = and(
    filtres?.typeParticipant
      ? eq(pointages.typeParticipant, filtres.typeParticipant)
      : undefined,
    filtres?.seanceId ? eq(pointages.seanceId, filtres.seanceId) : undefined,
    filtres?.mode ? eq(pointages.mode, filtres.mode) : undefined,
    filtres?.groupe ? eq(groupes.code, filtres.groupe) : undefined,
    filtres?.ecue ? eq(ecues.code, filtres.ecue) : undefined,
    filtres?.nom ? sql`(${utilisateurs.prenom} || ' ' || ${utilisateurs.nom}) ilike ${"%" + filtres.nom + "%"}` : undefined,
  );

  const rows = await db
    .select({
      id: pointages.id,
      seanceId: pointages.seanceId,
      seance: sql<string>`${ecues.code} || ' — ' || ${ecues.intitule}`,
      dateSeance: seances.dateSeance,
      heureDebut: seances.heureDebut,
      heureFin: seances.heureFin,
      groupe: groupes.code,
      matricule: utilisateurs.matricule,
      nom: sql<string>`${utilisateurs.prenom} || ' ' || ${utilisateurs.nom}`,
      typeParticipant: pointages.typeParticipant,
      statut: pointages.statut,
      statutAssiduite: pointages.statutAssiduite,
      mode: pointages.mode,
      timestampEntree: pointages.timestampEntree,
      timestampSortie: pointages.timestampSortie,
      dureeMinutes: pointages.dureeMinutes,
      verdictGeofence: pointages.verdictGeofence,
      precisionPosition: pointages.precisionPosition,
      accuracyM: pointages.accuracyM,
      motifManuel: pointages.motifManuel,
      commentaire: pointages.commentaire,
      auteurManuelNom: pointages.auteurManuelNom,
      anomalies: pointages.anomalies,
      heartbeats: sql<number>`(select count(*) from heartbeats h where h.pointage_id = ${pointages.id})`,
    })
    .from(pointages)
    .innerJoin(utilisateurs, eq(pointages.utilisateurId, utilisateurs.id))
    .innerJoin(seances, eq(pointages.seanceId, seances.id))
    .innerJoin(ecues, eq(seances.ecueId, ecues.id))
    .innerJoin(groupes, eq(seances.groupeId, groupes.id))
    .where(where)
    .orderBy(desc(pointages.timestampEntree))
    .limit(200);

  return rows.map((r) => ({ ...r, anomalies: (r.anomalies ?? []) as string[] }));
}

/* ------------------------------------------------------------------ */
/* Audit, configuration, annuaire                                      */
/* ------------------------------------------------------------------ */

export async function chargerAudit(limit = 100) {
  const rows = await db
    .select()
    .from(auditLogs)
    .orderBy(desc(auditLogs.horodatage))
    .limit(limit);
  return rows;
}

export async function chargerSites() {
  return db.select().from(refSites).orderBy(refSites.id);
}

export async function chargerActeurs() {
  return db.select().from(utilisateurs).orderBy(utilisateurs.id);
}

export async function chargerMotifsManuels() {
  return db
    .select()
    .from(motifsManuels)
    .orderBy(motifsManuels.id);
}

export async function chargerMissions() {
  return db.select().from(missionsEncadrants).orderBy(missionsEncadrants.id);
}

export async function chargerAffectations() {
  return db
    .select({
      id: affectationsPedagogiques.id,
      enseignant: sql<string>`${utilisateurs.prenom} || ' ' || ${utilisateurs.nom}`,
      ecue: ecues.code,
      groupe: groupes.code,
      role: affectationsPedagogiques.role,
    })
    .from(affectationsPedagogiques)
    .innerJoin(utilisateurs, eq(affectationsPedagogiques.utilisateurId, utilisateurs.id))
    .innerJoin(ecues, eq(affectationsPedagogiques.ecueId, ecues.id))
    .innerJoin(groupes, eq(affectationsPedagogiques.groupeId, groupes.id));
}

export { jointuresLmd };
