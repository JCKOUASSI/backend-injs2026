/**
 * POST /api/seances/{id}/autoclore/ — clôture de séance.
 * QR fermés, heartbeat stoppé, sorties automatiques, présence clôturée.
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, lireCorps, reponseErreur } from "@/lib/api";
import { cloreSeance } from "@/lib/services";

export async function POST(
  req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const { id } = await context.params;
  const corps = await lireCorps<{ motif: string }>(req);

  const resultat = await cloreSeance({
    acteur,
    seanceId: Number(id),
    motif: corps.motif,
  });

  if (estErreur(resultat)) return reponseErreur(resultat);
  return NextResponse.json(resultat);
}
