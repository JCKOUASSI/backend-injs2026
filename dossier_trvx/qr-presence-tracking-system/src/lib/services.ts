/**
 * Services d'écriture — badgeage QR, heartbeat, sortie, émargement manuel,
 * correction. Le serveur est l'autorité finale : token, séance, participant,
 * geofence et RBAC sont toujours revérifiés ici.
 */
import { and, eq, sql } from "drizzle-orm";

import { db } from "../db";
import {
  affectationsPedagogiques,
  auditLogs,
  ecues,
  groupes,
  heartbeats,
  inscriptions,
  missionsEncadrants,
  pointages,
  refSites,
  seances,
  sessionsQr,
  utilisateurs,
} from "../db/schema";
import {
  Acteur,
  erreur,
  evaluerPosition,
  creerNonce,
  hashJeton,
  peut,
  ReponseErreur,
  signerJeton,
  verifierJeton,
  type EvaluationPosition,
  type ModeBadgeage,
  type MotifManuel,
  type Role,
  type StatutAssiduite,
} from "./domain";

export type Resultat<T> = (T & { ok: true }) | ReponseErreur;

export const RETARD_APRES_MINUTES = 15;

/* ------------------------------------------------------------------ */
/* Acteur (authentification de démonstration par en-tête)               */
/* ------------------------------------------------------------------ */

export async function resolverActeur(acteurId: unknown): Promise<Acteur | null> {
  const id = Number(acteurId);
  if (!Number.isFinite(id)) return null;
  const [u] = await db
    .select()
    .from(utilisateurs)
    .where(eq(utilisateurs.id, id))
    .limit(1);
  if (!u) return null;
  return { id: u.id, nom: `${u.nom} ${u.prenom}`, role: u.role as Role };
}

/* ------------------------------------------------------------------ */
/* Journal d'audit non destructif                                      */
/* ------------------------------------------------------------------ */

export async function journaliser(params: {
  auteurId?: number | null;
  auteurNom: string;
  entite: string;
  entiteId?: number | null;
  action: string;
  ancienneValeur?: unknown;
  nouvelleValeur?: unknown;
  motif?: string | null;
}) {
  await db.insert(auditLogs).values({
    auteurId: params.auteurId ?? null,
    auteurNom: params.auteurNom,
    entite: params.entite,
    entiteId: params.entiteId ?? null,
    action: params.action,
    ancienneValeur: params.ancienneValeur ?? null,
    nouvelleValeur: params.nouvelleValeur ?? null,
    motif: params.motif ?? null,
  });
}

/* ------------------------------------------------------------------ */
/* Session QR                                                          */
/* ------------------------------------------------------------------ */

export async function ouvrirSessionQr(params: {
  acteur: Acteur;
  seanceId: number;
  dureeSecondes?: number;
  emission?: string;
}): Promise<
  Resultat<{
    session: { id: number; jeton: string; expireLe: Date; rotation: number; nonce: string };
  }>
> {
  if (!peut(params.acteur, "session.qr.emettre")) return erreur("UTILISATEUR_NON_AUTORISE");

  const [seance] = await db.select().from(seances).where(eq(seances.id, params.seanceId));
  if (!seance) return erreur("PRESENCE_INTROUVABLE");
  if (seance.statut === "ANNULEE") return erreur("SEANCE_ANNULEE");
  if (seance.statut === "TERMINEE") return erreur("SEANCE_TERMINEE");
  if (seance.statut !== "PUBLIEE") return erreur("SEANCE_INACTIVE");

  const duree = Math.min(Math.max(params.dureeSecondes ?? 300, 30), 3600);
  const expirationEpoch = Math.floor(Date.now() / 1000) + duree;

  const session = await db.transaction(async (tx) => {
    // Anti-rejeu : toute session encore ouverte de la séance est expirée.
    await tx
      .update(sessionsQr)
      .set({ statut: "EXPIREE" })
      .where(
        and(
          eq(sessionsQr.seanceId, params.seanceId),
          eq(sessionsQr.statut, "OUVERTE"),
        ),
      );

    const [{ maxRotation }] = await tx
      .select({ maxRotation: sql<number>`coalesce(max(${sessionsQr.rotation}), 0)` })
      .from(sessionsQr)
      .where(eq(sessionsQr.seanceId, params.seanceId));

    const nonce = creerNonce();
    const id = await tx
      .insert(sessionsQr)
      .values({
        seanceId: params.seanceId,
        jeton: "provisoire",
        jetonHash: "",
        nonce,
        expireLe: new Date(expirationEpoch * 1000),
        statut: "OUVERTE",
        rotation: Number(maxRotation ?? 0) + 1,
        emisPar: params.emission ?? params.acteur.nom,
      })
      .returning({ id: sessionsQr.id });

    const sessionId = id[0].id;
    const jeton = signerJeton({
      seanceId: params.seanceId,
      sessionId,
      nonce,
      expirationEpoch,
    });
    await tx
      .update(sessionsQr)
      .set({ jeton, jetonHash: hashJeton(jeton) })
      .where(eq(sessionsQr.id, sessionId));

    await tx
      .update(seances)
      .set({ majLe: new Date() })
      .where(eq(seances.id, params.seanceId));

    return {
      id: sessionId,
      jeton,
      expireLe: new Date(expirationEpoch * 1000),
      rotation: Number(maxRotation ?? 0) + 1,
      nonce,
    };
  });

  return { ok: true, session };
}

