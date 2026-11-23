import { NextResponse } from "next/server";

import { getEmploiDuTemps } from "@/lib/get-injs/queries";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const JOURS: Record<number, string> = {
  1: "Lundi",
  2: "Mardi",
  3: "Mercredi",
  4: "Jeudi",
  5: "Vendredi",
  6: "Samedi",
};

function cellule(valeur: string | number | null | undefined): string {
  const texte = valeur === null || valeur === undefined ? "" : String(valeur);
  return `"${texte.replace(/"/g, '""')}"`;
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const nombre = (cle: string) => {
    const valeur = url.searchParams.get(cle);
    const n = Number(valeur);
    return valeur && !Number.isNaN(n) ? n : undefined;
  };
  const lignes = await getEmploiDuTemps({
    anneeCode: url.searchParams.get("anneeCode") ?? undefined,
    filiereCode: url.searchParams.get("filiereCode") ?? undefined,
    formationId: nombre("formationId"),
    niveau: url.searchParams.get("niveau") ?? undefined,
    groupeId: nombre("groupeId"),
    vagueId: nombre("vagueId"),
    semestre: nombre("semestre"),
    limit: 20000,
  });

  const entetes = [
    "Code EDT",
    "Semestre",
    "Niveau",
    "Filière",
    "Formation",
    "Groupe",
    "Module",
    "Code module",
    "Type",
    "Jour",
    "Début",
    "Fin",
    "Salle",
    "Capacité",
    "Effectif",
    "Enseignant",
    "Grade",
  ];
  const corps = lignes.map((l) =>
    [
      l.edtCode,
      l.semestre,
      l.niveau,
      l.filiere,
      l.formation,
      l.groupeCode ?? "Promotion",
      l.module,
      l.moduleCode,
      l.typeSeance,
      JOURS[l.jour] ?? l.jour,
      l.heureDebut,
      l.heureFin,
      l.salle,
      l.capacite,
      l.effectif,
      l.ennseignant ?? "À affecter",
      l.grade ?? "",
    ].map(cellule).join(";"),
  );
  const csv = `\uFEFF${[entetes.map(cellule).join(";"), ...corps].join("\r\n")}`;
  return new NextResponse(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="emplois-du-temps-injs-${new Date().toISOString().slice(0, 10)}.csv"`,
    },
  });
}
