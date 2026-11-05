/**
 * Moteur LMD de génération des emplois du temps — GET INJS APP.
 *
 * Principe : pour chaque semestre, on regroupe les groupes inscrits, on
 * programme les CM mutualisés (promotion), puis les TD et TP par groupe, en
 * respectant simultanément :
 *  - l'unicité d'une salle sur un créneau (par semestre, les périodes étant
 *    disjointes d'un semestre à l'autre),
 *  - l'unicité d'un enseignant sur un créneau,
 *  - l'unicité d'un groupe sur un créneau,
 *  - la capacité d'accueil des salles (meilleur ajustement),
 *  - les quotas hebdomadaires par groupe.
 * L'algorithme est déterministe (hash stable + tri par pénalité de créneau).
 */
import type {
  ConflitSeance,
  EngineGroupe,
  EngineModule,
  EngineSeance,
  GenerationInput,
  GenerationResult,
  GenerationStats,
  SlotDef,
} from "./types";

export const NIVEAUX = ["L1", "L2", "L3", "M1", "M2"] as const;

export const SEMESTRES_PAR_NIVEAU: Record<string, number[]> = {
  L1: [1, 2],
  L2: [3, 4],
  L3: [5, 6],
  M1: [7, 8],
  M2: [9, 10],
};

export function niveauDeSemestre(semestre: number): string {
  if (semestre <= 2) return "L1";
  if (semestre <= 4) return "L2";
  if (semestre <= 6) return "L3";
  if (semestre <= 8) return "M1";
  return "M2";
}

export function semestresDuNiveau(niveau: string): number[] {
  return SEMESTRES_PAR_NIVEAU[niveau?.toUpperCase()] ?? [1, 2];
}

export function normaliserNiveau(valeur: string): string {
  const v = (valeur || "").trim().toUpperCase().replace(/[\s-]/g, "");
  if (SEMESTRES_PAR_NIVEAU[v]) return v;
  const m = v.match(/^(LICENCE|LIC|L)([123])$/);
  if (m) return `L${m[2]}`;
  const mm = v.match(/^(MASTER|MAST|M)([12])$/);
  if (mm) return `M${mm[2]}`;
  if (/^[1-5]$/.test(v)) return NIVEAUX[Number(v) - 1];
  return "L1";
}

export function normaliserSemestre(valeur: string | number, niveau: string): number {
  const brut = String(valeur ?? "").trim().toUpperCase().replace(/^S/, "");
  const n = Number.parseInt(brut, 10);
  if (!Number.isNaN(n) && n >= 1 && n <= 10) return n;
  return semestresDuNiveau(niveau)[0];
}

const PREFERENCES_SALLE: Record<string, string[]> = {
  amphi: ["amphi", "conference", "cours"],
  cours: ["cours", "td", "conference"],
  td: ["td", "cours", "conference"],
  lab: ["lab", "td", "cours"],
  gym: ["gym", "dojo", "terrain"],
  dojo: ["dojo", "gym"],
  terrain: ["terrain", "gym"],
  piscine: ["piscine", "gym"],
  conference: ["conference", "cours", "amphi"],
};

