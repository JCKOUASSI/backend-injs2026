/**
 * GET /api/presences/ — historique filtrable des présences.
 * La latitude/longitude n'est jamais exposée : seule la mesure de conformité
 * (distance, verdict, précision) est restituée.
 */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, reponseErreur } from "@/lib/api";
import { chargerPresences } from "@/lib/queries";

export async function GET(req: Request) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const url = new URL(req.url);
  const p = url.searchParams;

  const lignes = await chargerPresences({
    typeParticipant: p.get("type_participant") ?? undefined,
    seanceId: p.get("seance_id") ? Number(p.get("seance_id")) : undefined,
    groupe: p.get("groupe") ?? undefined,
    ecue: p.get("ecue") ?? undefined,
    mode: p.get("mode") ?? undefined,
    nom: p.get("nom") ?? undefined,
  });

  return NextResponse.json({ count: lignes.length, results: lignes });
}
