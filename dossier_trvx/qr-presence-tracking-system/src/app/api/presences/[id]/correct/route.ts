/**
 * POST /api/presences/{id}/correct/ — correction non destructive.
 * L'ancienne valeur, la nouvelle valeur, l'auteur, la date et le motif sont
 * conservés dans le journal d'audit.
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, lireCorps, reponseErreur } from "@/lib/api";
import { corrigerPointage } from "@/lib/services";
import type { StatutAssiduite } from "@/lib/domain";

export async function POST(
  req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const { id } = await context.params;
  const corps = await lireCorps<{
    statut_assiduite: StatutAssiduite;
    motif_manuel: string;
    commentaire: string;
    motif: string;
  }>(req);

  const resultat = await corrigerPointage({
    acteur,
    pointageId: Number(id),
    patch: {
      statutAssiduite: corps.statut_assiduite,
      motifManuel: corps.motif_manuel,
      commentaire: corps.commentaire,
    },
    motif: String(corps.motif ?? ""),
  });

  if (estErreur(resultat)) return reponseErreur(resultat);
  return NextResponse.json(resultat);
}