/* ------------------------------------------------------------------ */
/* Vérifications partagées                                             */
/* ------------------------------------------------------------------ */

async function chargerSeanceComplete(seanceId: number) {
  const [row] = await db
    .select({
      seance: seances,
      site: refSites,
      ecue: ecues,
      groupe: groupes,
    })
    .from(seances)
    .leftJoin(refSites, eq(seances.siteId, refSites.id))
    .innerJoin(ecues, eq(seances.ecueId, ecues.id))
    .innerJoin(groupes, eq(seances.groupeId, groupes.id))
    .where(eq(seances.id, seanceId))
    .limit(1);
  return row ?? null;
}

export function verifierOuvertureSeance(statut: string): ReponseErreur | null {
  if (statut === "ANNULEE") return erreur("SEANCE_ANNULEE");
  if (statut === "TERMINEE") return erreur("SEANCE_TERMINEE");
  if (statut !== "PUBLIEE") return erreur("SEANCE_INACTIVE");
  return null;
}

/** Contrôle de participant selon la nature métier du rôle (jamais par nom). */
export async function verifierParticipant(params: {
  utilisateurId: number;
  role: Role;
  seance: { id: number; ecueId: number; groupeId: number; dateSeance: string; encadrantId: number | null };
}): Promise<ReponseErreur | null> {
  const { utilisateurId, role, seance } = params;

  if (role === "ETUDIANT" || role === "ADMIN") {
    const insc = await db
      .select()
      .from(inscriptions)
      .where(
        and(
          eq(inscriptions.utilisateurId, utilisateurId),
          eq(inscriptions.statut, "INSCRIPTION_VALIDEE"),
        ),
      );
    const enVigueur = insc.filter((i) => i.dateEffet <= seance.dateSeance);
    if (enVigueur.length === 0) return erreur("ETUDIANT_NON_INSCRIT");
    if (!enVigueur.some((i) => i.groupeId === seance.groupeId)) {
      return erreur("ETUDIANT_HORS_GROUPE");
    }
    return null;
  }

  if (role === "ENSEIGNANT") {
    const aff = await db
      .select()
      .from(affectationsPedagogiques)
      .where(
        and(
          eq(affectationsPedagogiques.utilisateurId, utilisateurId),
          eq(affectationsPedagogiques.ecueId, seance.ecueId),
          eq(affectationsPedagogiques.groupeId, seance.groupeId),
        ),
      );
    if (aff.length === 0) return erreur("ENSEIGNANT_NON_AFFECTE");
    return null;
  }

  // ENCADRANT : mission / activité couvrant la séance. Un encadrant n'est
  // jamais assimilé à un enseignant.
  const missions = await db
    .select()
    .from(missionsEncadrants)
    .where(
      and(
        eq(missionsEncadrants.utilisateurId, utilisateurId),
        eq(missionsEncadrants.actif, true),
      ),
    );
  const couvrante = missions.find(
    (m) =>
      m.dateDebut <= seance.dateSeance &&
      m.dateFin >= seance.dateSeance &&
      (m.groupeId === null || m.groupeId === seance.groupeId),
  );
  if (!couvrante) return erreur("ACTIVITE_NON_AUTORISEE");
  return null;
}

