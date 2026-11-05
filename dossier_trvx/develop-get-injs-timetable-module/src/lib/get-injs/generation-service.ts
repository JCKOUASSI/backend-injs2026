import { and, eq, inArray, sql } from "drizzle-orm";

import { db } from "@/db";
import * as schema from "@/db/schema";
import { referentiel } from "../../../get-injs-app/data/referentiel";
import {
  genererEmploiDuTemps,
  niveauDeSemestre,
  semestresDuNiveau,
} from "../../../get-injs-app/lib/engine";
import type {
  Affectation,
  EngineGroupe,
  EngineModule,
  GenerationResult,
} from "../../../get-injs-app/lib/types";

export type DemandeGeneration = {
  anneeCode?: string;
  filiereCode?: string;
  formationId?: number;
  niveau?: string;
  groupeId?: number;
  semestre?: number;
  semestres?: number[];
  inclureSamedi?: boolean;
  eviterPauseMidi?: boolean;
  maxSeancesParGroupe?: number;
  seed?: number;
  libelle?: string;
  publier?: boolean;
};

export type ResultatGeneration = {
  runId: number;
  edtId: number;
  edtCode: string;
  stats: GenerationResult["stats"];
  alertes: string[];
  nonPlacees: GenerationResult["nonPlacees"];
  classes: number;
  semestres: number[];
  anneeCode: string;
};

function chunk<T>(items: T[], taille: number): T[][] {
  const resultat: T[][] = [];
  for (let i = 0; i < items.length; i += taille) resultat.push(items.slice(i, i + taille));
  return resultat;
}

