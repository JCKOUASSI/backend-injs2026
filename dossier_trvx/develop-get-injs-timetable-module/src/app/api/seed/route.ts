import { NextResponse } from "next/server";
import { count } from "drizzle-orm";

import { db } from "@/db";
import * as schema from "@/db/schema";
import { ensureSeeded } from "@/lib/get-injs/seed";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function POST() {
  try {
    await ensureSeeded();
    const [etudiants, groupes, salles, modules, enseignants, seances] = await Promise.all([
      db.select({ n: count() }).from(schema.etudiants),
      db.select({ n: count() }).from(schema.groupes),
      db.select({ n: count() }).from(schema.salles),
      db.select({ n: count() }).from(schema.modules),
      db.select({ n: count() }).from(schema.enseignants),
      db.select({ n: count() }).from(schema.seances),
    ]);
    return NextResponse.json({
      ok: true,
      module: "get-injs-app",
      compteurs: {
        etudiants: etudiants[0]?.n ?? 0,
        groupes: groupes[0]?.n ?? 0,
        salles: salles[0]?.n ?? 0,
        modules: modules[0]?.n ?? 0,
        enseignants: enseignants[0]?.n ?? 0,
        seances: seances[0]?.n ?? 0,
      },
    });
  } catch (erreur) {
    return NextResponse.json(
      { ok: false, erreur: erreur instanceof Error ? erreur.message : "Erreur d'initialisation" },
      { status: 500 },
    );
  }
}
