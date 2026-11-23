/**
 * POST /api/seances/{id}/qr/ — émission / rotation de la session QR.
 * Une session est temporaire, signée, rattachée à la séance, et toute session
 * précédente est expirée (anti-rejeu).
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, lireCorps, reponseErreur } from "@/lib/api";
import { ouvrirSessionQr } from "@/lib/services";

export async function POST(
  req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const { id } = await context.params;
  const corps = await lireCorps<{ duree_secondes: number }>(req);

  const resultat = await ouvrirSessionQr({
    acteur,
    seanceId: Number(id),
    dureeSecondes: corps.duree_secondes ? Number(corps.duree_secondes) : undefined,
  });

  if (estErreur(resultat)) return reponseErreur(resultat);
  return NextResponse.json(resultat, { status: 201 });
}