export async function genererEtPersister(demande: DemandeGeneration): Promise<ResultatGeneration> {
  const [annee] = await db
    .select()
    .from(schema.academicYears)
    .where(eq(schema.academicYears.code, demande.anneeCode ?? referentiel.activeYear))
    .limit(1);
  const anneeCible =
    annee ??
    (
      await db
        .select()
        .from(schema.academicYears)
        .orderBy(sql`${schema.academicYears.code} desc`)
        .limit(1)
    )[0];
  if (!anneeCible) throw new Error("Aucune année académique disponible : lancez l'initialisation.");

  const groupesDb = await db
    .select({
      id: schema.groupes.id,
      code: schema.groupes.code,
      formationId: schema.groupes.formationId,
      formationCode: schema.formations.code,
      niveau: schema.groupes.niveau,
      vagueId: schema.groupes.vagueId,
      effectif: schema.groupes.effectif,
      effectifCible: schema.groupes.effectifCible,
      filiereCode: schema.filieres.code,
    })
    .from(schema.groupes)
    .innerJoin(schema.formations, eq(schema.groupes.formationId, schema.formations.id))
    .innerJoin(schema.filieres, eq(schema.formations.filiereId, schema.filieres.id))
    .where(
      and(
        eq(schema.groupes.anneeId, anneeCible.id),
        demande.groupeId ? eq(schema.groupes.id, demande.groupeId) : undefined,
        demande.formationId ? eq(schema.groupes.formationId, demande.formationId) : undefined,
        demande.niveau ? eq(schema.groupes.niveau, demande.niveau) : undefined,
        demande.filiereCode ? eq(schema.filieres.code, demande.filiereCode) : undefined,
      ),
    )
    .orderBy(schema.groupes.code);

  if (groupesDb.length === 0) {
    throw new Error("Aucun groupe ne correspond au périmètre demandé.");
  }

  let semestres: number[];
  if (demande.semestres && demande.semestres.length > 0) {
    semestres = [...new Set(demande.semestres)].filter((s) => s >= 1 && s <= 10);
  } else if (demande.semestre) {
    semestres = [demande.semestre];
  } else {
    const set = new Set<number>();
    for (const groupe of groupesDb) for (const s of semestresDuNiveau(groupe.niveau)) set.add(s);
    semestres = [...set].sort((a, b) => a - b);
  }

  const formationIds = [...new Set(groupesDb.map((g) => g.formationId))];
  const modulesDb = await db
    .select()
    .from(schema.modules)
    .where(
      and(
        inArray(schema.modules.formationId, formationIds),
        inArray(schema.modules.semestre, semestres),
        eq(schema.modules.actif, true),
      ),
    );

  const [sallesDb, enseignantsDb, affectationsDb] = await Promise.all([
    db.select().from(schema.salles).where(eq(schema.salles.schedulable, true)),
    db.select().from(schema.enseignants).where(eq(schema.enseignants.actif, true)),
    modulesDb.length > 0
      ? db
          .select()
          .from(schema.moduleEnseignants)
          .where(
            inArray(
              schema.moduleEnseignants.moduleId,
              modulesDb.map((m) => m.id),
            ),
          )
      : Promise.resolve([]),
  ]);

  const groupes: EngineGroupe[] = groupesDb.map((g) => ({
    id: g.id,
    code: g.code,
    formationId: g.formationId,
    formationCode: g.formationCode,
    niveau: g.niveau,
    vagueId: g.vagueId,
    effectif: Math.max(1, g.effectif || g.effectifCible),
    semestres: semestresDuNiveau(g.niveau),
  }));

  const modules: EngineModule[] = modulesDb.map((m) => ({
    id: m.id,
    code: m.code,
    titre: m.titre,
    formationId: m.formationId,
    semestre: m.semestre,
    nature: m.nature,
    heuresCm: m.heuresCm,
    heuresTd: m.heuresTd,
    heuresTp: m.heuresTp,
    roomNeedCm: m.roomNeedCm,
    roomNeedTd: m.roomNeedTd,
    roomNeedTp: m.roomNeedTp,
  }));

  const affectations: Affectation[] = affectationsDb.map((a) => ({
    moduleId: a.moduleId,
    enseignantId: a.enseignantId,
    typeSeance: a.typeSeance,
  }));

  const resultat = genererEmploiDuTemps({
    anneeCode: anneeCible.code,
    groupes,
    modules,
    salles: sallesDb.map((s) => ({
      id: s.id,
      code: s.code,
      type: s.type,
      capacite: s.capacite,
    })),
    enseignants: enseignantsDb.map((e) => ({
      id: e.id,
      matricule: e.matricule,
      nom: `${e.prenom} ${e.nom}`,
      specialite: e.specialite,
    })),
    affectations,
    slots: referentiel.slots.map((s) => ({ ...s })),
    jours: referentiel.jours.map((j) => ({ ...j })),
    options: {
      semestres,
      maxSeancesParGroupe: Math.min(36, Math.max(10, demande.maxSeancesParGroupe ?? 30)),
      inclureSamedi: demande.inclureSamedi ?? true,
      eviterPauseMidi: demande.eviterPauseMidi ?? false,
      seed: demande.seed ?? 2026,
      maxTpParGroupe: 4,
    },
  });

  if (resultat.seances.length === 0) {
    throw new Error(
      `Génération impossible : ${resultat.alertes.join(" ") || "aucune séance planifiable."}`,
    );
  }

  const portee = `${demande.filiereCode ?? "TOUTES-FILIERES"}-${demande.formationId ?? "TOUTES-FORMATIONS"}-${demande.niveau ?? "TOUS-NIVEAUX"}-S${semestres.join("_")}`;
  const codeEdt = `EDT-${anneeCible.code}-${portee}-${Date.now().toString().slice(-6)}`;
  const libelle =
    demande.libelle ??
    `Emploi du temps ${anneeCible.code} · ${demande.filiereCode ?? "toutes filières"} · ${demande.formationId ? `formation #${demande.formationId}` : "toutes formations"} · semestres ${semestres.join(", ")}`;

  const [edt] = await db
    .insert(schema.emploisDuTemps)
    .values({
      code: codeEdt,
      libelle,
      anneeId: anneeCible.id,
      version: 1,
      statut: demande.publier ? "publie" : "brouillon",
      params: {
        filiereCode: demande.filiereCode ?? null,
        formationId: demande.formationId ?? null,
        niveau: demande.niveau ?? null,
        groupeId: demande.groupeId ?? null,
        semestres,
        inclureSamedi: demande.inclureSamedi ?? true,
        maxSeancesParGroupe: demande.maxSeancesParGroupe ?? 30,
      },
      stats: resultat.stats as unknown as Record<string, unknown>,
      publieLe: demande.publier ? new Date() : null,
    })
    .returning({ id: schema.emploisDuTemps.id, code: schema.emploisDuTemps.code });

  const [run] = await db
    .insert(schema.generationRuns)
    .values({
      anneeId: anneeCible.id,
      edtId: edt.id,
      scope: {
        filiereCode: demande.filiereCode ?? null,
        formationId: demande.formationId ?? null,
        niveau: demande.niveau ?? null,
        groupeId: demande.groupeId ?? null,
        semestres,
      },
      options: {
        inclureSamedi: demande.inclureSamedi ?? true,
        eviterPauseMidi: demande.eviterPauseMidi ?? false,
        maxSeancesParGroupe: demande.maxSeancesParGroupe ?? 30,
        seed: demande.seed ?? 2026,
      },
      statut: "termine",
      stats: resultat.stats as unknown as Record<string, unknown>,
      logs: resultat.alertes,
      dureeMs: resultat.stats.dureeMs,
      termineLe: new Date(),
    })
    .returning({ id: schema.generationRuns.id });

  // Remplacement des séances du périmètre (idempotence des regénérations).
  await db
    .delete(schema.seances)
    .where(
      and(
        eq(schema.seances.anneeId, anneeCible.id),
        inArray(schema.seances.semestre, semestres),
        inArray(schema.seances.formationId, formationIds),
        demande.groupeId ? eq(schema.seances.groupeId, demande.groupeId) : undefined,
      ),
    );

  const valeurs: (typeof schema.seances.$inferInsert)[] = resultat.seances.map((s) => ({
    edtId: edt.id,
    anneeId: anneeCible.id,
    formationId: s.formationId,
    moduleId: s.moduleId,
    groupeId: s.groupeId,
    vagueId: s.vagueId,
    enseignantId: s.enseignantId,
    salleId: s.salleId,
    niveau: s.niveau,
    semestre: s.semestre,
    typeSeance: s.typeSeance,
    jour: s.jour,
    slotCode: s.slotCode,
    heureDebut: s.heureDebut,
    heureFin: s.heureFin,
    effectif: s.effectif,
  }));
  for (const lot of chunk(valeurs, 500)) {
    await db.insert(schema.seances).values(lot);
  }

  // Nettoyage des en-têtes d'EDT devenus vides.
  await db.execute(sql`
    delete from gi_emplois_du_temps e
    where not exists (select 1 from gi_seances s where s.edt_id = e.id)
  `);

  return {
    runId: run.id,
    edtId: edt.id,
    edtCode: edt.code,
    stats: resultat.stats,
    alertes: resultat.alertes,
    nonPlacees: resultat.nonPlacees.slice(0, 50),
    classes: new Set(modulesDb.map((m) => `${m.formationId}-S${m.semestre}`)).size,
    semestres,
    anneeCode: anneeCible.code,
  };
}

export function niveauxDuPerimetre(): string[] {
  return ["L1", "L2", "L3", "M1", "M2"];
}

export function niveauSemestre(semestre: number): string {
  return niveauDeSemestre(semestre);
}
