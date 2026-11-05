/**
 * Import externe d'étudiants inscrits (CSV / XLSX) — GET INJS APP.
 * Le parseur est tolérant : il détecte les colonnes par alias, normalise les
 * niveaux/semestres et permet de reconstituer un parcours académique LMD même
 * lorsque l'inscription n'a pas été faite dans l'application de base.
 */
import { normaliserNiveau, semestresDuNiveau } from "./engine";

export type EtudiantImporte = {
  ligne: number;
  matricule: string;
  nom: string;
  prenom: string;
  sexe: string;
  dateNaissance: string | null;
  email: string | null;
  telephone: string | null;
  filiere: string;
  formation: string;
  niveau: string;
  groupe: string;
  vague: string;
  semestre: number | null;
  statut: string;
  anneeAcademique: string | null;
};

export type ResultatAnalyse = {
  lignes: EtudiantImporte[];
  erreurs: string[];
  ignorees: number;
  colonnesDetectees: Record<string, string>;
  colonnesIgnorees: string[];
  separateur: string;
};

const ALIASES: Record<string, string[]> = {
  matricule: ["matricule", "matriculeetudiant", "numero", "numeromatricule", "id", "codeetudiant", "no"],
  nom: ["nom", "nomdefamille", "lastname", "nomde famille", "noms"],
  prenom: ["prenom", "prenoms", "firstname", "prenom(s)"],
  sexe: ["sexe", "genre", "sex", "gender"],
  dateNaissance: ["datenaissance", "datedenaissance", "datedenaiss", "datenaiss", "datenais", "dateofbirth", "naissance", "ddn"],
  email: ["email", "mail", "courriel", "adressemail"],
  telephone: ["telephone", "tel", "phone", "contact", "mobile"],
  filiere: ["filiere", "mention", "ecole", "school", "departement", "mentiondorigine"],
  formation: ["formation", "parcours", "filiereformation", "filieredeformation", "formationdorigine", "intituleformation", "parcoursdeformation", "specialite", "programme", "option"],
  niveau: ["niveau", "level", "niveaudetude", "niveaudetudes", "classe", "anneeetude", "niveauscolaire"],
  groupe: ["groupe", "group", "grp", "groupeetudiants", "groupetd"],
  vague: ["vague", "promotion", "cohorte", "vagueadmission", "session"],
  semestre: ["semestre", "semester", "s", "sem"],
  statut: ["statut", "status", "etat", "situation"],
  anneeAcademique: ["anneeacademique", "annee", "anneescolaire", "academicyear", "promotionannee", "anneeuniversitaire"],
};

