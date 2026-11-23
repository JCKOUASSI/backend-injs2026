import { and, eq, inArray, sql } from "drizzle-orm";

import { db } from "@/db";
import * as schema from "@/db/schema";
import {
  analyserContenuCsv,
  analyserLignes,
  semestresCibles,
  type EtudiantImporte,
  type ResultatAnalyse,
} from "../../../get-injs-app/lib/import-parser";
import { normaliserNiveau, semestresDuNiveau } from "../../../get-injs-app/lib/engine";
import { ensureSeeded } from "@/lib/get-injs/seed";
import { genererEtPersister, type DemandeGeneration, type ResultatGeneration } from "@/lib/get-injs/generation-service";

export type DemandeImport = {
  fichier: string;
  contenu: Buffer;
  anneeCode?: string;
  autoCreer?: boolean;
  generer?: boolean;
  generation?: Omit<DemandeGeneration, "anneeCode">;
};

export type ResultatImport = {
  jobId: number;
  fichier: string;
  anneeCode: string;
  lignes: number;
  importes: number;
  nouveaux: number;
  ignores: number;
  erreurs: string[];
  colonnesDetectees: Record<string, string>;
  colonnesIgnorees: string[];
  referentielsCrees: { filieres: number; formations: number; groupes: number; vagues: number };
  dureeMs: number;
  generation?: { stats: ResultatGeneration["stats"]; alertes: string[]; classes: number };
};

function chunk<T>(items: T[], taille: number): T[][] {
  const resultat: T[][] = [];
  for (let i = 0; i < items.length; i += taille) resultat.push(items.slice(i, i + taille));
  return resultat;
}

