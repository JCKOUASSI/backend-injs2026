/**
 * GET /api/presences/session/{id}/ — présences d'une séance.
 * Équivalent contractuel de /api/presences/{seance}/session/.
 */
import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";

import { db } from "@/db";
import { pointages, utilisateurs } from "@/db/schema";
import { acteurRequis, estErreur, reponseErreur } from "@/lib/api";

export async function GET(
  req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const { id } = await context.params;
  const lignes = await db
    .select({
      id: pointages.id,
      utilisateurId: pointages.utilisateurId,
      matricule: utilisateurs.matricule,
      nom: utilisateurs.prenom,
      typeParticipant: pointages.typeParticipant,
      statut: pointages.statut,
      statutAssiduite: pointages.statutAssiduite,
      mode: pointages.mode,
      timestampEntree: pointages.timestampEntree,
      timestampSortie: pointages.timestampSortie,
      verdictGeofence: pointages.verdictGeofence,
      motifManuel: pointages.motifManuel,
      anomalies: pointages.anomalies,
    })
    .from(pointages)
    .innerJoin(utilisateurs, eq(pointages.utilisateurId, utilisateurs.id))
    .where(eq(pointages.seanceId, Number(id)));

  return NextResponse.json({ count: lignes.length, results: lignes });
}
