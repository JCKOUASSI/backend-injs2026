import { NextResponse } from "next/server";

import { importerEtudiants } from "@/lib/get-injs/import-service";
import { MODELE_CSV } from "../../../../get-injs-app/lib/import-parser";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const TAILLE_MAX = 15 * 1024 * 1024;

export async function POST(request: Request) {
  try {
    const formulaire = await request.formData();
    const fichier = formulaire.get("fichier");
    if (!(fichier instanceof File)) {
      return NextResponse.json({ ok: false, erreur: "Aucun fichier reçu." }, { status: 400 });
    }
    if (fichier.size === 0) {
      return NextResponse.json({ ok: false, erreur: "Le fichier est vide." }, { status: 400 });
    }
    if (fichier.size > TAILLE_MAX) {
      return NextResponse.json(
        { ok: false, erreur: "Fichier trop volumineux (15 Mo maximum)." },
        { status: 400 },
      );
    }
    const contenu = Buffer.from(await fichier.arrayBuffer());
    const resultat = await importerEtudiants({
      fichier: fichier.name,
      contenu,
      anneeCode: (formulaire.get("anneeCode") as string) || undefined,
      autoCreer: formulaire.get("autoCreer") !== "false",
      generer: formulaire.get("generer") === "true",
      generation: {
        inclureSamedi: formulaire.get("inclureSamedi") !== "false",
        semestre: formulaire.get("semestre") ? Number(formulaire.get("semestre")) : undefined,
      },
    });
    return NextResponse.json({ ok: true, resultat });
  } catch (erreur) {
    return NextResponse.json(
      { ok: false, erreur: erreur instanceof Error ? erreur.message : "Erreur d'import" },
      { status: 400 },
    );
  }
}

export async function GET() {
  return new NextResponse(MODELE_CSV, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": 'attachment; filename="modele-import-etudiants-injs.csv"',
    },
  });
}