function cleNom(valeur: string): string {
  return valeur
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

function slugCode(valeur: string): string {
  return valeur
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")
    .slice(0, 8);
}

export async function lireFichierEtudiants(
  nom: string,
  contenu: Buffer,
): Promise<ResultatAnalyse> {
  const estXlsx = /\.(xlsx|xlsm|xlsb|xls)$/i.test(nom) || (contenu[0] === 0x50 && contenu[1] === 0x4b);
  if (estXlsx) {
    const XLSX = await import("xlsx");
    const classeur = XLSX.read(contenu, { type: "buffer" });
    const feuille = classeur.Sheets[classeur.SheetNames[0]];
    if (!feuille) {
      return {
        lignes: [],
        erreurs: ["Classeur vide : aucune feuille exploitable."],
        ignorees: 0,
        colonnesDetectees: {},
        colonnesIgnorees: [],
        separateur: "xlsx",
      };
    }
    const rows = XLSX.utils.sheet_to_json<string[]>(feuille, {
      header: 1,
      raw: false,
      defval: "",
      blankrows: false,
    });
    return analyserLignes(
      rows.map((row) => (Array.isArray(row) ? row.map((cellule) => String(cellule ?? "")) : [])),
      "xlsx",
    );
  }
  return analyserContenuCsv(contenu.toString("utf8"));
}

export async function importerEtudiants(demande: DemandeImport): Promise<ResultatImport> {
  const debut = Date.now();
  await ensureSeeded();

  const analyse = await lireFichierEtudiants(demande.fichier, demande.contenu);
  if (analyse.lignes.length === 0) {
    throw new Error(
      analyse.erreurs[0] ??
        "Aucune ligne exploitable : vérifiez la présence des colonnes nom, prénom, formation et niveau.",
    );
  }
  if (analyse.lignes.length > 20000) {
    throw new Error("Fichier trop volumineux : 20 000 lignes maximum par import.");
  }

  const anneeCode = demande.anneeCode ?? "2026-2027";
  const [annee] = await db
    .select()
    .from(schema.academicYears)
    .where(eq(schema.academicYears.code, anneeCode))
    .limit(1);
  if (!annee) throw new Error(`Année académique ${anneeCode} inconnue.`);

  const erreurs: string[] = [...analyse.erreurs].slice(0, 20);
  const referentielsCrees = { filieres: 0, formations: 0, groupes: 0, vagues: 0 };
  const autoCreer = demande.autoCreer ?? true;

  const [filieresDb, formationsDb, groupesDb, vaguesDb, enseignantsDisponibles] = await Promise.all([
    db.select().from(schema.filieres),
    db.select().from(schema.formations),
    db.select().from(schema.groupes).where(eq(schema.groupes.anneeId, annee.id)),
    db.select().from(schema.vagues).where(eq(schema.vagues.anneeId, annee.id)),
    db.select({ id: schema.enseignants.id }).from(schema.enseignants).orderBy(schema.enseignants.id),
  ]);

  const filiereParCle = new Map<string, { id: number; code: string }>();
  for (const f of filieresDb) {
    filiereParCle.set(f.code.toUpperCase(), f);
    filiereParCle.set(slugCode(f.nom), f);
    filiereParCle.set(cleNom(f.nom), f);
  }
  const formationParCle = new Map<string, { id: number; code: string; filiereId: number }>();
  for (const f of formationsDb) {
    formationParCle.set(f.code.toUpperCase(), f);
    formationParCle.set(slugCode(f.nom), f);
    formationParCle.set(cleNom(f.nom), f);
  }
  const groupeParCode = new Map<string, { id: number; code: string }>();
  for (const g of groupesDb) groupeParCode.set(g.code.toUpperCase(), g);
  const vagueParCle = new Map<string, { id: number; code: string }>();
  for (const v of vaguesDb) {
    vagueParCle.set(v.code.toUpperCase(), v);
    vagueParCle.set(v.niveau.toUpperCase(), v);
  }

  const codesFilieres = new Set(filieresDb.map((f) => f.code.toUpperCase()));
  const codesFormations = new Set(formationsDb.map((f) => f.code.toUpperCase()));

  async function resoudreFiliere(ligne: EtudiantImporte) {
    const cle = ligne.filiere.toUpperCase();
    const directe =
      filiereParCle.get(cle) ?? filiereParCle.get(slugCode(ligne.filiere)) ?? filiereParCle.get(cleNom(ligne.filiere));
    if (directe) return directe;
    if (!autoCreer) return filieresDb[0] ?? null;
    let code = slugCode(ligne.filiere) || "FILIERE";
    let suffixe = 2;
    while (codesFilieres.has(code)) code = `${slugCode(ligne.filiere)}${suffixe++}`;
    codesFilieres.add(code);
    const [creee] = await db
      .insert(schema.filieres)
      .values({ code, nom: ligne.filiere, ecole: "INJS" })
      .returning({ id: schema.filieres.id, code: schema.filieres.code });
    filiereParCle.set(code, creee);
    referentielsCrees.filieres += 1;
    return creee;
  }

  async function resoudreFormation(ligne: EtudiantImporte, filiereId: number) {
    const cle = ligne.formation.toUpperCase();
    const directe =
      formationParCle.get(cle) ??
      formationParCle.get(slugCode(ligne.formation)) ??
      formationParCle.get(cleNom(ligne.formation));
    if (directe) return directe;
    if (!autoCreer) return null;
    let code = slugCode(ligne.formation) || `FORM${referentielsCrees.formations + 1}`;
    let suffixe = 2;
    while (codesFormations.has(code)) code = `${slugCode(ligne.formation)}${suffixe++}`;
    codesFormations.add(code);
    const [creee] = await db
      .insert(schema.formations)
      .values({
        filiereId,
        code,
        nom: ligne.formation,
        cycle: "Licence-Master",
        maquette: "canevas_importe",
      })
      .returning({ id: schema.formations.id, code: schema.formations.code, filiereId: schema.formations.filiereId });
    formationParCle.set(code, creee);
    referentielsCrees.formations += 1;
    // Maquette par défaut : 8 modules par semestre pour garantir la génération d'EDT.
    const niveaux = normaliserNiveau(ligne.niveau);
    for (const semestre of semestresDuNiveau(niveaux)) {
      const valeurs = Array.from({ length: 8 }, (_, i) => ({
        code: `${code}-S${semestre}-UE${String(i + 1).padStart(2, "0")}`,
        formationId: creee.id,
        semestre,
        titre: [
          "Introduction au domaine",
          "Fondamentaux techniques",
          "Sciences appliquées",
          "Méthodologie de la recherche",
          "Langue et communication",
          "Informatique appliquée",
          "Pratique professionnelle",
          "Projet personnel et professionnel",
        ][i],
        ects: 3,
        nature: i % 3 === 0 ? "theorique" : i % 3 === 1 ? "mixte" : "pratique",
        heuresCm: 20,
        heuresTd: 20,
        heuresTp: i % 3 === 2 ? 20 : 0,
        roomNeedTp: i % 3 === 2 ? "gym" : "td",
        source: "canevas_importe",
      }));
      const modulesCrees = await db
        .insert(schema.modules)
        .values(valeurs)
        .onConflictDoNothing()
        .returning({ id: schema.modules.id });
      // Affectation automatique d'enseignants pour que la maquette soit
      // immédiatement planifiable (CM, TD, TP).
      if (enseignantsDisponibles.length > 0) {
        const affectations: (typeof schema.moduleEnseignants.$inferInsert)[] = [];
        modulesCrees.forEach((module, index) => {
          (["CM", "TD", "TP"] as const).forEach((type, position) => {
            affectations.push({
              moduleId: module.id,
              enseignantId:
                enseignantsDisponibles[
                  (index * 3 + position) % enseignantsDisponibles.length
                ].id,
              typeSeance: type,
              chargeHoraire: 2,
            });
          });
        });
        if (affectations.length > 0) {
          await db.insert(schema.moduleEnseignants).values(affectations).onConflictDoNothing();
        }
      }
    }
    return creee;
  }

  async function resoudreVague(ligne: EtudiantImporte, niveau: string) {
    const cle = ligne.vague ? ligne.vague.toUpperCase() : niveau.toUpperCase();
    const directe = vagueParCle.get(cle) ?? vagueParCle.get(niveau.toUpperCase());
    if (directe) return directe;
    if (!autoCreer) return null;
    let code = ligne.vague ? slugCode(ligne.vague) : `VAG-${niveau}`;
    let suffixe = 2;
    while ([...vagueParCle.values()].some((v) => v.code === code)) code = `${code}-${suffixe++}`;
    const [creee] = await db
      .insert(schema.vagues)
      .values({
        code,
        label: ligne.vague || `Vague ${niveau} — import ${annee.code}`,
        niveau,
        anneeId: annee.id,
        statut: "ouverte",
      })
      .returning({ id: schema.vagues.id, code: schema.vagues.code });
    vagueParCle.set(code, creee);
    vagueParCle.set(niveau.toUpperCase(), creee);
    referentielsCrees.vagues += 1;
    return creee;
  }

  async function resoudreGroupe(
    ligne: EtudiantImporte,
    formation: { id: number; code: string },
    vague: { id: number; code: string } | null,
    niveau: string,
  ) {
    const code = (ligne.groupe || `${formation.code}-${niveau}-IMPORT`).toUpperCase();
    const directe = groupeParCode.get(code);
    if (directe) return directe;
    if (!autoCreer) return null;
    const [cree] = await db
      .insert(schema.groupes)
      .values({
        code,
        label: `${formation.code} ${niveau} — ${code}`,
        formationId: formation.id,
        vagueId: vague?.id ?? null,
        anneeId: annee.id,
        niveau,
        effectifCible: 40,
        source: "import",
      })
      .onConflictDoNothing()
      .returning({ id: schema.groupes.id, code: schema.groupes.code });
    if (cree) {
      groupeParCode.set(code, cree);
      referentielsCrees.groupes += 1;
      return cree;
    }
    const [existante] = await db
      .select({ id: schema.groupes.id, code: schema.groupes.code })
      .from(schema.groupes)
      .where(and(eq(schema.groupes.anneeId, annee.id), eq(schema.groupes.code, code)))
      .limit(1);
    return existante ?? null;
  }

  type Prepare = {
    matricule: string;
    nom: string;
    prenom: string;
    sexe: string;
    dateNaissance: string | null;
    email: string | null;
    telephone: string | null;
    statut: string;
    niveau: string;
    formationId: number;
    filiereId: number;
    groupeId: number | null;
    vagueId: number | null;
    semestres: number[];
  };
  const prepares: Prepare[] = [];
  const matriculesVus = new Set<string>();

  for (const ligne of analyse.lignes) {
    try {
      const filiere = await resoudreFiliere(ligne);
      if (!filiere) {
        erreurs.push(`Ligne ${ligne.ligne} : filière inconnue (${ligne.filiere}).`);
        continue;
      }
      const formation = await resoudreFormation(ligne, filiere.id);
      if (!formation) {
        erreurs.push(`Ligne ${ligne.ligne} : formation inconnue (${ligne.formation}).`);
        continue;
      }
      const niveau = normaliserNiveau(ligne.niveau);
      const vague = await resoudreVague(ligne, niveau);
      const groupe = await resoudreGroupe(ligne, formation, vague, niveau);
      const matricule = ligne.matricule.toUpperCase();
      if (matriculesVus.has(matricule)) continue;
      matriculesVus.add(matricule);
      prepares.push({
        matricule,
        nom: ligne.nom,
        prenom: ligne.prenom,
        sexe: ligne.sexe,
        dateNaissance: ligne.dateNaissance,
        email: ligne.email,
        telephone: ligne.telephone,
        statut: ligne.statut,
        niveau,
        formationId: formation.id,
        filiereId: filiere.id,
        groupeId: groupe?.id ?? null,
        vagueId: vague?.id ?? null,
        semestres: semestresCibles({ ...ligne, niveau }),
      });
    } catch (erreur) {
      erreurs.push(
        `Ligne ${ligne.ligne} : ${erreur instanceof Error ? erreur.message : "erreur inconnue"}`,
      );
    }
  }

  if (prepares.length === 0) {
    throw new Error("Aucun étudiant exploitable dans le fichier fourni.");
  }

  let nouveaux = 0;
  for (const lot of chunk(prepares, 500)) {
    const inseres = await db
      .insert(schema.etudiants)
      .values(
        lot.map((p) => ({
          matricule: p.matricule,
          nom: p.nom,
          prenom: p.prenom,
          sexe: p.sexe,
          dateNaissance: p.dateNaissance,
          email: p.email,
          telephone: p.telephone,
          anneeId: annee.id,
          formationId: p.formationId,
          groupeId: p.groupeId,
          vagueId: p.vagueId,
          niveau: p.niveau,
          statut: p.statut || "inscrit",
          source: "import",
        })),
      )
      .onConflictDoNothing()
      .returning({ id: schema.etudiants.id });
    nouveaux += inseres.length;
  }

  const etudiantsEnBase: { id: number; matricule: string }[] = [];
  for (const lot of chunk(prepares.map((p) => p.matricule), 1000)) {
    const lignes = await db
      .select({ id: schema.etudiants.id, matricule: schema.etudiants.matricule })
      .from(schema.etudiants)
      .where(inArray(schema.etudiants.matricule, lot));
    etudiantsEnBase.push(...lignes);
  }
  const idParMatricule = new Map(etudiantsEnBase.map((e) => [e.matricule, e.id]));

  let inscriptionsCreees = 0;
  const valeursInscriptions: (typeof schema.inscriptions.$inferInsert)[] = [];
  for (const p of prepares) {
    const etudiantId = idParMatricule.get(p.matricule);
    if (!etudiantId) continue;
    for (const semestre of p.semestres) {
      valeursInscriptions.push({
        etudiantId,
        anneeId: annee.id,
        filiereId: p.filiereId,
        formationId: p.formationId,
        groupeId: p.groupeId,
        vagueId: p.vagueId,
        niveau: p.niveau,
        semestre,
        statut: p.statut || "inscrit",
        source: "import",
      });
    }
  }
  for (const lot of chunk(valeursInscriptions, 800)) {
    const lignes = await db
      .insert(schema.inscriptions)
      .values(lot)
      .onConflictDoNothing()
      .returning({ id: schema.inscriptions.id });
    inscriptionsCreees += lignes.length;
  }

  await db.execute(sql`
    update gi_groupes g set effectif = coalesce(sub.total, 0)
    from (select groupe_id, count(*)::int as total from gi_etudiants where groupe_id is not null group by groupe_id) sub
    where g.id = sub.groupe_id
  `);
  await db.execute(sql`
    update gi_vagues v set effectif_reel = coalesce(sub.total, 0)
    from (select vague_id, count(*)::int as total from gi_etudiants where vague_id is not null group by vague_id) sub
    where v.id = sub.vague_id
  `);

  let generation: ResultatImport["generation"];
  if (demande.generer) {
    try {
      const resultat = await genererEtPersister({
        anneeCode: annee.code,
        ...demande.generation,
      });
      generation = {
        stats: resultat.stats,
        alertes: resultat.alertes,
        classes: resultat.classes,
      };
    } catch (erreur) {
      erreurs.push(
        `Génération post-import : ${erreur instanceof Error ? erreur.message : "échec inconnu"}`,
      );
    }
  }

  const dureeMs = Date.now() - debut;
  const [job] = await db
    .insert(schema.importJobs)
    .values({
      fichier: demande.fichier,
      anneeId: annee.id,
      statut: erreurs.length > 0 ? "termine_avec_alertes" : "termine",
      lignes: analyse.lignes.length,
      importes: prepares.length,
      ignores: analyse.ignorees + (analyse.lignes.length - prepares.length),
      referentielsCrees,
      erreurs: erreurs.slice(0, 50),
      dureeMs,
    })
    .returning({ id: schema.importJobs.id });

  return {
    jobId: job.id,
    fichier: demande.fichier,
    anneeCode: annee.code,
    lignes: analyse.lignes.length,
    importes: prepares.length,
    nouveaux,
    ignores: Math.max(0, analyse.lignes.length - prepares.length) + analyse.ignorees,
    erreurs: erreurs.slice(0, 50),
    colonnesDetectees: analyse.colonnesDetectees,
    colonnesIgnorees: analyse.colonnesIgnorees,
    referentielsCrees,
    dureeMs,
    generation,
  };
}

export async function effectifsParGroupe() {
  return db
    .select({
      groupe: schema.groupes.code,
      effectif: schema.groupes.effectif,
      niveau: schema.groupes.niveau,
      formation: schema.formations.code,
    })
    .from(schema.groupes)
    .innerJoin(schema.formations, eq(schema.groupes.formationId, schema.formations.id))
    .orderBy(schema.groupes.code);
}
