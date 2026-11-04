/**
 * POST /api/scan/secure/ — badgeage automatique par QR.
 * Le client n'envoie que la mesure (lat/lng/accuracy) : token, séance,
 * participant, geofence et anti-rejeu sont contrôlés côté serveur.
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, lireCorps, reponseErreur } from "@/lib/api";
import { consommerScan } from "@/lib/services";

export async function POST(req: Request) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const corps = await lireCorps<{
    jeton: string;
    latitude: number;
    longitude: number;
    accuracy: number;
    device_id: string;
    timestamp_client: string;
  }>(req);

  const resultat = await consommerScan({
    jeton: String(corps.jeton ?? ""),
    acteur,
    latitude: corps.latitude ?? null,
    longitude: corps.longitude ?? null,
    accuracy: corps.accuracy ?? null,
    deviceId: corps.device_id ?? null,
    timestampClient: corps.timestamp_client ?? null,
  });

  if (estErreur(resultat)) return reponseErreur(resultat);
  return NextResponse.json(resultat, { status: 201 });
}
