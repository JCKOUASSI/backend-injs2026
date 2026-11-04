import { NextResponse } from "next/server";

import { ensureSeeded } from "@/lib/get-injs/seed";
import { genererEtPersister, type DemandeGeneration } from "@/lib/get-injs/generation-service";
import { db } from "@/db";
import * as schema from "@/db/schema";
import { desc } from "drizzle-orm";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(request: Request) {
  try {
    await ensureSeeded();
    const corps = (await request.json()) as DemandeGeneration;
    const resultat = await genererEtPersister({
      anneeCode: corps.anneeCode,
      filiereCode: corps.filiereCode || undefined,
      formationId: corps.formationId ? Number(corps.formationId) : undefined,
      niveau: corps.niveau || undefined,
      groupeId: corps.groupeId ? Number(corps.groupeId) : undefined,
      semestre: corps.semestre ? Number(corps.semestre) : undefined,
      semestres: Array.isArray(corps.semestres) ? corps.semestres.map(Number) : undefined,
      inclureSamedi: corps.inclureSamedi ?? true,
      eviterPauseMidi: corps.eviterPauseMidi ?? false,
      maxSeancesParGroupe: corps.maxSeancesParGroupe ? Number(corps.maxSeancesParGroupe) : 30,
      seed: corps.seed ? Number(corps.seed) : 2026,
      publier: corps.publier ?? false,
      libelle: corps.libelle || undefined,
    });
    return NextResponse.json({ ok: true, resultat });
  } catch (erreur) {
    return NextResponse.json(
      { ok: false, erreur: erreur instanceof Error ? erreur.message : "Erreur de génération" },
      { status: 400 },
    );
  }
}

export async function GET() {
  try {
    await ensureSeeded();
    const runs = await db
      .select()
      .from(schema.generationRuns)
      .orderBy(desc(schema.generationRuns.demarreLe))
      .limit(20);
    return NextResponse.json({ ok: true, runs });
  } catch (erreur) {
    return NextResponse.json(
      { ok: false, erreur: erreur instanceof Error ? erreur.message : "Erreur" },
      { status: 500 },
    );
  }
}