function statutAssiduiteDepuis(entree: Date, debut: Date): StatutAssiduite {
  const decalage = (entree.getTime() - debut.getTime()) / 60000;
  return decalage > RETARD_APRES_MINUTES ? "RETARD" : "PRESENT";
}

function debutSeanceEnDate(dateSeance: string, heureDebut: string): Date {
  return new Date(`${dateSeance}T${heureDebut}:00`);
}

/* ------------------------------------------------------------------ */
/* 1. Scan QR (badgeage automatique)                                   */
/* ------------------------------------------------------------------ */

export async function consommerScan(params: {
  jeton: string;
  acteur: Acteur;
  latitude?: number | null;
  longitude?: number | null;
  accuracy?: number | null;
  deviceId?: string | null;
  timestampClient?: string | null;
}): Promise<
  Resultat<{
    pointage: { id: number; statut: string; mode: ModeBadgeage; timestampEntree: Date };
    seance: { id: number; libelle: string; dateSeance: string; heureDebut: string; heureFin: string; salle: string | null };
    evaluation: EvaluationPosition;
  }>
> {
  const jeton = verifierJeton(params.jeton);
  if (!jeton.valide) return erreur(jeton.code);

  const [session] = await db
    .select()
    .from(sessionsQr)
    .where(eq(sessionsQr.id, jeton.sessionId))
    .limit(1);
  if (!session || session.jeton !== params.jeton || session.seanceId !== jeton.seanceId) {
    return erreur("QR_INVALIDE");
  }
  if (session.statut === "EXPIREE") return erreur("QR_EXPIRE");
  if (session.statut === "CLOTUREE") return erreur("QR_REUTILISE");
  if (session.nonce !== jeton.nonce) return erreur("QR_REUTILISE");

  const complete = await chargerSeanceComplete(session.seanceId);
  if (!complete) return erreur("PRESENCE_INTROUVABLE");
  const refusSeance = verifierOuvertureSeance(complete.seance.statut);
  if (refusSeance) return erreur(refusSeance.code);

  const refusParticipant = await verifierParticipant({
    utilisateurId: params.acteur.id,
    role: params.acteur.role,
    seance: {
      id: complete.seance.id,
      ecueId: complete.seance.ecueId,
      groupeId: complete.seance.groupeId,
      dateSeance: complete.seance.dateSeance,
      encadrantId: complete.seance.encadrantId,
    },
  });
  if (refusParticipant) return erreur(refusParticipant.code);

  const evaluation = evaluerPosition(
    {
      latitude: params.latitude,
      longitude: params.longitude,
      accuracy: params.accuracy,
    },
    complete.site,
  );
  if (evaluation.codeRefus) {
    return erreur(evaluation.codeRefus, {
      distance_m: evaluation.distanceM,
      rayon_m: evaluation.rayonM,
      accuracy_m: params.accuracy ?? null,
      verdict: evaluation.verdict,
    });
  }

  const result = await db.transaction(async (tx) => {
    await tx.execute(
      sql`select pg_advisory_xact_lock(${complete.seance.id * 1000000 + params.acteur.id})`,
    );
    const existants = await tx
      .select({ id: pointages.id, statut: pointages.statut })
      .from(pointages)
      .where(
        and(
          eq(pointages.seanceId, complete.seance.id),
          eq(pointages.utilisateurId, params.acteur.id),
        ),
      );
    const ouvert = existants.find((p) => p.statut === "EN_COURS");
    if (ouvert) return { double: true as const, pointageId: ouvert.id };

    const debut = debutSeanceEnDate(complete.seance.dateSeance, complete.seance.heureDebut);
    const entree = new Date();
    const anomalies: string[] = [];
    if (evaluation.verdict === "HORS_PERIMETRE") anomalies.push("HORS_GEOFENCE_ENTREE");
    if (evaluation.precision === "POSITION_IMPRECISE") anomalies.push("POSITION_IMPRECISE");

    const [cree] = await tx
      .insert(pointages)
      .values({
        seanceId: complete.seance.id,
        utilisateurId: params.acteur.id,
        typeParticipant: params.acteur.role === "ADMIN" ? "ETUDIANT" : params.acteur.role,
        sessionIdQr: session.id,
        statut: "EN_COURS",
        statutAssiduite: statutAssiduiteDepuis(entree, debut),
        mode: "QR_AUTOMATIQUE",
        sourceEntree: "BADGE_ENTREE",
        timestampEntree: entree,
        timestampClient: params.timestampClient ? new Date(params.timestampClient) : null,
        latitude: params.latitude ?? null,
        longitude: params.longitude ?? null,
        accuracyM: params.accuracy ?? null,
        distanceM: evaluation.distanceM,
        verdictGeofence: evaluation.verdict,
        precisionPosition: evaluation.precision,
        deviceId: params.deviceId ?? null,
        lastHeartbeatAt: entree,
        anomalies,
      })
      .returning({ id: pointages.id, statut: pointages.statut });

    await journaliser({
      auteurId: params.acteur.id,
      auteurNom: params.acteur.nom,
      entite: "pointage",
      entiteId: cree.id,
      action: "BADGE_ENTREE_QR",
      nouvelleValeur: {
        mode: "QR_AUTOMATIQUE",
        verdict: evaluation.verdict,
        distance_m: evaluation.distanceM,
      },
    });

    return { double: false as const, pointageId: cree.id, statut: cree.statut };
  });

  if ("double" in result && result.double) {
    return erreur("DOUBLE_ENTREE", { pointage_id: result.pointageId });
  }

  const [pointage] = await db
    .select()
    .from(pointages)
    .where(eq(pointages.id, result.pointageId))
    .limit(1);

  return {
    ok: true,
    pointage: {
      id: pointage.id,
      statut: pointage.statut,
      mode: "QR_AUTOMATIQUE",
      timestampEntree: pointage.timestampEntree,
    },
    seance: {
      id: complete.seance.id,
      libelle: `${complete.ecue.code} — ${complete.ecue.intitule}`,
      dateSeance: complete.seance.dateSeance,
      heureDebut: complete.seance.heureDebut,
      heureFin: complete.seance.heureFin,
      salle: complete.seance.salle,
    },
    evaluation,
  };
}

