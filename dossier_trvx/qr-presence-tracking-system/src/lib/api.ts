/** Utilitaires de route : corps JSON, acteur, réponses normalisées. */
import { NextResponse } from "next/server";

import { ERREURS, type Acteur, type ReponseErreur } from "./domain";
import { resolverActeur } from "./services";

export async function lireCorps<T>(req: Request): Promise<Partial<T>> {
  try {
    const data = await req.json();
    return (data ?? {}) as Partial<T>;
  } catch {
    return {} as Partial<T>;
  }
}

/**
 * Identifiants de démonstration transportés par en-tête :
 *   x-acteur-id : identifiant utilisateur du référentiel.
 * En production, l'identité vient du JWT Django/Keycloak : le contrôle métier
 * serveur, lui, ne change pas.
 */
export async function acteurDepuisRequete(req: Request): Promise<Acteur | null> {
  const entete = req.headers.get("x-acteur-id");
  return resolverActeur(entete);
}

export function reponseErreur(e: ReponseErreur) {
  const statut = ERREURS[e.code]?.http ?? 400;
  return NextResponse.json(e, { status: statut });
}

export async function acteurRequis(req: Request): Promise<Acteur | ReponseErreur> {
  const acteur = await acteurDepuisRequete(req);
  if (!acteur) {
    const base = ERREURS.UTILISATEUR_NON_AUTORISE;
    return { ok: false, ...base, code: base.code, message: base.message };
  }
  return acteur;
}

export function estErreur(v: unknown): v is ReponseErreur {
  return typeof v === "object" && v !== null && (v as ReponseErreur).ok === false;
}
