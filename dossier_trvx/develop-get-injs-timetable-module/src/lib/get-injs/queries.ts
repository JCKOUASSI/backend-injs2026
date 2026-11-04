import { and, asc, count, desc, eq, ilike, or, sql } from "drizzle-orm";

import { db } from "@/db";
import * as schema from "@/db/schema";

export type FiltresEmploiDuTemps = {
  anneeCode?: string;
  filiereCode?: string;
  formationId?: number;
  niveau?: string;
  groupeId?: number;
  vagueId?: number;
  semestre?: number;
  typeSeance?: string;
  limit?: number;
};

export type SeanceDetaillee = {
  id: number;
  semestre: number;
  niveau: string;
  jour: number;
  slotCode: string;
  heureDebut: string;
  heureFin: string;
  typeSeance: string;
  effectif: number;
  salle: string;
  salleType: string;
  capacite: number;
  module: string;
  moduleCode: string;
  formation: string;
  formationCode: string;
  filiere: string;
  groupe: string | null;
  groupeCode: string | null;
  ennseignant: string | null;
  grade: string | null;
  edtCode: string;
};

export async function getAnnees() {
  return db.select().from(schema.academicYears).orderBy(desc(schema.academicYears.code));
}

export async function getAnneeActive() {
  const [active] = await db
    .select()
    .from(schema.academicYears)
    .where(eq(schema.academicYears.active, true))
    .limit(1);
  if (active) return active;
  const [fallback] = await db
    .select()
    .from(schema.academicYears)
    .orderBy(desc(schema.academicYears.code))
    .limit(1);
  return fallback ?? null;
}

export async function getReferentiels() {
  const [filieres, formations, niveaux, vagues, groupes, annees] = await Promise.all([
    db.select().from(schema.filieres).orderBy(asc(schema.filieres.code)),
    db.select().from(schema.formations).orderBy(asc(schema.formations.code)),
    db
      .select({ niveau: schema.groupes.niveau })
      .from(schema.groupes)
      .groupBy(schema.groupes.niveau)
      .orderBy(asc(schema.groupes.niveau)),
    db.select().from(schema.vagues).orderBy(asc(schema.vagues.code)),
    db
      .select({
        id: schema.groupes.id,
        code: schema.groupes.code,
        label: schema.groupes.label,
        niveau: schema.groupes.niveau,
        effectif: schema.groupes.effectif,
        formationId: schema.groupes.formationId,
        vagueId: schema.groupes.vagueId,
      })
      .from(schema.groupes)
      .orderBy(asc(schema.groupes.niveau), asc(schema.groupes.code)),
    getAnnees(),
  ]);
  return { filieres, formations, niveaux, vagues, groupes, annees };
}

export async function getDashboard() {
  const [
    etudiants,
    inscriptions,
    groupes,
    salles,
    enseignants,
    modules,
    seances,
    edt,
    runs,
    imports,
  ] = await Promise.all([
    db.select({ n: count() }).from(schema.etudiants),
    db.select({ n: count() }).from(schema.inscriptions),
    db.select({ n: count() }).from(schema.groupes),
    db.select({ n: count() }).from(schema.salles),
    db.select({ n: count() }).from(schema.enseignants),
    db.select({ n: count() }).from(schema.modules),
    db.select({ n: count() }).from(schema.seances),
    db
      .select()
      .from(schema.emploisDuTemps)
      .orderBy(desc(schema.emploisDuTemps.genereLe))
      .limit(3),
    db
      .select()
      .from(schema.generationRuns)
      .orderBy(desc(schema.generationRuns.demarreLe))
      .limit(4),
    db.select().from(schema.importJobs).orderBy(desc(schema.importJobs.createdAt)).limit(4),
  ]);

  const parFiliere = await db
    .select({
      filiere: schema.filieres.code,
      nom: schema.filieres.nom,
      effectif: sql<number>`count(*)::int`,
    })
    .from(schema.etudiants)
    .innerJoin(schema.formations, eq(schema.etudiants.formationId, schema.formations.id))
    .innerJoin(schema.filieres, eq(schema.formations.filiereId, schema.filieres.id))
    .groupBy(schema.filieres.code, schema.filieres.nom)
    .orderBy(desc(sql`count(*)`));

  const parNiveau = await db
    .select({
      niveau: schema.groupes.niveau,
      effectif: sql<number>`coalesce(sum(${schema.groupes.effectif}), 0)::int`,
      groupes: sql<number>`count(*)::int`,
    })
    .from(schema.groupes)
    .groupBy(schema.groupes.niveau)
    .orderBy(asc(schema.groupes.niveau));

  const parSemestre = await db
    .select({
      semestre: schema.seances.semestre,
      seances: sql<number>`count(*)::int`,
      cm: sql<number>`sum(case when ${schema.seances.typeSeance} = 'CM' then 1 else 0 end)::int`,
      td: sql<number>`sum(case when ${schema.seances.typeSeance} = 'TD' then 1 else 0 end)::int`,
      tp: sql<number>`sum(case when ${schema.seances.typeSeance} = 'TP' then 1 else 0 end)::int`,
    })
    .from(schema.seances)
    .groupBy(schema.seances.semestre)
    .orderBy(asc(schema.seances.semestre));

  return {
    compteurs: {
      etudiants: etudiants[0]?.n ?? 0,
      inscriptions: inscriptions[0]?.n ?? 0,
      groupes: groupes[0]?.n ?? 0,
      salles: salles[0]?.n ?? 0,
      enseignants: enseignants[0]?.n ?? 0,
      modules: modules[0]?.n ?? 0,
      seances: seances[0]?.n ?? 0,
    },
    edt,
    runs,
    imports,
    parFiliere,
    parNiveau,
    parSemestre,
  };
}