/* ------------------------------------------------------------------ */
/* 2. Heartbeat                                                        */
/* ------------------------------------------------------------------ */

export async function enregistrerHeartbeat(params: {
  jeton?: string | null;
  pointageId: number;
  acteur: Acteur;
  latitude?: number | null;
  longitude?: number | null;
  accuracy?: number | null;
}): Promise<
  Resultat<{
    heartbeat: { id: number; verdict: string; distanceM: number | null; horodatage: Date };
    pointage: { id: number; statut: string; outsideGeofenceCount: number; anomalies: string[] };
    evaluation: EvaluationPosition;
  }>
> {
  if (params.jeton) {
    const jeton = verifierJeton(params.jeton);
    if (!jeton.valide) return erreur(jeton.code);
  }
  if (!Number.isFinite(params.pointageId) || params.pointageId <= 0) {
    return erreur("REQUETE_INVALIDE");
  }

  const [pointage] = await db
    .select()
    .from(pointages)
    .where(eq(pointages.id, params.pointageId))
    .limit(1);
  if (!pointage) return erreur("PRESENCE_INTROUVABLE");
  if (pointage.statut !== "EN_COURS") return erreur("HEARTBEAT_INTERROMPU");
  if (pointage.utilisateurId !== params.acteur.id) return erreur("UTILISATEUR_NON_AUTORISE");

  const complete = await chargerSeanceComplete(pointage.seanceId);
  if (!complete) return erreur("PRESENCE_INTROUVABLE");
  const refusSeance = verifierOuvertureSeance(complete.seance.statut);
  if (refusSeance) return erreur(refusSeance.code);

  const evaluation = evaluerPosition(
    {
      latitude: params.latitude,
      longitude: params.longitude,
      accuracy: params.accuracy,
    },
    complete.site,
  );

  const horsPerimetre = evaluation.verdict === "HORS_PERIMETRE";
  const anomalies = new Set<string>(pointage.anomalies ?? []);
  if (horsPerimetre) anomalies.add("HEARTBEAT_HORS_GEOFENCE");
  if (evaluation.verdict === "POSITION_ABSENTE") anomalies.add("HEARTBEAT_POSITION_ABSENTE");

  const hb = await db.transaction(async (tx) => {
    const [cree] = await tx
      .insert(heartbeats)
      .values({
        pointageId: pointage.id,
        seanceId: pointage.seanceId,
        utilisateurId: pointage.utilisateurId,
        latitude: params.latitude ?? null,
        longitude: params.longitude ?? null,
        accuracyM: params.accuracy ?? null,
        distanceM: evaluation.distanceM,
        verdict: evaluation.verdict,
      })
      .returning({ id: heartbeats.id, horodatage: heartbeats.horodatage });

    await tx
      .update(pointages)
      .set({
        lastHeartbeatAt: new Date(),
        outsideGeofenceCount:
          pointage.outsideGeofenceCount + (horsPerimetre ? 1 : 0),
        anomalies: Array.from(anomalies),
        latitude: params.latitude ?? pointage.latitude,
        longitude: params.longitude ?? pointage.longitude,
        accuracyM: params.accuracy ?? pointage.accuracyM,
        distanceM: evaluation.distanceM ?? pointage.distanceM,
      })
      .where(eq(pointages.id, pointage.id));

    return cree;
  });

  return {
    ok: true,
    heartbeat: {
      id: hb.id,
      verdict: evaluation.verdict,
      distanceM: evaluation.distanceM,
      horodatage: hb.horodatage,
    },
    pointage: {
      id: pointage.id,
      statut: pointage.statut,
      outsideGeofenceCount: pointage.outsideGeofenceCount + (horsPerimetre ? 1 : 0),
      anomalies: Array.from(anomalies),
    },
    evaluation,
  };
}