export function normaliserCle(valeur: string): string {
  return valeur
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

function detecterSeparateur(texte: string): string {
  const echantillon = texte.split(/\r?\n/).slice(0, 5).join("\n");
  const candidats = [";", ",", "\t", "|"];
  let meilleur = ",";
  let score = -1;
  for (const sep of candidats) {
    const n = echantillon.split(sep).length;
    if (n > score) {
      score = n;
      meilleur = sep;
    }
  }
  return meilleur;
}

export function parseCsv(texte: string, separateur?: string): string[][] {
  const contenu = texte.replace(/^\uFEFF/, "");
  const sep = separateur ?? detecterSeparateur(contenu);
  const lignes: string[][] = [];
  let cellule = "";
  let ligne: string[] = [];
  let entreGuillemets = false;
  for (let i = 0; i < contenu.length; i += 1) {
    const c = contenu[i];
    if (entreGuillemets) {
      if (c === '"' && contenu[i + 1] === '"') {
        cellule += '"';
        i += 1;
      } else if (c === '"') {
        entreGuillemets = false;
      } else {
        cellule += c;
      }
      continue;
    }
    if (c === '"') {
      entreGuillemets = true;
    } else if (c === sep) {
      ligne.push(cellule.trim());
      cellule = "";
    } else if (c === "\n") {
      ligne.push(cellule.trim());
      if (ligne.some((v) => v !== "")) lignes.push(ligne);
      ligne = [];
      cellule = "";
    } else if (c !== "\r") {
      cellule += c;
    }
  }
  ligne.push(cellule.trim());
  if (ligne.some((v) => v !== "")) lignes.push(ligne);
  return lignes;
}

function normaliserSexe(valeur: string): string {
  const v = normaliserCle(valeur);
  if (["m", "h", "masculin", "homme", "male"].includes(v)) return "M";
  if (["f", "feminin", "femme", "female"].includes(v)) return "F";
  return "";
}

function normaliserDate(valeur: string): string | null {
  const v = valeur.trim();
  if (!v) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  const fr = v.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  if (fr) return `${fr[3]}-${fr[2].padStart(2, "0")}-${fr[1].padStart(2, "0")}`;
  const iso = new Date(v);
  if (!Number.isNaN(iso.getTime())) return iso.toISOString().slice(0, 10);
  return null;
}

export function analyserLignes(rows: string[][], separateur = ";"): ResultatAnalyse {
  if (rows.length < 2) {
    return {
      lignes: [],
      erreurs: ["Fichier vide ou sans ligne d'en-tête exploitable."],
      ignorees: 0,
      colonnesDetectees: {},
      colonnesIgnorees: [],
      separateur,
    };
  }
  const entetes = rows[0].map((h) => h.trim());
  const index: Record<string, number> = {};
  const colonnesDetectees: Record<string, string> = {};
  const colonnesIgnorees: string[] = [];
  entetes.forEach((entete, i) => {
    const cle = normaliserCle(entete);
    const champ = Object.entries(ALIASES).find(([, aliases]) => aliases.includes(cle))?.[0];
    if (champ && index[champ] === undefined) {
      index[champ] = i;
      colonnesDetectees[champ] = entete;
    } else if (entete) {
      colonnesIgnorees.push(entete);
    }
  });

  const erreurs: string[] = [];
  if (index.nom === undefined && index.prenom === undefined) {
    erreurs.push("Colonnes 'nom' et/ou 'prenom' introuvables dans le fichier.");
  }

  const lignes: EtudiantImporte[] = [];
  let ignorees = 0;
  rows.slice(1).forEach((row, position) => {
    const ligne = position + 2;
    const lire = (champ: string) =>
      index[champ] !== undefined ? (row[index[champ]] ?? "").toString().trim() : "";
    const nom = lire("nom") || lire("prenom");
    const prenom = lire("prenom") || lire("nom");
    if (!nom) {
      ignorees += 1;
      return;
    }
    const matricule = lire("matricule").replace(/\s+/g, "");
    const niveau = normaliserNiveau(lire("niveau") || detecterNiveauDepuisGroupe(lire("groupe")));
    const semestreBrut = lire("semestre");
    const semestreNum = Number.parseInt(semestreBrut.replace(/^S/i, ""), 10);
    const semestre =
      !Number.isNaN(semestreNum) && semestreNum >= 1 && semestreNum <= 10 ? semestreNum : null;
    lignes.push({
      ligne,
      matricule: matricule || `IMP-${String(ligne).padStart(6, "0")}-${normaliserCle(nom).slice(0, 4).toUpperCase()}`,
      nom: nom.toUpperCase(),
      prenom,
      sexe: normaliserSexe(lire("sexe")) || (position % 2 === 0 ? "F" : "M"),
      dateNaissance: normaliserDate(lire("dateNaissance")),
      email: lire("email") || null,
      telephone: lire("telephone") || null,
      filiere: lire("filiere") || "STAPS",
      formation: lire("formation") || "EM",
      niveau,
      groupe: lire("groupe").toUpperCase(),
      vague: lire("vague").toUpperCase(),
      semestre,
      statut: (lire("statut") || "inscrit").toLowerCase(),
      anneeAcademique: lire("anneeAcademique") || null,
    });
  });

  return { lignes, erreurs, ignorees, colonnesDetectees, colonnesIgnorees, separateur };
}

function detecterNiveauDepuisGroupe(groupe: string): string {
  const m = (groupe || "").toUpperCase().match(/(L[1-3]|M[12])/);
  return m ? m[1] : "L1";
}

export function analyserContenuCsv(texte: string): ResultatAnalyse {
  const separateur = detecterSeparateur(texte.replace(/^\uFEFF/, ""));
  return analyserLignes(parseCsv(texte, separateur), separateur);
}

export function semestresCibles(ligne: EtudiantImporte): number[] {
  return ligne.semestre ? [ligne.semestre] : semestresDuNiveau(ligne.niveau);
}

export const MODELE_CSV = `matricule;nom;prenom;sexe;date_naissance;email;telephone;filiere;formation;niveau;groupe;vague;semestre;statut
INJS-2026-90001;KOUASSI;Jean;M;2004-03-14;jean.kouassi@example.com;+2250700000001;STAPS;EM;L1;EM-L1-G1;Vague 1;1;inscrit
INJS-2026-90002;DIALLO;Aminata;F;2003-11-02;aminata.diallo@example.com;+2250700000002;STAPS;ES;L2;ES-L2-G1;Vague 2;3;inscrit
INJS-2026-90003;YAO;Serge;M;2002-06-21;serge.yao@example.com;+2250700000003;STASE;MS;M1;MS-M1-G1;Vague 4;7;inscrit
`;
