import { and, eq, sql } from "drizzle-orm";

import { db } from "@/db";
import * as schema from "@/db/schema";
import { referentiel } from "../../../get-injs-app/data/referentiel";
import { semestresDuNiveau } from "../../../get-injs-app/lib/engine";

const SEED_KEY = "get_injs_seed_v1";

const NOMS = [
  "Kouassi", "Yao", "Koné", "Traoré", "Diallo", "Bamba", "Ouattara", "Cissé", "Koffi",
  "Aka", "Soro", "Tanoh", "Gnahoré", "Diomandé", "Bakayoko", "Coulibaly", "Doumbia",
  "Konaté", "Tiémoko", "Assamoi", "Gbagbo", "Zadi", "Loba", "N'Guessan", "Ehui", "Sess",
  "Adou", "Béchi", "Dago", "Kacou", "Méité", "Sanogo", "Touré", "Zoro", "Bohoussou",
];
const PRENOMS_F = [
  "Aminata", "Mariam", "Awa", "Fatou", "Nadia", "Rachelle", "Akissi", "Adjoua", "Affoué",
  "Aya", "Grâce", "Prisca", "Salimata", "Kadiatou", "Bintou", "Estelle", "Nathalie",
  "Jocelyne", "Solange", "Émilie", "Rokhaya", "Aminata", "Flore", "Yasmine", "Léa",
];
const PRENOMS_M = [
  "Jean", "Serge", "Koffi", "Ismaël", "Moussa", "Ibrahim", "Yacouba", "Franck", "Éric",
  "Aboubakar", "Souleymane", "Armand", "Cédric", "Hervé", "Didier", "Olivier", "Jonas",
  "Bakary", "Lacina", "Sébastien", "Marcel", "Axel", "Boubacar", "Emmanuel", "Félix",
];

function chunk<T>(items: T[], taille: number): T[][] {
  const resultat: T[][] = [];
  for (let i = 0; i < items.length; i += taille) resultat.push(items.slice(i, i + taille));
  return resultat;
}

function slug(valeur: string): string {
  return valeur
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ".")
    .replace(/^\.|\.$/g, "");
}

let seedEnCours: Promise<void> | null = null;

export async function ensureSeeded(): Promise<void> {
  if (!seedEnCours) {
    seedEnCours = executerSeed().catch((erreur) => {
      seedEnCours = null;
      throw erreur;
    });
  }
  return seedEnCours;
}

