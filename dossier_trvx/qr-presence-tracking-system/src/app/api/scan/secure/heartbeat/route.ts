/**
 * POST /api/scan/secure/heartbeat/ — signal périodique pendant la séance.
 * Une sortie temporaire du périmètre n'annule jamais une présence validée :
 * elle génère une anomalie HEARTBEAT_HORS_GEOFENCE.
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, lireCorps, reponseErreur } from "@/lib/api";
import { enregistrerHeartbeat } from "@/lib/services";

export async function POST(req: Request) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const corps = await lireCorps<{
    jeton: string;
    pointage_id: number;
    latitude: number;
    longitude: number;
    accuracy: number;
  }>(req);

  const resultat = await enregistrerHeartbeat({
    jeton: corps.jeton ?? null,
    pointageId: Number(corps.pointage_id),
    acteur,
    latitude: corps.latitude ?? null,
    longitude: corps.longitude ?? null,
    accuracy: corps.accuracy ?? null,
  });

  if (estErreur(resultat)) return reponseErreur(resultat);
  return NextResponse.json(resultat);
}
