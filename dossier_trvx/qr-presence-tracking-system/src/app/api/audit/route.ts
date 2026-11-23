/** GET /api/audit/ — journal d'audit (corrections, émargements, clôtures). */
import { NextResponse } from "next/server";

import { acteurRequis, estErreur, reponseErreur } from "@/lib/api";
import { chargerAudit } from "@/lib/queries";

export async function GET(req: Request) {
  const acteur = await acteurRequis(req);
  if (estErreur(acteur)) return reponseErreur(acteur);

  const url = new URL(req.url);
  const limit = Number(url.searchParams.get("limit") ?? 100);
  return NextResponse.json({ results: await chargerAudit(limit) });
}