/* ------------------------------------------------------------------ */
/* 3. Sortie                                                           */
/* ------------------------------------------------------------------ */

export async function enregistrerSortie(params: {
  pointageId: number;
  acteur: Acteur;
  source?: "BADGE_SORTIE" | "SORTIE_AUTOMATIQUE_FIN_SEANCE";
  latitude?: number | null;
  longitude?: number | null;
  accuracy?: number | null;
}): Promise<
  Resultat<{
    pointage: {
      id: number;
      statut: string;
      timestampSortie: Date;
      dureeMinutes: number;
      statutAssiduite: StatutAssiduite | null;
    };
  }>
> {
  if (!Number.isFinite(params.pointageId) || params.pointageId <= 0) {
    return erreur("REQUETE_INVALIDE");
  }
  const [pointage] = await db
    .select()
    .from(pointages)
    .where(eq(pointages.id, params.pointageId))
    .limit(1);
  if (!pointage) return erreur("PRESENCE_INTROUVABLE");
  if (pointage.utilisateurId !== params.acteur.id && params.acteur.role !== "ADMIN") {
    return erreur("UTILISATEUR_NON_AUTORISE");
  }
  if (pointage.statut !== "EN_COURS") return erreur("SORTIE_SANS_ENTREE");

  const sortie = new Date();
  const duree = Math.max(
    0,
    Math.round((sortie.getTime() - pointage.timestampEntree.getTime()) / 60000),
  );
  const source = params.source ?? "BADGE_SORTIE";
  const statut = source === "SORTIE_AUTOMATIQUE_FIN_SEANCE" ? "SORTIE_AUTO" : "TERMINE";

  await db
    .update(pointages)
    .set({
      timestampSortie: sortie,
      dureeMinutes: duree,
      sourceSortie: source,
      statut,
    })
    .where(eq(pointages.id, pointage.id));

  await journaliser({
    auteurId: params.acteur.id,
    auteurNom: params.acteur.nom,
    entite: "pointage",
    entiteId: pointage.id,
    action: source === "BADGE_SORTIE" ? "BADGE_SORTIE" : "SORTIE_AUTOMATIQUE_FIN_SEANCE",
    ancienneValeur: { statut: pointage.statut },
    nouvelleValeur: { statut, duree_minutes: duree },
  });

  return {
    ok: true,
    pointage: {
      id: pointage.id,
      statut,
      timestampSortie: sortie,
      dureeMinutes: duree,
      statutAssiduite: pointage.statutAssiduite as StatutAssiduite | null,
    },
  };
}