export async function getEmploiDuTemps(filtres: FiltresEmploiDuTemps) {
  const conditions = [];
  if (filtres.anneeCode) conditions.push(eq(schema.academicYears.code, filtres.anneeCode));
  if (filtres.filiereCode) conditions.push(eq(schema.filieres.code, filtres.filiereCode));
  if (filtres.formationId) conditions.push(eq(schema.seances.formationId, filtres.formationId));
  if (filtres.niveau) conditions.push(eq(schema.seances.niveau, filtres.niveau));
  if (filtres.groupeId) conditions.push(eq(schema.seances.groupeId, filtres.groupeId));
  if (filtres.vagueId) conditions.push(eq(schema.seances.vagueId, filtres.vagueId));
  if (filtres.semestre) conditions.push(eq(schema.seances.semestre, filtres.semestre));
  if (filtres.typeSeance) conditions.push(eq(schema.seances.typeSeance, filtres.typeSeance));

  const lignes = await db
    .select({
      id: schema.seances.id,
      semestre: schema.seances.semestre,
      niveau: schema.seances.niveau,
      jour: schema.seances.jour,
      slotCode: schema.seances.slotCode,
      heureDebut: schema.seances.heureDebut,
      heureFin: schema.seances.heureFin,
      typeSeance: schema.seances.typeSeance,
      effectif: schema.seances.effectif,
      salle: schema.salles.code,
      salleType: schema.salles.type,
      capacite: schema.salles.capacite,
      module: schema.modules.titre,
      moduleCode: schema.modules.code,
      formation: schema.formations.nom,
      formationCode: schema.formations.code,
      filiere: schema.filieres.code,
      groupe: schema.groupes.label,
      groupeCode: schema.groupes.code,
      ennseignant: sql<string | null>`case when ${schema.enseignants.id} is null then null else ${schema.enseignants.prenom} || ' ' || ${schema.enseignants.nom} end`,
      grade: schema.enseignants.grade,
      edtCode: schema.emploisDuTemps.code,
    })
    .from(schema.seances)
    .innerJoin(schema.academicYears, eq(schema.seances.anneeId, schema.academicYears.id))
    .innerJoin(schema.modules, eq(schema.seances.moduleId, schema.modules.id))
    .innerJoin(schema.formations, eq(schema.seances.formationId, schema.formations.id))
    .innerJoin(schema.filieres, eq(schema.formations.filiereId, schema.filieres.id))
    .leftJoin(schema.groupes, eq(schema.seances.groupeId, schema.groupes.id))
    .leftJoin(schema.salles, eq(schema.seances.salleId, schema.salles.id))
    .leftJoin(schema.enseignants, eq(schema.seances.enseignantId, schema.enseignants.id))
    .leftJoin(schema.emploisDuTemps, eq(schema.seances.edtId, schema.emploisDuTemps.id))
    .where(conditions.length > 0 ? and(...conditions) : undefined)
    .orderBy(asc(schema.seances.semestre), asc(schema.seances.jour), asc(schema.seances.slotCode))
    .limit(filtres.limit ?? 400);

  return lignes as SeanceDetaillee[];
}

export async function getResumeEmploiDuTemps(filtres: FiltresEmploiDuTemps) {
  const conditions = [];
  if (filtres.anneeCode) conditions.push(eq(schema.academicYears.code, filtres.anneeCode));
  if (filtres.formationId) conditions.push(eq(schema.seances.formationId, filtres.formationId));
  if (filtres.groupeId) conditions.push(eq(schema.seances.groupeId, filtres.groupeId));
  if (filtres.semestre) conditions.push(eq(schema.seances.semestre, filtres.semestre));
  const [resultat] = await db
    .select({
      seances: sql<number>`count(*)::int`,
      cm: sql<number>`sum(case when ${schema.seances.typeSeance} = 'CM' then 1 else 0 end)::int`,
      td: sql<number>`sum(case when ${schema.seances.typeSeance} = 'TD' then 1 else 0 end)::int`,
      tp: sql<number>`sum(case when ${schema.seances.typeSeance} = 'TP' then 1 else 0 end)::int`,
      places: sql<number>`coalesce(sum(${schema.seances.effectif}), 0)::int`,
    })
    .from(schema.seances)
    .innerJoin(schema.academicYears, eq(schema.seances.anneeId, schema.academicYears.id))
    .where(conditions.length > 0 ? and(...conditions) : undefined);
  return resultat ?? { seances: 0, cm: 0, td: 0, tp: 0, places: 0 };
}

