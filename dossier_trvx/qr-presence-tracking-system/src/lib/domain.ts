/**
 * GET INJS APP — noyau métier Présences QR + Géolocalisation.
 * Règles calquées sur backend-injs2026 :
 *   - presences/geofence.py  : haversine, rayon par défaut 200 m,
 *                              refus LOCATION_INACCURATE / OUT_OF_GEOFENCE ;
 *   - presences/models.py    : statuts de processus + statuts d'assiduité ;
 *   - formations/QRToken     : jeton temporaire signé, non prédictible.
 * Le serveur reste l'autorité finale : le client ne fournit QUE la mesure.
 */
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

/* ------------------------------------------------------------------ */
/* Rôles                                                               */
/* ------------------------------------------------------------------ */

export type Role = "ETUDIANT" | "ENSEIGNANT" | "ENCADRANT" | "ADMIN";

export const ROLES: Role[] = ["ETUDIANT", "ENSEIGNANT", "ENCADRANT", "ADMIN"];

export type TypeParticipant = "ETUDIANT" | "ENSEIGNANT" | "ENCADRANT";

export type ModeBadgeage = "QR_AUTOMATIQUE" | "MANUEL";

export type SourcePointage =
  | "BADGE_ENTREE"
  | "HEARTBEAT"
  | "BADGE_SORTIE"
  | "SORTIE_AUTOMATIQUE_FIN_SEANCE"
  | "EMARGEMENT_MANUEL";

/** presences.Pointage.Statut (processus de badgeage). */
export const STATUTS_POINTAGE = [
  "EN_COURS",
  "TERMINE",
  "FORCE_DFRC",
  "ABSENT_NON_BADGE",
  "HORS_LIGNE_SUSPECT",
  "SORTIE_AUTO",
] as const;
export type StatutPointage = (typeof STATUTS_POINTAGE)[number];

/** presences.Pointage.StatutAssiduite (résultat pédagogique). */
export const STATUTS_ASSIDUITE = [
  "PRESENT",
  "ABSENT",
  "RETARD",
  "ABSENCE_JUSTIFIEE",
  "EXCUSE",
  "NON_RENSEIGNE",
] as const;
export type StatutAssiduite = (typeof STATUTS_ASSIDUITE)[number];

/* ------------------------------------------------------------------ */
/* Codes d'erreur métier                                               */
/* ------------------------------------------------------------------ */

export interface ErreurMetier {
  code: string;
  message: string;
  explication: string;
  action_recommandee: string;
  http: number;
}