/* ------------------------------------------------------------------ */
/* 4. Émargement manuel (exception RBAC + motif + audit)               */
/* ------------------------------------------------------------------ */

export async function emargementManuel(params: {
  acteur: Acteur;
  seanceId: number;
  utilisateurId: number;
  motif: string;
  commentaire?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  accuracy?: number | null;
}): Promise<
  Resultat<{
    pointage: { id: number; mode: ModeBadgeage; motifManuel: string; timestampEntree: Date };
  }>
> {
  if (!peut(params.acteur, "presence.emargement_manuel")) {
    return erreur("UTILISATEUR_NON_AUTORISE");
  }
  if (
    !Number.isFinite(params.seanceId) ||
    params.seanceId <= 0 ||
    !Number.isFinite(params.utilisateurId) ||
    params.utilisateurId <= 0
  ) {
    return erreur("REQUETE_INVALIDE");
  }
  if (!params.motif) return erreur("MOTIF_ABSENT");
  if (
    params.motif === "AUTRE" &&
    !(params.commentaire && params.commentaire.trim().length > 0)
  ) {
    return erreur("MOTIF_AUTRE_SANS_COMMENTAIRE");
  }

  const complete = await chargerSeanceComplete(params.seanceId);
  if (!complete) return erreur("PRESENCE_INTROUVABLE");
  const refusSeance = verifierOuvertureSeance(complete.seance.statut);
  if (refusSeance) return erreur(refusSeance.code);

  // Un enseignant n'émarge que sur ses propres séances ; un encadrant sur ses
  // missions ; l'administration sur l'ensemble.
  if (params.acteur.role === "ENSEIGNANT") {
    const aff = await db
      .select()
      .from(affectationsPedagogiques)
      .where(
        and(
          eq(affectationsPedagogiques.utilisateurId, params.acteur.id),
          eq(affectationsPedagogiques.ecueId, complete.seance.ecueId),
          eq(affectationsPedagogiques.groupeId, complete.seance.groupeId),
        ),
      );
    if (aff.length === 0 && complete.seance.enseignantId !== params.acteur.id) {
      return erreur("UTILISATEUR_NON_AUTORISE");
    }
  }
  if (params.acteur.role === "ENCADRANT") {
    const missions = await db
      .select()
      .from(missionsEncadrants)
      .where(
        and(
          eq(missionsEncadrants.utilisateurId, params.acteur.id),
          eq(missionsEncadrants.actif, true),
        ),
      );
    const couvrante = missions.some(
      (m) =>
        m.dateDebut <= complete.seance.dateSeance &&
        m.dateFin >= complete.seance.dateSeance &&
        (m.groupeId === null || m.groupeId === complete.seance.groupeId),
    );
    if (!couvrante && complete.seance.encadrantId !== params.acteur.id) {
      return erreur("UTILISATEUR_NON_AUTORISE");
    }
  }

  const [cible] = await db
    .select()
    .from(utilisateurs)
    .where(eq(utilisateurs.id, params.utilisateurId))
    .limit(1);
  if (!cible) return erreur("PRESENCE_INTROUVABLE");

  const evaluation = evaluerPosition(
    {
      latitude: params.latitude,
      longitude: params.longitude,
      accuracy: params.accuracy,
    },
    complete.site,
  );

  return db.transaction(async (tx) => {
    await tx.execute(
      sql`select pg_advisory_xact_lock(${complete.seance.id * 1000000 + params.utilisateurId})`,
    );
    const existants = await tx
      .select()
      .from(pointages)
      .where(
        and(
          eq(pointages.seanceId, complete.seance.id),
          eq(pointages.utilisateurId, params.utilisateurId),
        ),
      );
    const ouvert = existants.find((p) => p.statut === "EN_COURS");
    if (ouvert) return erreur("DOUBLE_ENTREE", { pointage_id: ouvert.id });

    const entree = new Date();
    const debut = debutSeanceEnDate(complete.seance.dateSeance, complete.seance.heureDebut);
    const [cree] = await tx
      .insert(pointages)
      .values({
        seanceId: complete.seance.id,
        utilisateurId: params.utilisateurId,
        typeParticipant: cible.role as string,
        statut: "EN_COURS",
        statutAssiduite: statutAssiduiteDepuis(entree, debut),
        mode: "MANUEL",
        sourceEntree: "EMARGEMENT_MANUEL",
        timestampEntree: entree,
        latitude: params.latitude ?? null,
        longitude: params.longitude ?? null,
        accuracyM: params.accuracy ?? null,
        distanceM: evaluation.distanceM,
        verdictGeofence: evaluation.verdict,
        precisionPosition: evaluation.precision,
        anomalies: ["EMARGEMENT_MANUEL"],
        motifManuel: params.motif,
        commentaire: params.commentaire ?? null,
        auteurManuelId: params.acteur.id,
        auteurManuelNom: params.acteur.nom,
      })
      .returning({ id: pointages.id });

    await journaliser({
      auteurId: params.acteur.id,
      auteurNom: params.acteur.nom,
      entite: "pointage",
      entiteId: cree.id,
      action: "CREATION_EMARGEMENT_MANUEL",
      nouvelleValeur: {
        utilisateur: params.utilisateurId,
        mode: "MANUEL",
        motif: params.motif,
        commentaire: params.commentaire ?? null,
      },
      motif: params.motif,
    });

    return {
      ok: true as const,
      pointage: {
        id: cree.id,
        mode: "MANUEL" as ModeBadgeage,
        motifManuel: params.motif,
        timestampEntree: entree,
      },
    };
  });
}