async function executerSeed(): Promise<void> {
  await db.transaction(async (tx) => {
    await tx.execute(sql`select pg_advisory_xact_lock(918273645)`);
    const deja = await tx
      .select({ value: schema.appMeta.value })
      .from(schema.appMeta)
      .where(eq(schema.appMeta.key, SEED_KEY))
      .limit(1);
    if (deja.length > 0) return;

    // 1. Années académiques
    const annees = await tx
      .insert(schema.academicYears)
      .values(
        referentiel.academicYears.map((annee) => ({
          code: annee.code,
          label: annee.label,
          dateDebut: annee.debut,
          dateFin: annee.fin,
          statut: annee.statut,
          active: annee.code === referentiel.activeYear,
        })),
      )
      .onConflictDoNothing()
      .returning({ id: schema.academicYears.id, code: schema.academicYears.code });
    const anneeId = annees.find((a) => a.code === referentiel.activeYear)?.id ?? annees[0]?.id;
    if (!anneeId) throw new Error("Année académique de référence introuvable");
    const anneeActive = referentiel.activeYear;

    // 2. Filières (mentions) et écoles
    const filieres = await tx
      .insert(schema.filieres)
      .values(
        referentiel.filieres.map((filiere) => ({
          code: filiere.code,
          nom: filiere.nom,
          ecole: filiere.ecole,
        })),
      )
      .onConflictDoNothing()
      .returning({ id: schema.filieres.id, code: schema.filieres.code });
    const filiereParCode = new Map(filieres.map((f) => [f.code, f.id]));

    // 3. Formations
    const formations = await tx
      .insert(schema.formations)
      .values(
        referentiel.formations.map((formation) => ({
          filiereId: filiereParCode.get(formation.filireCode) ?? filieres[0].id,
          code: formation.code,
          nom: formation.nom,
          cycle: formation.cycle,
          maquette: formation.maquette,
          actif: formation.actif,
        })),
      )
      .onConflictDoNothing()
      .returning({ id: schema.formations.id, code: schema.formations.code });
    const formationParCode = new Map(formations.map((f) => [f.code, f.id]));

    // 4. Bâtiments et salles
    const batiments = await tx
      .insert(schema.batiments)
      .values(referentiel.batiments.map((b) => ({ code: b.code, nom: b.nom, zone: b.zone })))
      .onConflictDoNothing()
      .returning({ id: schema.batiments.id, code: schema.batiments.code });
    const batimentParCode = new Map(batiments.map((b) => [b.code, b.id]));
    const salles = await tx
      .insert(schema.salles)
      .values(
        referentiel.salles.map((salle) => ({
          batimentId: batimentParCode.get(salle.batimentCode) ?? null,
          code: salle.code,
          nom: salle.nom,
          type: salle.type,
          capacite: salle.capacite,
          equipements: salle.equipements,
          schedulable: salle.schedulable,
        })),
      )
      .onConflictDoNothing()
      .returning({ id: schema.salles.id, code: schema.salles.code });

    // 5. Vagues (promotions) puis groupes
    const vagues = await tx
      .insert(schema.vagues)
      .values(
        referentiel.vagues.map((vague) => ({
          code: vague.code,
          label: vague.label,
          niveau: vague.niveau,
          anneeId,
          dateDebut: vague.debut,
          dateFin: vague.fin,
          statut: vague.statut,
          effectifPrevu: 0,
        })),
      )
      .onConflictDoNothing()
      .returning({ id: schema.vagues.id, code: schema.vagues.code });
    const vagueParCode = new Map(vagues.map((v) => [v.code, v.id]));

    const groupes = await tx
      .insert(schema.groupes)
      .values(
        referentiel.groupes.map((groupe) => ({
          code: groupe.code,
          label: groupe.label,
          formationId: formationParCode.get(groupe.formationCode)!,
          vagueId: vagueParCode.get(groupe.vagueCode) ?? null,
          anneeId,
          niveau: groupe.niveau,
          effectifCible: groupe.effectifCible,
          source: "referentiel",
        })),
      )
      .onConflictDoNothing()
      .returning({ id: schema.groupes.id, code: schema.groupes.code, formationId: schema.groupes.formationId });
    const groupeParCode = new Map(groupes.map((g) => [g.code, g]));

    // 6. Enseignants
    const enseignants = await tx
      .insert(schema.enseignants)
      .values(
        referentiel.enseignants.map((enseignant) => ({
          matricule: enseignant.matricule,
          nom: enseignant.nom,
          prenom: enseignant.prenom,
          grade: enseignant.grade,
          specialite: enseignant.formationCode,
          email: enseignant.email,
          maxHeures: enseignant.maxHeures,
        })),
      )
      .onConflictDoNothing()
      .returning({ id: schema.enseignants.id, matricule: schema.enseignants.matricule, specialite: schema.enseignants.specialite });
    const enseignantsParSpecialite = new Map<string, number[]>();
    for (const enseignant of enseignants) {
      const liste = enseignantsParSpecialite.get(enseignant.specialite) ?? [];
      liste.push(enseignant.id);
      enseignantsParSpecialite.set(enseignant.specialite, liste);
    }

    // 7. Modules (maquettes LMD) et affectations enseignants
    const modules = await tx
      .insert(schema.modules)
      .values(
        referentiel.modules.flatMap((module) => {
          const formationId = formationParCode.get(module.formationCode);
          if (!formationId) return [];
          return [
            {
              code: module.code,
              formationId,
              semestre: module.semestre,
              titre: module.titre,
              ects: module.ects,
              nature: module.nature,
              heuresCm: module.heureCm,
              heuresTd: module.heureTd,
              heuresTp: module.heureTp,
              roomNeedCm: module.roomNeedCm,
              roomNeedTd: module.roomNeedTd,
              roomNeedTp: module.roomNeedTp,
              source: module.source,
            },
          ];
        }),
      )
      .onConflictDoNothing()
      .returning({
        id: schema.modules.id,
        code: schema.modules.code,
        formationId: schema.modules.formationId,
      });

    const affectations: (typeof schema.moduleEnseignants.$inferInsert)[] = [];
    const codeParFormation = new Map(formations.map((f) => [f.id, f.code]));
    modules.forEach((module, i) => {
      const codeFormation = codeParFormation.get(module.formationId) ?? "EM";
      const pool = enseignantsParSpecialite.get(codeFormation) ?? enseignants.map((e) => e.id);
      if (pool.length === 0) return;
      const types: ("CM" | "TD" | "TP")[] = ["CM", "TD", "TP"];
      types.forEach((type, j) => {
        affectations.push({
          moduleId: module.id,
          enseignantId: pool[(i * 3 + j) % pool.length],
          typeSeance: type,
          chargeHoraire: 2,
        });
      });
    });
    for (const lot of chunk(affectations, 800)) {
      await tx.insert(schema.moduleEnseignants).values(lot).onConflictDoNothing();
    }

    // 8. Étudiants inscrits (cohorte de démonstration alignée sur les effectifs cibles)
    const groupeParCodeVague = groupeParCode;
    const etudiants: (typeof schema.etudiants.$inferInsert)[] = [];
    let compteur = 1;
    for (const groupe of referentiel.groupes) {
      const groupeDb = groupeParCodeVague.get(groupe.code);
      const formationId = formationParCode.get(groupe.formationCode);
      if (!groupeDb || !formationId) continue;
      for (let i = 0; i < groupe.effectifCible; i += 1) {
        const sexe = (compteur + i) % 2 === 0 ? "F" : "M";
        const prenom = sexe === "F" ? PRENOMS_F[(compteur + i) % PRENOMS_F.length] : PRENOMS_M[(compteur + i) % PRENOMS_M.length];
        const nom = NOMS[(compteur * 7 + i) % NOMS.length];
        const num = compteur + i;
        etudiants.push({
          matricule: `INJS-${anneeActive.slice(0, 4)}-${String(num).padStart(5, "0")}`,
          nom: nom.toUpperCase(),
          prenom,
          sexe,
          dateNaissance: `${1998 + (num % 9)}-${String((num % 12) + 1).padStart(2, "0")}-${String((num % 27) + 1).padStart(2, "0")}`,
          email: `${slug(prenom)}.${slug(nom)}${num}@injs-marcory.example`,
          telephone: `+22507${String(num).padStart(8, "0").slice(0, 8)}`,
          anneeId,
          formationId,
          groupeId: groupeDb.id,
          vagueId: vagueParCode.get(groupe.vagueCode) ?? null,
          niveau: groupe.niveau,
          statut: "inscrit",
          source: "app",
        });
      }
      compteur += groupe.effectifCible;
    }

    const inscriptions: (typeof schema.inscriptions.$inferInsert)[] = [];
    for (const lot of chunk(etudiants, 400)) {
      const inseres = await tx
        .insert(schema.etudiants)
        .values(lot)
        .onConflictDoNothing()
        .returning({
          id: schema.etudiants.id,
          matricule: schema.etudiants.matricule,
          formationId: schema.etudiants.formationId,
          groupeId: schema.etudiants.groupeId,
          vagueId: schema.etudiants.vagueId,
          niveau: schema.etudiants.niveau,
        });
      for (const etudiant of inseres) {
        const formationId = etudiant.formationId ?? formationParCode.get("EM")!;
        const filiereId =
          filiereParCode.get(
            referentiel.formations.find((f) => formationParCode.get(f.code) === formationId)?.filireCode ?? "STAPS",
          ) ?? filieres[0].id;
        for (const semestre of semestresDuNiveau(etudiant.niveau ?? "L1")) {
          inscriptions.push({
            etudiantId: etudiant.id,
            anneeId,
            filiereId,
            formationId,
            groupeId: etudiant.groupeId,
            vagueId: etudiant.vagueId,
            niveau: etudiant.niveau ?? "L1",
            semestre,
            statut: "inscrit",
            source: "app",
          });
        }
      }
    }
    for (const lot of chunk(inscriptions, 800)) {
      await tx.insert(schema.inscriptions).values(lot).onConflictDoNothing();
    }

    // 9. Synchronisation des effectifs
    await tx.execute(sql`
      update gi_groupes g set effectif = coalesce(sub.total, 0)
      from (select groupe_id, count(*)::int as total from gi_etudiants where groupe_id is not null group by groupe_id) sub
      where g.id = sub.groupe_id
    `);
    await tx.execute(sql`
      update gi_vagues v set effectif_reel = coalesce(sub.total, 0), effectif_prevu = coalesce(sub.total, 0)
      from (select vague_id, count(*)::int as total from gi_etudiants where vague_id is not null group by vague_id) sub
      where v.id = sub.vague_id
    `);

    await tx
      .insert(schema.appMeta)
      .values({ key: SEED_KEY, value: new Date().toISOString() })
      .onConflictDoNothing();
    await tx
      .insert(schema.appMeta)
      .values({ key: "get_injs_etudiants", value: String(etudiants.length) })
      .onConflictDoUpdate({ target: schema.appMeta.key, set: { value: String(etudiants.length) } });
  });
}