export async function getEtudiants(params: {
  recherche?: string;
  formationCode?: string;
  niveau?: string;
  page?: number;
  taille?: number;
}) {
  const page = Math.max(1, params.page ?? 1);
  const taille = Math.min(100, Math.max(10, params.taille ?? 25));
  const conditions = [];
  if (params.recherche) {
    conditions.push(
      or(
        ilike(schema.etudiants.matricule, `%${params.recherche}%`),
        ilike(schema.etudiants.nom, `%${params.recherche}%`),
        ilike(schema.etudiants.prenom, `%${params.recherche}%`),
      ),
    );
  }
  if (params.formationCode) conditions.push(eq(schema.formations.code, params.formationCode));
  if (params.niveau) conditions.push(eq(schema.etudiants.niveau, params.niveau));
  const where = conditions.length > 0 ? and(...conditions) : undefined;

  const [lignes, total] = await Promise.all([
    db
      .select({
        id: schema.etudiants.id,
        matricule: schema.etudiants.matricule,
        nom: schema.etudiants.nom,
        prenom: schema.etudiants.prenom,
        sexe: schema.etudiants.sexe,
        niveau: schema.etudiants.niveau,
        statut: schema.etudiants.statut,
        source: schema.etudiants.source,
        formation: schema.formations.code,
        formationNom: schema.formations.nom,
        groupe: schema.groupes.code,
        vague: schema.vagues.code,
      })
      .from(schema.etudiants)
      .leftJoin(schema.formations, eq(schema.etudiants.formationId, schema.formations.id))
      .leftJoin(schema.groupes, eq(schema.etudiants.groupeId, schema.groupes.id))
      .leftJoin(schema.vagues, eq(schema.etudiants.vagueId, schema.vagues.id))
      .where(where)
      .orderBy(asc(schema.etudiants.matricule))
      .limit(taille)
      .offset((page - 1) * taille),
    db
      .select({ n: count() })
      .from(schema.etudiants)
      .leftJoin(schema.formations, eq(schema.etudiants.formationId, schema.formations.id))
      .where(where),
  ]);
  return { lignes, total: total[0]?.n ?? 0, page, taille };
}

export async function getReferentielComplet() {
  const [filieres, formations, batiments, salles, modules, enseignants, groupes, vagues, annees] =
    await Promise.all([
      db.select().from(schema.filieres).orderBy(asc(schema.filieres.code)),
      db.select().from(schema.formations).orderBy(asc(schema.formations.code)),
      db.select().from(schema.batiments).orderBy(asc(schema.batiments.code)),
      db.select().from(schema.salles).orderBy(asc(schema.salles.type), asc(schema.salles.code)),
      db.select().from(schema.modules).orderBy(asc(schema.modules.formationId), asc(schema.modules.semestre)),
      db.select().from(schema.enseignants).orderBy(asc(schema.enseignants.matricule)),
      db
        .select({
          id: schema.groupes.id,
          code: schema.groupes.code,
          label: schema.groupes.label,
          niveau: schema.groupes.niveau,
          effectif: schema.groupes.effectif,
          effectifCible: schema.groupes.effectifCible,
          formationId: schema.groupes.formationId,
          vagueId: schema.groupes.vagueId,
        })
        .from(schema.groupes)
        .orderBy(asc(schema.groupes.code)),
      db.select().from(schema.vagues).orderBy(asc(schema.vagues.code)),
      getAnnees(),
    ]);
  return { filieres, formations, batiments, salles, modules, enseignants, groupes, vagues, annees };
}

export async function getHistorique() {
  const [runs, imports, edts] = await Promise.all([
    db
      .select()
      .from(schema.generationRuns)
      .orderBy(desc(schema.generationRuns.demarreLe))
      .limit(8),
    db.select().from(schema.importJobs).orderBy(desc(schema.importJobs.createdAt)).limit(8),
    db.select().from(schema.emploisDuTemps).orderBy(desc(schema.emploisDuTemps.genereLe)).limit(8),
  ]);
  return { runs, imports, edts };
}

export async function getSemestresDisponibles(): Promise<number[]> {
  const lignes = await db
    .select({ semestre: schema.seances.semestre })
    .from(schema.seances)
    .groupBy(schema.seances.semestre)
    .orderBy(asc(schema.seances.semestre));
  return lignes.map((l) => l.semestre);
}