export const ERREURS: Record<string, ErreurMetier> = {
  QR_INVALIDE: {
    code: "QR_INVALIDE",
    message: "QR code invalide.",
    explication:
      "La signature du jeton ne correspond pas ou le format attendu n'est pas respecté. Le QR peut être falsifié, tronqué ou provenir d'un autre système.",
    action_recommandee:
      "Régénérer le QR depuis la séance, puis rescanner. Si le refus persiste, procéder à un émargement manuel motivé.",
    http: 422,
  },
  QR_EXPIRE: {
    code: "QR_EXPIRE",
    message: "QR code expiré.",
    explication:
      "Le jeton de session a dépassé sa durée de validité. Un QR de session est temporaire par conception : il ne peut pas être conservé ni rejoué.",
    action_recommandee:
      "Demander à l'enseignant de rafraîchir le QR (rotation de session), puis rescanner immédiatement.",
    http: 422,
  },
  QR_REUTILISE: {
    code: "QR_REUTILISE",
    message: "QR code déjà consommé.",
    explication:
      "Ce jeton a déjà servi à ouvrir un pointage. La réutilisation d'un jeton consommé est un motif de suspicion de fraude (anti-rejeu).",
    action_recommandee:
      "Ne pas accepter le jeton. Contrôler l'identité du porteur et enregistrer un émargement manuel motivé si nécessaire.",
    http: 422,
  },
  QR_SEANCE_MISMATCH: {
    code: "QR_SEANCE_MISMATCH",
    message: "QR code non lié à cette séance.",
    explication:
      "Le jeton présenté a été émis pour une autre séance que celle demandée. Chaque session QR est strictement rattachée à une séance.",
    action_recommandee:
      "Scanner le QR affiché dans la salle concernée. Vérifier que la séance affichée sur l'écran correspond au cours en cours.",
    http: 422,
  },
  SEANCE_INACTIVE: {
    code: "SEANCE_INACTIVE",
    message: "Séance non ouverte au badgeage.",
    explication:
      "La séance n'est ni publiée ni en cours : elle est en brouillon, en simulation, en attente de validation ou annulée. Une séance non publiée ne peut pas ouvrir de session de présence.",
    action_recommandee:
      "Faire publier la séance par l'habilité (validation puis publication) avant tout badgeage.",
    http: 422,
  },
  SEANCE_TERMINEE: {
    code: "SEANCE_TERMINEE",
    message: "Séance terminée.",
    explication:
      "La séance est clôturée : plus aucun pointage, heartbeat ou sortie ne peut être accepté. Les données historiques sont conservées.",
    action_recommandee:
      "Aucune action de badgeage. En cas d'anomalie, passer par une correction motivée ou un rattrapage.",
    http: 422,
  },
  SEANCE_ANNULEE: {
    code: "SEANCE_ANNULEE",
    message: "Séance annulée.",
    explication:
      "La séance a été annulée. Une séance annulée n'accepte plus aucun pointage et conserve sa traçabilité d'annulation.",
    action_recommandee:
      "Vérifier la séance de remplacement liée à cette annulation et badger sur cette dernière.",
    http: 422,
  },
  UTILISATEUR_NON_AUTORISE: {
    code: "UTILISATEUR_NON_AUTORISE",
    message: "Utilisateur non autorisé.",
    explication:
      "L'utilisateur authentifié ne dispose pas de la permission métier requise pour cette opération. Le contrôle serveur fait foi, l'interface ne protège rien.",
    action_recommandee:
      "Faire débloquer la permission par un administrateur habilité (RBAC INJS-LMD).",
    http: 403,
  },
  ETUDIANT_NON_INSCRIT: {
    code: "ETUDIANT_NON_INSCRIT",
    message: "Étudiant non inscrit pour cette séance.",
    explication:
      "Aucune inscription administrative validée et en vigueur à la date de la séance n'a été trouvée pour cet utilisateur.",
    action_recommandee:
      "Vérifier l'inscription de l'étudiant (année académique, formation, parcours) ou passer par un émargement manuel motivé.",
    http: 422,
  },
  ETUDIANT_HORS_GROUPE: {
    code: "ETUDIANT_HORS_GROUPE",
    message: "Étudiant hors groupe de la séance.",
    explication:
      "L'étudiant est inscrit, mais son groupe pédagogique ne correspond pas au groupe de la séance scannée.",
    action_recommandee:
      "Scanner le QR de la séance du groupe de l'étudiant, ou corriger son affectation de groupe.",
    http: 422,
  },
  ENSEIGNANT_NON_AFFECTE: {
    code: "ENSEIGNANT_NON_AFFECTE",
    message: "Enseignant non affecté à cette séance.",
    explication:
      "Aucune affectation pédagogique ne relie cet enseignant à l'ECUE et au groupe de la séance. Le rapprochement se fait sur l'affectation, jamais sur le nom.",
    action_recommandee:
      "Enregistrer l'affectation pédagogique (ECUE + groupe + année) ou faire badger l'enseignant affecté.",
    http: 422,
  },
  ACTIVITE_NON_AUTORISEE: {
    code: "ACTIVITE_NON_AUTORISEE",
    message: "Activité non autorisée pour cet encadrant.",
    explication:
      "L'encadrant ne dispose d'aucune mission ou activité couvrant cette séance. Un encadrant n'est pas assimilable à un enseignant.",
    action_recommandee:
      "Enregistrer la mission d'encadrement couvrant la date et le groupe de la séance.",
    http: 422,
  },
  HORS_GEOFENCE: {
    code: "HORS_GEOFENCE",
    message: "Position hors du périmètre autorisé.",
    explication:
      "La distance calculée par le serveur entre la position déclarée et le site de la séance dépasse le rayon autorisé. La géolocalisation ne fait jamais foi seule : elle est combinée au QR et au contrôle serveur.",
    action_recommandee:
      "Se rapprocher de la salle de cours puis rescanner, ou justifier d'un déplacement (sortie pédagogique) par un émargement motivé.",
    http: 422,
  },
  GPS_INDISPONIBLE: {
    code: "GPS_INDISPONIBLE",
    message: "Position non disponible.",
    explication:
      "Aucune latitude/longitude n'a été fournie par le terminal, ou la mesure est inexploitable. Le contrôle de périmètre ne peut pas être effectué.",
    action_recommandee:
      "Activer la localisation du terminal et rescanner ; à défaut, émargement manuel motivé GPS_INDISPONIBLE.",
    http: 422,
  },
  PRECISION_GPS_INSUFFISANTE: {
    code: "PRECISION_GPS_INSUFFISANTE",
    message: "Précision GPS insuffisante.",
    explication:
      "L'incertitude annoncée par le terminal dépasse le seuil de précision configuré pour le site. La mesure est imprécise ou inexploitable.",
    action_recommandee:
      "Se placer à ciel ouvert, patienter quelques secondes pour stabiliser la position, puis rescanner.",
    http: 422,
  },
  DOUBLE_ENTREE: {
    code: "DOUBLE_ENTREE",
    message: "Entrée déjà enregistrée.",
    explication:
      "Un pointage est déjà ouvert pour ce participant sur cette séance. Une seconde entrée est refusée pour empêcher les doublons.",
    action_recommandee:
      "Aucune action : le pointage existant reste en cours. Utiliser le heartbeat ou la sortie.",
    http: 409,
  },
  SORTIE_SANS_ENTREE: {
    code: "SORTIE_SANS_ENTREE",
    message: "Sortie sans entrée.",
    explication:
      "Aucun pointage ouvert n'existe pour ce participant sur cette séance : une sortie ne peut pas être enregistrée.",
    action_recommandee:
      "Procéder d'abord à l'entrée (scan QR ou émargement), puis à la sortie.",
    http: 422,
  },
  HEARTBEAT_INTERROMPU: {
    code: "HEARTBEAT_INTERROMPU",
    message: "Heartbeat interrompu.",
    explication:
      "Aucun signal périodique n'a été reçu depuis la fenêtre de tolérance. La continuité de présence n'est plus attestée.",
    action_recommandee:
      "Rouvrir l'application de badgeage pour relancer le heartbeat, ou justifier l'interruption.",
    http: 422,
  },
  MOTIF_ABSENT: {
    code: "MOTIF_ABSENT",
    message: "Motif obligatoire manquant.",
    explication:
      "Tout émargement manuel est une exception : il doit être motivé pour être auditable.",
    action_recommandee: "Sélectionner un motif dans la liste configurée.",
    http: 422,
  },
  MOTIF_AUTRE_SANS_COMMENTAIRE: {
    code: "MOTIF_AUTRE_SANS_COMMENTAIRE",
    message: "Commentaire obligatoire pour le motif AUTRE.",
    explication:
      "Le motif AUTRE exige un commentaire explicite décrivant la situation, afin de garder une traçabilité exploitable.",
    action_recommandee: "Renseigner un commentaire précis puis valider.",
    http: 422,
  },
  PRESENCE_INTROUVABLE: {
    code: "PRESENCE_INTROUVABLE",
    message: "Présence introuvable.",
    explication: "Aucun pointage ne correspond à l'identifiant fourni.",
    action_recommandee: "Rafraîchir la liste des présences de la séance.",
    http: 404,
  },
  REQUETE_INVALIDE: {
    code: "REQUETE_INVALIDE",
    message: "Requête invalide.",
    explication: "Les champs obligatoires sont absents ou mal typés.",
    action_recommandee: "Compléter la requête conformément au contrat API.",
    http: 400,
  },
};

