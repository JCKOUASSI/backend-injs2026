/**
 * POST /api/scan/secure/exit/ — badgeage de sortie.
 * Aucune sortie humaine n'est inventée : sans événement reçu, la sortie reste
 * automatique de fin de séance (SORTIE_AUTOMATIQUE_FIN_SEANCE).
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, lireCorps, reponseErreur } from "@/lib/api";
import { enregistrerSortie } from "@/lib/services";

export async function POST(req: Request) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const corps = await lireCorps<{
    pointage_id: number;
    source: "BADGE_SORTIE" | "SORTIE_AUTOMATIQUE_FIN_SEANCE";
    latitude: number;
    longitude: number;
    accuracy: number;
  }>(req);

  const resultat = await enregistrerSortie({
    pointageId: Number(corps.pointage_id),
    acteur,
    source: corps.source ?? "BADGE_SORTIE",
    latitude: corps.latitude ?? null,
    longitude: corps.longitude ?? null,
    accuracy: corps.accuracy ?? null,
  });

  if (estErreur(resultat)) return reponseErreur(resultat);
  return NextResponse.json(resultat);
}
