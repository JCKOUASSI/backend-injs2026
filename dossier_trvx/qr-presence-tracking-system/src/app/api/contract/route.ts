/**
 * GET /api/contract/ — contrat d'interopérabilité du module Présences.
 * Documenté pour le futur module Flutter/PWA et pour l'OpenAPI.
 */
import { NextResponse } from "next/server";

import { ERREURS, ETATS_BADGEAGE, MOTIFS_MANUELS, STATUTS_ASSIDUITE, STATUTS_POINTAGE } from "@/lib/domain";

export const dynamic = "force-dynamic";

const ENDPOINTS = [
  {
    methode: "POST",
    url: "/api/scan/secure/",
    objet: "Badgeage automatique par QR (entrée)",
    corps: ["jeton", "latitude", "longitude", "accuracy", "device_id", "timestamp_client"],
    retour: ["pointage", "seance", "evaluation"],
  },
  {
    methode: "POST",
    url: "/api/scan/secure/heartbeat/",
    objet: "Signal périodique pendant la séance",
    corps: ["jeton", "pointage_id", "latitude", "longitude", "accuracy"],
    retour: ["heartbeat", "pointage", "evaluation"],
  },
  {
    methode: "POST",
    url: "/api/scan/secure/exit/",
    objet: "Badgeage de sortie",
    corps: ["pointage_id", "source", "latitude", "longitude", "accuracy"],
    retour: ["pointage"],
  },
  {
    methode: "POST",
    url: "/api/presences/manual/",
    objet: "Émargement manuel (RBAC + motif obligatoire)",
    corps: ["seance_id", "utilisateur_id", "motif", "commentaire"],
    retour: ["pointage"],
  },
  {
    methode: "POST",
    url: "/api/presences/{id}/correct/",
    objet: "Correction non destructive (audit ancienne/nouvelle valeur)",
    corps: ["statut_assiduite", "motif_manuel", "commentaire", "motif"],
    retour: ["pointage", "auditId"],
  },
  {
    methode: "GET",
    url: "/api/presences/",
    objet: "Historique filtrable",
    filtres: ["type_participant", "seance_id", "groupe", "ecue", "mode", "nom"],
  },
  { methode: "GET", url: "/api/presences/{id}/", objet: "Détail d'un pointage" },
  { methode: "GET", url: "/api/presences/session/{id}/", objet: "Présences d'une séance" },
  { methode: "GET", url: "/api/presences/actor/{id}/", objet: "Historique d'un participant" },
  {
    methode: "POST",
    url: "/api/seances/{id}/qr/",
    objet: "Émission / rotation de la session QR",
    corps: ["duree_secondes"],
  },
  {
    methode: "POST",
    url: "/api/seances/{id}/autoclore/",
    objet: "Clôture de séance (QR fermés, sorties automatiques)",
    corps: ["motif"],
  },
  {
    methode: "GET",
    url: "/api/seances/{id}/",
    objet: "Fiche séance + métriques de tableau de bord",
  },
  {
    methode: "GET / PUT",
    url: "/api/config/geofence/",
    objet: "Configuration du périmètre (site, latitude, longitude, rayon, actif)",
  },
  { methode: "GET", url: "/api/audit/", objet: "Journal d'audit" },
];

export async function GET() {
  return NextResponse.json({
    module: "GET INJS APP — Présences QR + Géolocalisation",
    version: "1.0",
    principe:
      "Le serveur est l'autorité finale. Le client transmet une mesure (latitude, longitude, accuracy) et jamais un verdict de présence.",
    entetes: {
      "x-acteur-id": "Identifiant utilisateur du référentiel (démonstration). En production : JWT.",
    },
    endpoints: ENDPOINTS,
    codes_erreur: Object.values(ERREURS).map(
      ({ code, message, explication, action_recommandee }) => ({
        code,
        message,
        explication,
        action_recommandee,
      }),
    ),
    statuts_pointage: STATUTS_POINTAGE,
    statuts_assiduite: STATUTS_ASSIDUITE,
    motifs_emanuels: MOTIFS_MANUELS,
    etats_badgeage: ETATS_BADGEAGE,
  });
}