export interface ReponseErreur {
  ok: false;
  code: string;
  message: string;
  explication: string;
  action_recommandee: string;
  details?: Record<string, unknown>;
}

export function erreur(
  code: keyof typeof ERREURS | string,
  details?: Record<string, unknown>,
): ReponseErreur {
  const base = ERREURS[code] ?? ERREURS.REQUETE_INVALIDE;
  return {
    ok: false,
    code: base.code,
    message: base.message,
    explication: base.explication,
    action_recommandee: base.action_recommandee,
    details,
  };
}

/* ------------------------------------------------------------------ */
/* Géofence — calcul serveur (haversine), jamais une preuve client     */
/* ------------------------------------------------------------------ */

export const RAYON_DEFAUT_M = 200; // MOBILE_GEOFENCE_DEFAULT_RADIUS_M
export const PRECISION_MAX_DEFAUT_M = 50; // MOBILE_GEOFENCE_MAX_ACCURACY_M

export interface SiteGeofence {
  id: number;
  code: string;
  nom: string;
  actif: boolean;
  geofenceLatitude: number | null;
  geofenceLongitude: number | null;
  geofenceRayonM: number | null;
  precisionMaxM: number;
}

export type VerdictPosition =
  | "DANS_PERIMETRE"
  | "HORS_PERIMETRE"
  | "POSITION_IMPRECISE"
  | "POSITION_INEXPLOITABLE"
  | "POSITION_ABSENTE"
  | "SITE_NON_LOCALISE";

