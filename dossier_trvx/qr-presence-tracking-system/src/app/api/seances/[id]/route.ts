/**
 * GET /api/seances/{id}/ — fiche séance : contexte LMD, session QR,
 * attendus, présences et métriques de tableau de bord.
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, reponseErreur } from "@/lib/api";
import { chargerSeanceDetail } from "@/lib/queries";

export async function GET(
  req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const { id } = await context.params;
  const detail = await chargerSeanceDetail(Number(id));
  if (!detail) {
    return NextResponse.json(
      {
        ok: false,
        code: "PRESENCE_INTROUVABLE",
        message: "Séance introuvable.",
        explication: "Aucune séance ne correspond à cet identifiant.",
        action_recommandee: "Vérifier l'identifiant de séance.",
      },
      { status: 404 },
    );
  }
  return NextResponse.json(detail);
}
