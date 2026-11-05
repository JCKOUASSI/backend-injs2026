/**
 * POST /api/presences/manual/ — émargement manuel (exception RBAC + motif).
 * Toute présence manuelle est auditable : auteur, date, participant, séance,
 * motif, commentaire, mode = MANUEL.
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, lireCorps, reponseErreur } from "@/lib/api";
import { emargementManuel } from "@/lib/services";

export async function POST(req: Request) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const corps = await lireCorps<{
    seance_id: number;
    utilisateur_id: number;
    motif: string;
    commentaire: string;
    latitude: number;
    longitude: number;
    accuracy: number;
  }>(req);

  const resultat = await emargementManuel({
    acteur,
    seanceId: Number(corps.seance_id),
    utilisateurId: Number(corps.utilisateur_id),
    motif: String(corps.motif ?? ""),
    commentaire: corps.commentaire ?? null,
    latitude: corps.latitude ?? null,
    longitude: corps.longitude ?? null,
    accuracy: corps.accuracy ?? null,
  });

  if (estErreur(resultat)) return reponseErreur(resultat);
  return NextResponse.json(resultat, { status: 201 });
}