export type PrecisionPosition =
  | "POSITION_ACCEPTABLE"
  | "POSITION_IMPRECISE"
  | "POSITION_INEXPLOITABLE"
  | "POSITION_ABSENTE";

export interface MesurePosition {
  latitude?: number | null;
  longitude?: number | null;
  accuracy?: number | null;
}

export interface EvaluationPosition {
  verdict: VerdictPosition;
  precision: PrecisionPosition;
  distanceM: number | null;
  rayonM: number | null;
  controleEffectue: boolean;
  codeRefus?: "GPS_INDISPONIBLE" | "PRECISION_GPS_INSUFFISANTE" | "HORS_GEOFENCE";
}

/** Distance approximative en mètres (formule de haversine, cf. geofence.py). */
export function distanceMetres(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const rayonTerre = 6371000;
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLambda = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * rayonTerre * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function siteNonLocalise(site: SiteGeofence | null | undefined): boolean {
  return (
    !site ||
    site.geofenceLatitude === null ||
    site.geofenceLongitude === null ||
    !site.actif
  );
}

/**
 * Le client transmet latitude / longitude / accuracy. Il ne transmet JAMAIS
 * `inside_geofence` comme preuve : le verdict est calculé ici.
 */
export function evaluerPosition(
  mesure: MesurePosition,
  site: SiteGeofence | null | undefined,
): EvaluationPosition {
  const lat = mesure.latitude;
  const lng = mesure.longitude;
  const acc = mesure.accuracy ?? null;

  if (lat === null || lat === undefined || lng === null || lng === undefined) {
    return {
      verdict: "POSITION_ABSENTE",
      precision: "POSITION_ABSENTE",
      distanceM: null,
      rayonM: site?.geofenceRayonM ?? RAYON_DEFAUT_M,
      controleEffectue: false,
      codeRefus: "GPS_INDISPONIBLE",
    };
  }

  const seuil = site?.precisionMaxM ?? PRECISION_MAX_DEFAUT_M;
  let precision: PrecisionPosition = "POSITION_ACCEPTABLE";
  if (acc !== null && acc > seuil * 3) precision = "POSITION_INEXPLOITABLE";
  else if (acc !== null && acc > seuil) precision = "POSITION_IMPRECISE";

  if (siteNonLocalise(site)) {
    // Comportement historique du référentiel : site non géolocalisé → aucun contrôle.
    return {
      verdict: "SITE_NON_LOCALISE",
      precision,
      distanceM: null,
      rayonM: null,
      controleEffectue: false,
    };
  }

  const rayon = site!.geofenceRayonM ?? RAYON_DEFAUT_M;
  const distance = distanceMetres(
    lat,
    lng,
    site!.geofenceLatitude!,
    site!.geofenceLongitude!,
  );

  if (precision === "POSITION_INEXPLOITABLE") {
    return {
      verdict: "POSITION_INEXPLOITABLE",
      precision,
      distanceM: distance,
      rayonM: rayon,
      controleEffectue: true,
      codeRefus: "PRECISION_GPS_INSUFFISANTE",
    };
  }
  if (precision === "POSITION_IMPRECISE") {
    return {
      verdict: "POSITION_IMPRECISE",
      precision,
      distanceM: distance,
      rayonM: rayon,
      controleEffectue: true,
      codeRefus: "PRECISION_GPS_INSUFFISANTE",
    };
  }
  if (distance > rayon) {
    return {
      verdict: "HORS_PERIMETRE",
      precision,
      distanceM: distance,
      rayonM: rayon,
      controleEffectue: true,
      codeRefus: "HORS_GEOFENCE",
    };
  }
  return {
    verdict: "DANS_PERIMETRE",
    precision,
    distanceM: distance,
    rayonM: rayon,
    controleEffectue: true,
  };
}

/* ------------------------------------------------------------------ */
/* Session QR — jeton temporaire signé, anti-rejeu                     */
/* ------------------------------------------------------------------ */

const PREFIXE = "INJS1";

function secret(): string {
  return process.env.QR_SECRET ?? "INJS-DEV-QR-SECRET-A-REMPLACER";
}

export function creerNonce(): string {
  return randomBytes(12).toString("hex");
}

export function signature(payload: string): string {
  return createHmac("sha256", secret()).update(payload).digest("hex").slice(0, 32);
}

/** Jeton : INJS1.<seance>.<session>.<nonce>.<expirationEpoch>.<signature> */
export function signerJeton(params: {
  seanceId: number;
  sessionId: number;
  nonce: string;
  expirationEpoch: number;
}): string {
  const payload = `${PREFIXE}.${params.seanceId}.${params.sessionId}.${params.nonce}.${params.expirationEpoch}`;
  return `${payload}.${signature(payload)}`;
}

export type ResultatJeton =
  | {
      valide: true;
      seanceId: number;
      sessionId: number;
      nonce: string;
      expirationEpoch: number;
    }
  | { valide: false; code: "QR_INVALIDE" | "QR_EXPIRE" };

export function verifierJeton(
  jeton: string,
  maintenantEpoch: number = Math.floor(Date.now() / 1000),
): ResultatJeton {
  const parts = (jeton ?? "").trim().split(".");
  if (parts.length !== 6 || parts[0] !== PREFIXE) {
    return { valide: false, code: "QR_INVALIDE" };
  }
  const [prefixe, seanceRaw, sessionRaw, nonce, expRaw, sig] = parts;
  const payload = [prefixe, seanceRaw, sessionRaw, nonce, expRaw].join(".");
  const attendu = Buffer.from(signature(payload));
  const recu = Buffer.from(sig ?? "");
  if (attendu.length !== recu.length || !timingSafeEqual(attendu, recu)) {
    return { valide: false, code: "QR_INVALIDE" };
  }
  const expirationEpoch = Number(expRaw);
  const seanceId = Number(seanceRaw);
  const sessionId = Number(sessionRaw);
  if (
    !Number.isFinite(expirationEpoch) ||
    !Number.isFinite(seanceId) ||
    !Number.isFinite(sessionId)
  ) {
    return { valide: false, code: "QR_INVALIDE" };
  }
  if (expirationEpoch <= maintenantEpoch) {
    return { valide: false, code: "QR_EXPIRE" };
  }
  return {
    valide: true,
    seanceId,
    sessionId,
    nonce,
    expirationEpoch,
  };
}

export function hashJeton(jeton: string): string {
  return createHmac("sha256", secret()).update(jeton).digest("hex");
}

/* ------------------------------------------------------------------ */
/* RBAC — permissions INJS-LMD réutilisées (pas de nouveau système)    */
/* ------------------------------------------------------------------ */

export type Permission =
  | "presence.consulter"
  | "presence.consulter_toutes"
  | "presence.badger"
  | "presence.emargement_manuel"
  | "presence.corriger"
  | "presence.clore"
  | "session.qr.emettre"
  | "geofence.configurer"
  | "audit.consulter";

const PERMISSIONS_PAR_ROLE: Record<Role, Permission[]> = {
  ETUDIANT: ["presence.consulter", "presence.badger"],
  ENSEIGNANT: [
    "presence.consulter",
    "presence.badger",
    "presence.emargement_manuel",
    "presence.clore",
    "session.qr.emettre",
  ],
  ENCADRANT: [
    "presence.consulter",
    "presence.badger",
    "presence.emargement_manuel",
    "session.qr.emettre",
  ],
  ADMIN: [
    "presence.consulter",
    "presence.consulter_toutes",
    "presence.badger",
    "presence.emargement_manuel",
    "presence.corriger",
    "presence.clore",
    "session.qr.emettre",
    "geofence.configurer",
    "audit.consulter",
  ],
};

export interface Acteur {
  id: number;
  nom: string;
  role: Role;
}

export function permissions(role: Role): Permission[] {
  return PERMISSIONS_PAR_ROLE[role] ?? [];
}

export function peut(acteur: Acteur, permission: Permission): boolean {
  return permissions(acteur.role).includes(permission);
}

/* ------------------------------------------------------------------ */
/* Motifs d'émargement manuel                                          */
/* ------------------------------------------------------------------ */

export const MOTIFS_MANUELS = [
  { code: "QR_NON_LISIBLE", libelle: "QR non lisible", exigeCommentaire: false },
  { code: "GPS_INDISPONIBLE", libelle: "GPS indisponible", exigeCommentaire: false },
  { code: "PANNE_RESEAU", libelle: "Panne réseau", exigeCommentaire: false },
  {
    code: "PROBLEME_TECHNIQUE",
    libelle: "Problème technique",
    exigeCommentaire: false,
  },
  {
    code: "PARTICIPANT_PRESENT_SANS_BADGE",
    libelle: "Participant présent sans badge",
    exigeCommentaire: false,
  },
  { code: "AUTRE", libelle: "Autre", exigeCommentaire: true },
] as const;

export type MotifManuel = (typeof MOTIFS_MANUELS)[number]["code"];

/* ------------------------------------------------------------------ */
/* États d'affichage du poste de badgeage (contrat Flutter/PWA)        */
/* ------------------------------------------------------------------ */

export const ETATS_BADGEAGE = [
  "PRET_A_BADGER",
  "SCAN_EN_COURS",
  "VERIFICATION",
  "PRESENCE_VALIDEE",
  "PRESENCE_REFUSEE",
  "HEARTBEAT_ACTIF",
  "SEANCE_TERMINEE",
  "EN_ATTENTE_SYNCHRONISATION",
] as const;
export type EtatBadgeage = (typeof ETATS_BADGEAGE)[number];

export function intituleEtatBadgeage(état: EtatBadgeage): string {
  return état.replace(/_/g, " ");
}