function hashStable(valeur: string): number {
  let h = 2166136261;
  for (let i = 0; i < valeur.length; i += 1) {
    h ^= valeur.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

/**
 * Une grille hebdomadaire type accueille une séance récurrente par type et par
 * module. Les volumes complémentaires (heures au-delà de la séance de base)
 * relèvent des semaines d'approfondissement / du travail encadré, et non d'un
 * dédoublement systématique qui saturerait la semaine (27 à 32 créneaux).
 */
function nbSeances(heures: number): number {
  return heures > 0 ? 1 : 0;
}

function minutes(heure: string): number {
  const [h, m] = heure.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

type SeanceInterne = EngineSeance & { moduleCode?: string; formationCode?: string };

export function verifierConflits(seances: SeanceInterne[]): ConflitSeance[] {
  const conflits: ConflitSeance[] = [];
  const salles = new Map<string, SeanceInterne[]>();
  const profs = new Map<string, SeanceInterne[]>();
  const groupes = new Map<string, SeanceInterne[]>();
  const push = (map: Map<string, SeanceInterne[]>, key: string, seance: SeanceInterne) => {
    const liste = map.get(key) ?? [];
    liste.push(seance);
    map.set(key, liste);
  };
  for (const s of seances) {
    const creneau = `${s.semestre}|${s.jour}|${s.slotCode}`;
    push(salles, `${creneau}|${s.salleId}`, s);
    if (s.enseignantId) push(profs, `${creneau}|${s.enseignantId}`, s);
    for (const g of s.groupesCouverts) push(groupes, `${creneau}|${g}`, s);
  }
  const inspecter = (
    map: Map<string, SeanceInterne[]>,
    type: ConflitSeance["type"],
  ) => {
    for (const [key, liste] of map) {
      if (liste.length < 2) continue;
      const [semestre, jour, slotCode, ressource] = key.split("|");
      conflits.push({
        type,
        semestre: Number(semestre),
        jour: Number(jour),
        slotCode,
        ressource,
        seances: liste.map((s) => `${s.moduleCode ?? s.moduleId}/${s.typeSeance}/${s.jour}-${s.slotCode}`),
      });
    }
  };
  inspecter(salles, "salle");
  inspecter(profs, "enseignant");
  inspecter(groupes, "groupe");
  return conflits;
}

export function genererEmploiDuTemps(input: GenerationInput): GenerationResult {
  const debut = Date.now();
  const { options } = input;
  const alertes: string[] = [];
  const nonPlacees: GenerationResult["nonPlacees"] = [];
  const seances: SeanceInterne[] = [];

  const jours = input.jours.filter((j) => options.inclureSamedi || j.code !== 6);
  const slotsValides: SlotDef[] = input.slots.filter(
    (s) => !(options.eviterPauseMidi && s.penalty >= 5),
  );

  const creneaux: { jour: number; slot: SlotDef; score: number }[] = [];
  for (const jour of jours) {
    for (const slot of slotsValides) {
      if (jour.code === 6 && !slot.samedi) continue;
      creneaux.push({ jour: jour.code, slot, score: slot.penalty * 100 + jour.code * 7 });
    }
  }
  creneaux.sort((a, b) => a.score - b.score);

  if (creneaux.length === 0 || input.salles.length === 0) {
    return {
      seances: [],
      alertes: ["Aucun créneau ou aucune salle disponible : génération impossible."],
      nonPlacees: [],
      stats: statistiques([], [], input.salles.length, creneaux.length, options.semestres, debut),
    };
  }

  const sallesParType = new Map<string, typeof input.salles>();
  for (const salle of input.salles) {
    const liste = sallesParType.get(salle.type) ?? [];
    liste.push(salle);
    sallesParType.set(salle.type, liste);
  }
  for (const liste of sallesParType.values()) {
    liste.sort((a, b) => a.capacite - b.capacite || a.code.localeCompare(b.code));
  }
  const sallesTriees = [...input.salles].sort((a, b) => b.capacite - a.capacite);

  const profsParModule = new Map<string, number[]>();
  for (const aff of input.affectations) {
    const cle = `${aff.moduleId}|${aff.typeSeance}`;
    const liste = profsParModule.get(cle) ?? [];
    liste.push(aff.enseignantId);
    profsParModule.set(cle, liste);
  }
  const profsParSpecialite = new Map<string, number[]>();
  for (const prof of input.enseignants) {
    const liste = profsParSpecialite.get(prof.specialite) ?? [];
    liste.push(prof.id);
    profsParSpecialite.set(prof.specialite, liste);
  }

  const occupSalle = new Set<string>();
  const occupProf = new Set<string>();
  const occupGroupe = new Set<string>();
  const chargeGroupe = new Map<string, number>();
  const occupJour = new Map<string, number>();
  const cleChargeGroupe = (semestre: number, groupeId: number) => `${semestre}|${groupeId}`;
  const cleChargeProf = (semestre: number, profId: number) => `${semestre}|${profId}`;
  const chargeProf = new Map<string, number>();
  const sallesMobilisees = new Set<number>();
  const profsMobilises = new Set<number>();
  const placesEtudiantes = new Set<number>();

  const cle = (semestre: number, jour: number, slot: string, id: number) =>
    `${semestre}|${jour}|${slot}|${id}`;

  const construireIndexSalles = (need: string): (typeof input.salles)[number][] => {
    const types = PREFERENCES_SALLE[need] ?? ["cours", "td"];
    const liste: (typeof input.salles)[number][] = [];
    for (const type of types) liste.push(...(sallesParType.get(type) ?? []));
    return liste;
  };

  const choisirSalle = (
    need: string,
    effectif: number,
    semestre: number,
    jour: number,
    slot: string,
  ) => {
    const candidates = construireIndexSalles(need);
    for (const salle of candidates) {
      if (salle.capacite < effectif) continue;
      if (!occupSalle.has(cle(semestre, jour, slot, salle.id))) return salle;
    }
    // Aucune salle assez grande : on retient la plus grande disponible du type visé.
    for (let i = candidates.length - 1; i >= 0; i -= 1) {
      const salle = candidates[i];
      if (!occupSalle.has(cle(semestre, jour, slot, salle.id))) return salle;
    }
    for (const salle of sallesTriees) {
      if (!occupSalle.has(cle(semestre, jour, slot, salle.id))) return salle;
    }
    return null;
  };

  const choisirProf = (
    module: EngineModule,
    type: "CM" | "TD" | "TP",
    formationCode: string,
    semestre: number,
    jour: number,
    slot: string,
  ) => {
    const directs = profsParModule.get(`${module.id}|${type}`) ?? [];
    const secours = profsParModule.get(`${module.id}|CM`) ?? [];
    const specialite = profsParSpecialite.get(formationCode) ?? [];
    // Dernier recours : tout enseignant disponible (formations importées sans
    // affectation explicite), en équilibrant les charges.
    const global = input.enseignants.map((enseignant) => enseignant.id);
    const candidats = [...new Set([...directs, ...secours, ...specialite, ...global])].filter(
      (id) => !occupProf.has(cle(semestre, jour, slot, id)),
    );
    if (candidats.length === 0) return null;
    // Équilibrage des charges : on retient l'enseignant disponible le moins chargé.
    candidats.sort(
      (a, b) =>
        (chargeProf.get(cleChargeProf(semestre, a)) ?? 0) -
        (chargeProf.get(cleChargeProf(semestre, b)) ?? 0),
    );
    return candidats[0];
  };

  const trierCreneaux = (
    module: EngineModule,
    libelleGroupe: string,
    groupes: EngineGroupe[],
    semestre: number,
  ) => {
    const bruit = hashStable(`${module.code}|${libelleGroupe}|${options.seed}`) % 97;
    const score = (candidat: { jour: number; slot: SlotDef; score: number }) => {
      const chargeJour = groupes.reduce(
        (total, g) => total + (occupJour.get(`${semestre}|${candidat.jour}|${g.id}`) ?? 0),
        0,
      );
      return candidat.score + chargeJour * 9 + ((bruit + candidat.jour) % 5);
    };
    return [...creneaux].sort(
      (a, b) => score(a) - score(b) || a.jour - b.jour || a.slot.code.localeCompare(b.slot.code),
    );
  };

  type Demande = {
    semestre: number;
    formationId: number;
    module: EngineModule;
    type: "CM" | "TD" | "TP";
    groupes: EngineGroupe[];
    need: string;
    effectif: number;
    libelle: string;
    verifierQuota: boolean;
  };

  const placer = (demande: Demande): boolean => {
    const { semestre, module, type, groupes } = demande;
    if (
      demande.verifierQuota &&
      groupes.some(
        (g) => (chargeGroupe.get(cleChargeGroupe(semestre, g.id)) ?? 0) >= options.maxSeancesParGroupe,
      )
    ) {
      nonPlacees.push({
        semestre,
        formationId: demande.formationId,
        moduleCode: module.code,
        groupeCode: groupes.map((g) => g.code).join(", "),
        typeSeance: type,
        raison: "Quota hebdomadaire du groupe atteint",
      });
      return false;
    }

    for (const creneau of trierCreneaux(module, demande.libelle, groupes, semestre)) {
      const { jour, slot } = creneau;
      if (groupes.some((g) => occupGroupe.has(cle(semestre, jour, slot.code, g.id)))) continue;
      const salle = choisirSalle(demande.need, demande.effectif, semestre, jour, slot.code);
      if (!salle) continue;
      const prof = choisirProf(module, type, groupes[0]?.formationCode ?? "", semestre, jour, slot.code);
      if (!prof) continue;

      const seance: SeanceInterne = {
        formationId: demande.formationId,
        moduleId: module.id,
        groupeId: groupes.length === 1 ? groupes[0].id : null,
        vagueId: groupes.length >= 1 ? groupes[0].vagueId : null,
        enseignantId: prof,
        salleId: salle.id,
        niveau: groupes[0]?.niveau ?? niveauDeSemestre(semestre),
        semestre,
        typeSeance: type,
        jour,
        slotCode: slot.code,
        heureDebut: slot.debut,
        heureFin: slot.fin,
        effectif: demande.effectif,
        groupesCouverts: groupes.map((g) => g.id),
        moduleCode: module.code,
        formationCode: groupes[0]?.formationCode,
      };
      seances.push(seance);
      occupSalle.add(cle(semestre, jour, slot.code, salle.id));
      occupProf.add(cle(semestre, jour, slot.code, prof));
      const cleProf = cleChargeProf(semestre, prof);
      chargeProf.set(cleProf, (chargeProf.get(cleProf) ?? 0) + 1);
      for (const g of groupes) {
        occupGroupe.add(cle(semestre, jour, slot.code, g.id));
        const cleGroupe = cleChargeGroupe(semestre, g.id);
        chargeGroupe.set(cleGroupe, (chargeGroupe.get(cleGroupe) ?? 0) + 1);
        const jourCle = `${semestre}|${jour}|${g.id}`;
        occupJour.set(jourCle, (occupJour.get(jourCle) ?? 0) + 1);
      }
      sallesMobilisees.add(salle.id);
      profsMobilises.add(prof);
      for (const g of groupes) placesEtudiantes.add(g.id);
      return true;
    }

    nonPlacees.push({
      semestre,
      formationId: demande.formationId,
      moduleCode: module.code,
      groupeCode: groupes.map((g) => g.code).join(", "),
      typeSeance: type,
      raison: "Aucun créneau compatible (salle, enseignant ou indisponibilité)",
    });
    return false;
  };

  const semestres = [...new Set(options.semestres)].sort((a, b) => a - b);
  const modulesParFormation = new Map<string, EngineModule[]>();
  for (const module of input.modules) {
    const clef = `${module.formationId}|${module.semestre}`;
    const liste = modulesParFormation.get(clef) ?? [];
    liste.push(module);
    modulesParFormation.set(clef, liste);
  }
  for (const liste of modulesParFormation.values()) liste.sort((a, b) => a.code.localeCompare(b.code));

  for (const semestre of semestres) {
    if (semestre < 1 || semestre > 10) {
      alertes.push(`Semestre ${semestre} ignoré (hors plage LMD 1–10).`);
      continue;
    }
    const groupesSemestre = input.groupes
      .filter((g) => g.semestres.includes(semestre))
      .sort((a, b) => a.formationCode.localeCompare(b.formationCode) || a.code.localeCompare(b.code));
    if (groupesSemestre.length === 0) {
      alertes.push(`Semestre ${semestre} : aucun groupe inscrit, aucun emploi du temps généré.`);
      continue;
    }
    const parFormation = new Map<number, EngineGroupe[]>();
    for (const groupe of groupesSemestre) {
      const liste = parFormation.get(groupe.formationId) ?? [];
      liste.push(groupe);
      parFormation.set(groupe.formationId, liste);
    }

    for (const [formationId, groupesFormation] of [...parFormation.entries()].sort((a, b) => a[0] - b[0])) {
      const modules = modulesParFormation.get(`${formationId}|${semestre}`) ?? [];
      if (modules.length === 0) {
        alertes.push(
          `Aucune maquette pour la formation ${groupesFormation[0]?.formationCode ?? formationId} au semestre ${semestre}.`,
        );
        continue;
      }

      // 1. Cours magistraux mutualisés par promotion (découpage selon la plus grande salle).
      for (const module of modules) {
        const nbCm = nbSeances(module.heuresCm);
        if (nbCm === 0) continue;
        const sallesCm = construireIndexSalles(module.roomNeedCm);
        const capaciteMax = Math.max(...input.salles.map((s) => s.capacite), 1);
        const capaciteCible = Math.max(
          ...sallesCm.map((s) => s.capacite),
          1,
        ) || capaciteMax;
        const trie = [...groupesFormation].sort((a, b) => b.effectif - a.effectif);
        const lots: EngineGroupe[][] = [];
        let lot: EngineGroupe[] = [];
        let cumul = 0;
        for (const groupe of trie) {
          if (lot.length > 0 && cumul + groupe.effectif > capaciteCible) {
            lots.push(lot);
            lot = [];
            cumul = 0;
          }
          lot.push(groupe);
          cumul += groupe.effectif;
        }
        if (lot.length > 0) lots.push(lot);

        for (let occurrence = 0; occurrence < nbCm; occurrence += 1) {
          for (const groupesCm of lots) {
            placer({
              semestre,
              formationId,
              module,
              type: "CM",
              groupes: groupesCm,
              need: module.roomNeedCm,
              effectif: groupesCm.reduce((total, g) => total + g.effectif, 0),
              libelle: `CM-${module.code}`,
              verifierQuota: false,
            });
          }
        }
      }

      // 2. Travaux dirigés puis travaux pratiques, par groupe.
      for (const groupe of groupesFormation) {
        for (const module of modules) {
          const nbTd = nbSeances(module.heuresTd);
          for (let i = 0; i < nbTd; i += 1) {
            placer({
              semestre,
              formationId,
              module,
              type: "TD",
              groupes: [groupe],
              need: module.roomNeedTd,
              effectif: groupe.effectif,
              libelle: `TD-${module.code}-${groupe.code}-${i}`,
              verifierQuota: true,
            });
          }
        }
        // TP : priorisation des modules les plus pratiques, dans la limite du
        // budget hebdomadaire du groupe.
        const modulesTp = modules
          .filter((module) => module.heuresTp > 0)
          .sort((a, b) => b.heuresTp - a.heuresTp || a.code.localeCompare(b.code))
          .slice(0, Math.max(1, options.maxTpParGroupe ?? 4));
        for (const module of modulesTp) {
          const nbTp = nbSeances(module.heuresTp);
          for (let i = 0; i < nbTp; i += 1) {
            placer({
              semestre,
              formationId,
              module,
              type: "TP",
              groupes: [groupe],
              need: module.roomNeedTp,
              effectif: Math.max(1, Math.min(groupe.effectif, 60)),
              libelle: `TP-${module.code}-${groupe.code}-${i}`,
              verifierQuota: true,
            });
          }
        }
      }
    }
  }

  const conflits = verifierConflits(seances);
  if (conflits.length > 0) {
    alertes.push(`${conflits.length} conflit(s) résiduel(s) détecté(s) : arbitrage manuel requis.`);
  }
  if (nonPlacees.length > 0) {
    alertes.push(
      `${nonPlacees.length} séance(s) non placée(s). Réduisez le périmètre ou activez le samedi / les créneaux supplémentaires.`,
    );
  }
  const profsSurchargesParSemestre = [...chargeProf.entries()].filter(([, n]) => n > 16);
  const profsSurcharges = profsSurchargesParSemestre;
  if (profsSurcharges.length > 0) {
    alertes.push(
      `${profsSurcharges.length} enseignant(s) dépassent 16 séances hebdomadaires (32 h) : vérifier les charges.`,
    );
  }

  const duree = Date.now() - debut;
  const stats: GenerationStats = statistiques(
    seances,
    nonPlacees,
    input.salles.length,
    creneaux.length,
    semestres,
    debut,
  );
  stats.groupes = new Set(seances.flatMap((s) => s.groupesCouverts)).size;
  stats.modules = new Set(seances.map((s) => s.moduleId)).size;
  stats.sallesMobilisees = sallesMobilisees.size;
  stats.enseignantsMobilises = profsMobilises.size;
  stats.placesEtudiantes = [...placesEtudiantes].reduce((total, id) => {
    const groupe = input.groupes.find((g) => g.id === id);
    return total + (groupe?.effectif ?? 0);
  }, 0);
  stats.conflits = conflits.length;
  stats.dureeMs = duree;
  return { seances, stats, alertes, nonPlacees };
}

function statistiques(
  seances: SeanceInterne[],
  nonPlacees: GenerationResult["nonPlacees"],
  nbSalles: number,
  nbCreneaux: number,
  semestres: number[],
  debut: number,
): GenerationStats {
  const capaciteTotale = Math.max(1, nbSalles * nbCreneaux * Math.max(1, semestres.length));
  return {
    seances: seances.length,
    cm: seances.filter((s) => s.typeSeance === "CM").length,
    td: seances.filter((s) => s.typeSeance === "TD").length,
    tp: seances.filter((s) => s.typeSeance === "TP").length,
    groupes: 0,
    modules: 0,
    sallesMobilisees: 0,
    enseignantsMobilises: 0,
    placesEtudiantes: 0,
    nonPlacees: nonPlacees.length,
    conflits: 0,
    tauxCouverture:
      seances.length + nonPlacees.length === 0
        ? 0
        : Math.round((seances.length / (seances.length + nonPlacees.length)) * 1000) / 10,
    tauxOccupationSalles: Math.round((seances.length / capaciteTotale) * 1000) / 10,
    dureeMs: Date.now() - debut,
    parSemestre: semestres.map((semestre) => ({
      semestre,
      seances: seances.filter((s) => s.semestre === semestre).length,
      nonPlacees: nonPlacees.filter((n) => n.semestre === semestre).length,
    })),
  };
}

export function minutesEntre(debut: string, fin: string): number {
  return minutes(fin) - minutes(debut);
}
