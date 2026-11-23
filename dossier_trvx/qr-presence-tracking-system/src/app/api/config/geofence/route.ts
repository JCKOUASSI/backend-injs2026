/**
 * GET / PUT /api/config/geofence/ — configuration du périmètre.
 * Aucune coordonnée n'est codée en dur : tout est explicite et audité.
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, lireCorps, reponseErreur } from "@/lib/api";
import { chargerSites } from "@/lib/queries";
import { enregistrerGeofence } from "@/lib/services";

export async function GET(req: Request) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);
  return NextResponse.json({ results: await chargerSites() });
}

export async function PUT(req: Request) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const corps = await lireCorps<{
    site_id: number;
    geofence_latitude: number | null;
    geofence_longitude: number | null;
    geofence_rayon_m: number | null;
    precision_max_m: number;
    actif: boolean;
    note_configuration: string;
  }>(req);

  const resultat = await enregistrerGeofence({
    acteur,
    siteId: Number(corps.site_id),
    patch: {
      geofenceLatitude: corps.geofence_latitude ?? null,
      geofenceLongitude: corps.geofence_longitude ?? null,
      geofenceRayonM: corps.geofence_rayon_m ?? null,
      precisionMaxM: corps.precision_max_m ? Number(corps.precision_max_m) : undefined,
      actif: corps.actif,
      noteConfiguration: corps.note_configuration ?? null,
    },
  });

  if (estErreur(resultat)) return reponseErreur(resultat);
  return NextResponse.json(resultat);
}
