/**
 * GET /api/presences/{id}/ — détail d'un pointage (sans coordonnées brutes).
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
  const [ligne] = await db
    .select({
      id: pointages.id,
      seanceId: pointages.seanceId,
      matricule: utilisateurs.matricule,
      nom: utilisateurs.nom,
      prenom: utilisateurs.prenom,
      typeParticipant: pointages.typeParticipant,
      statut: pointages.statut,
      statutAssiduite: pointages.statutAssiduite,
      mode: pointages.mode,
      sourceEntree: pointages.sourceEntree,
      sourceSortie: pointages.sourceSortie,
      timestampEntree: pointages.timestampEntree,
      timestampSortie: pointages.timestampSortie,
      dureeMinutes: pointages.dureeMinutes,
      distanceM: pointages.distanceM,
      accuracyM: pointages.accuracyM,
      verdictGeofence: pointages.verdictGeofence,
      precisionPosition: pointages.precisionPosition,
      motifManuel: pointages.motifManuel,
      commentaire: pointages.commentaire,
      auteurManuelNom: pointages.auteurManuelNom,
      anomalies: pointages.anomalies,
    })
    .from(pointages)
    .innerJoin(utilisateurs, eq(pointages.utilisateurId, utilisateurs.id))
    .where(eq(pointages.id, Number(id)));

  if (!ligne) {
    return NextResponse.json(
      {
        ok: false,
        code: "PRESENCE_INTROUVABLE",
        message: "Présence introuvable.",
        explication: "Aucun pointage ne correspond à cet identifiant.",
        action_recommandee: "Rafraîchir la liste des présences.",
      },
      { status: 404 },
    );
  }
  return NextResponse.json(ligne);
}