export async function anneeActiveId(): Promise<number> {
  const [annee] = await db
    .select({ id: schema.academicYears.id })
    .from(schema.academicYears)
    .where(eq(schema.academicYears.active, true))
    .limit(1);
  if (annee) return annee.id;
  const [premiere] = await db
    .select({ id: schema.academicYears.id })
    .from(schema.academicYears)
    .orderBy(sql`${schema.academicYears.code} desc`)
    .limit(1);
  if (!premiere) throw new Error("Aucune année académique configurée");
  return premiere.id;
}

export async function anneeParCode(code: string): Promise<typeof schema.academicYears.$inferSelect | null> {
  const [annee] = await db
    .select()
    .from(schema.academicYears)
    .where(eq(schema.academicYears.code, code))
    .limit(1);
  return annee ?? null;
}

export async function groupeEtVague(
  formationId: number,
  niveau: string,
  anneeId: number,
): Promise<{ groupeId: number | null; vagueId: number | null }> {
  const [vague] = await db
    .select({ id: schema.vagues.id })
    .from(schema.vagues)
    .where(and(eq(schema.vagues.anneeId, anneeId), eq(schema.vagues.niveau, niveau)))
    .limit(1);
  const [groupe] = await db
    .select({ id: schema.groupes.id })
    .from(schema.groupes)
    .where(
      and(
        eq(schema.groupes.anneeId, anneeId),
        eq(schema.groupes.formationId, formationId),
        eq(schema.groupes.niveau, niveau),
      ),
    )
    .limit(1);
  return { groupeId: groupe?.id ?? null, vagueId: vague?.id ?? null };
}