/* ------------------------------------------------------------------ */
/* 5. Correction (non destructive)                                     */
/* ------------------------------------------------------------------ */

export async function corrigerPointage(params: {
  acteur: Acteur;
  pointageId: number;
  patch: {
    statutAssiduite?: StatutAssiduite;
    motifManuel?: MotifManuel | string;
    commentaire?: string;
  };
  motif: string;
}): Promise<Resultat<{ pointage: { id: number }; auditId: number }>> {
  if (!peut(params.acteur, "presence.corriger")) {
    return erreur("UTILISATEUR_NON_AUTORISE");
  }
  if (!params.motif || params.motif.trim().length === 0) {
    return erreur("MOTIF_ABSENT");
  }
  if (!Number.isFinite(params.pointageId) || params.pointageId <= 0) {
    return erreur("REQUETE_INVALIDE");
  }

  const [pointage] = await db
    .select()
    .from(pointages)
    .where(eq(pointages.id, params.pointageId))
    .limit(1);
  if (!pointage) return erreur("PRESENCE_INTROUVABLE");

  const ancienneValeur: Record<string, unknown> = {
    statut_assiduite: pointage.statutAssiduite,
    motif_manuel: pointage.motifManuel,
    commentaire: pointage.commentaire,
    statut: pointage.statut,
  };
  const nouvelleValeur: Record<string, unknown> = { ...ancienneValeur };
  const patch: Partial<typeof pointages.$inferInsert> = {};
  if (params.patch.statutAssiduite) {
    patch.statutAssiduite = params.patch.statutAssiduite;
    nouvelleValeur.statut_assiduite = params.patch.statutAssiduite;
  }
  if (params.patch.motifManuel) {
    patch.motifManuel = params.patch.motifManuel;
    nouvelleValeur.motif_manuel = params.patch.motifManuel;
  }
  if (params.patch.commentaire !== undefined) {
    patch.commentaire = params.patch.commentaire;
    nouvelleValeur.commentaire = params.patch.commentaire;
  }

  await db.update(pointages).set(patch).where(eq(pointages.id, pointage.id));

  await db.insert(auditLogs).values({
    auteurId: params.acteur.id,
    auteurNom: params.acteur.nom,
    entite: "pointage",
    entiteId: pointage.id,
    action: "CORRECTION_PRESENCE",
    ancienneValeur,
    nouvelleValeur,
    motif: params.motif,
  });

  const [audit] = await db
    .select({ id: auditLogs.id })
    .from(auditLogs)
    .where(eq(auditLogs.entiteId, pointage.id))
    .orderBy(sql`${auditLogs.id} desc`)
    .limit(1);

  return { ok: true, pointage: { id: pointage.id }, auditId: audit?.id ?? 0 };
}

/* ------------------------------------------------------------------ */
/* 6. Clôture de séance                                                */
/* ------------------------------------------------------------------ */

