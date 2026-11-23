/**
 * GET /api/presences/actor/{id}/ — historique d'un participant
 * (étudiant, enseignant ou encadrant).
 */
import { NextResponse } from "next/server";
import { and, desc, eq } from "drizzle-orm";

import { db } from "@/db";
import { ecues, groupes, pointages, seances, utilisateurs } from "@/db/schema";
import { acteurRequis, estErreur, reponseErreur } from "@/lib/api";

export async function GET(
  req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const { id } = await context.params;
  const [personne] = await db
    .select()
    .from(utilisateurs)
    .where(eq(utilisateurs.id, Number(id)));
  if (!personne) {
    return NextResponse.json(
      {
        ok: false,
        code: "PRESENCE_INTROUVABLE",
        message: "Participant introuvable.",
        explication: "Aucun utilisateur ne correspond à cet identifiant.",
        action_recommandee: "Vérifier le matricule.",
      },
      { status: 404 },
    );
  }

  const lignes = await db
    .select({
      id: pointages.id,
      seance: ecues.code,
      ecueIntitule: ecues.intitule,
      groupe: groupes.code,
      dateSeance: seances.dateSeance,
      heureDebut: seances.heureDebut,
      heureFin: seances.heureFin,
      statut: pointages.statut,
      statutAssiduite: pointages.statutAssiduite,
      mode: pointages.mode,
      timestampEntree: pointages.timestampEntree,
      timestampSortie: pointages.timestampSortie,
      anomalies: pointages.anomalies,
    })
    .from(pointages)
    .innerJoin(seances, eq(pointages.seanceId, seances.id))
    .innerJoin(ecues, eq(seances.ecueId, ecues.id))
    .innerJoin(groupes, eq(seances.groupeId, groupes.id))
    .where(and(eq(pointages.utilisateurId, Number(id))))
    .orderBy(desc(pointages.timestampEntree));

  return NextResponse.json({
    participant: {
      id: personne.id,
      matricule: personne.matricule,
      nom: `${personne.prenom} ${personne.nom}`,
      role: personne.role,
    },
    count: lignes.length,
    results: lignes,
  });
}