export async function cloreSeance(params: {
  acteur: Acteur;
  seanceId: number;
  motif?: string;
}): Promise<Resultat<{ seance: { id: number; statut: string }; clotures: number }>> {
  if (!peut(params.acteur, "presence.clore")) return erreur("UTILISATEUR_NON_AUTORISE");

  const [seance] = await db.select().from(seances).where(eq(seances.id, params.seanceId));
  if (!seance) return erreur("PRESENCE_INTROUVABLE");
  if (seance.statut === "TERMINEE") return erreur("SEANCE_TERMINEE");
  if (seance.statut === "ANNULEE") return erreur("SEANCE_ANNULEE");

  const clotures = await db.transaction(async (tx) => {
    const ouverts = await tx
      .select({ id: pointages.id })
      .from(pointages)
      .where(
        and(eq(pointages.seanceId, params.seanceId), eq(pointages.statut, "EN_COURS")),
      );

    // Aucune sortie humaine n'est inventée : la sortie est automatique de fin
    // de séance et le statut de processus reste distinct.
    for (const p of ouverts) {
      await tx
        .update(pointages)
        .set({
          timestampSortie: new Date(),
          sourceSortie: "SORTIE_AUTOMATIQUE_FIN_SEANCE",
          statut: "SORTIE_AUTO",
          dureeMinutes: sql`round(extract(epoch from (now() - ${pointages.timestampEntree})) / 60)`,
        })
        .where(eq(pointages.id, p.id));
    }

    await tx
      .update(sessionsQr)
      .set({ statut: "CLOTUREE" })
      .where(
        and(
          eq(sessionsQr.seanceId, params.seanceId),
          eq(sessionsQr.statut, "OUVERTE"),
        ),
      );

    await tx
      .update(seances)
      .set({ statut: "TERMINEE", majLe: new Date(), modifiePar: params.acteur.nom })
      .where(eq(seances.id, params.seanceId));

    return ouverts.length;
  });

  await journaliser({
    auteurId: params.acteur.id,
    auteurNom: params.acteur.nom,
    entite: "seance",
    entiteId: params.seanceId,
    action: "CLOTURE_SEANCE",
    ancienneValeur: { statut: seance.statut },
    nouvelleValeur: { statut: "TERMINEE", pointages_clotures: clotures },
    motif: params.motif ?? null,
  });

  return { ok: true, seance: { id: params.seanceId, statut: "TERMINEE" }, clotures };
}

/* ------------------------------------------------------------------ */
/* 7. Configuration geofence                                           */
/* ------------------------------------------------------------------ */

export async function enregistrerGeofence(params: {
  acteur: Acteur;
  siteId: number;
  patch: {
    geofenceLatitude?: number | null;
    geofenceLongitude?: number | null;
    geofenceRayonM?: number | null;
    precisionMaxM?: number;
    actif?: boolean;
    noteConfiguration?: string | null;
  };
}): Promise<Resultat<{ site: typeof refSites.$inferSelect }>> {
  if (!peut(params.acteur, "geofence.configurer")) {
    return erreur("UTILISATEUR_NON_AUTORISE");
  }
  const [avant] = await db.select().from(refSites).where(eq(refSites.id, params.siteId));
  if (!avant) return erreur("PRESENCE_INTROUVABLE");

  const [apres] = await db
    .update(refSites)
    .set({ ...params.patch, majLe: new Date() })
    .where(eq(refSites.id, params.siteId))
    .returning();

  await journaliser({
    auteurId: params.acteur.id,
    auteurNom: params.acteur.nom,
    entite: "ref_site",
    entiteId: params.siteId,
    action: "MODIFICATION_GEOFENCE",
    ancienneValeur: {
      latitude: avant.geofenceLatitude,
      longitude: avant.geofenceLongitude,
      rayon_m: avant.geofenceRayonM,
      precision_max_m: avant.precisionMaxM,
      actif: avant.actif,
    },
    nouvelleValeur: {
      latitude: apres.geofenceLatitude,
      longitude: apres.geofenceLongitude,
      rayon_m: apres.geofenceRayonM,
      precision_max_m: apres.precisionMaxM,
      actif: apres.actif,
    },
  });

  return { ok: true, site: apres };
}
