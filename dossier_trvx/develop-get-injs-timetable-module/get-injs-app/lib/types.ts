/** Types du moteur de génération GET INJS (aucune dépendance framework). */

export type SlotDef = {
  code: string;
  label: string;
  debut: string;
  fin: string;
  penalty: number;
  samedi: boolean;
  partie?: string;
};

export type JourDef = { code: number; label: string };

export type EngineSalle = {
  id: number;
  code: string;
  type: string;
  capacite: number;
  batiment?: string;
};

export type EngineEnseignant = {
  id: number;
  matricule: string;
  nom: string;
  specialite: string;
};

export type EngineModule = {
  id: number;
  code: string;
  titre: string;
  formationId: number;
  semestre: number;
  nature: string;
  heuresCm: number;
  heuresTd: number;
  heuresTp: number;
  roomNeedCm: string;
  roomNeedTd: string;
  roomNeedTp: string;
};

export type EngineGroupe = {
  id: number;
  code: string;
  formationId: number;
  formationCode: string;
  niveau: string;
  vagueId: number | null;
  effectif: number;
  semestres: number[];
};

export type Affectation = {
  moduleId: number;
  enseignantId: number;
  typeSeance: string;
};

export type GenerationOptions = {
  semestres: number[];
  maxSeancesParGroupe: number;
  inclureSamedi: boolean;
  eviterPauseMidi: boolean;
  seed: number;
  maxSemestreParGroupe?: number;
  /** Nombre maximal de TP hebdomadaires par groupe (priorisation par volume). */
  maxTpParGroupe?: number;
};

export type EngineSeance = {
  formationId: number;
  moduleId: number;
  groupeId: number | null;
  vagueId: number | null;
  enseignantId: number | null;
  salleId: number;
  niveau: string;
  semestre: number;
  typeSeance: "CM" | "TD" | "TP";
  jour: number;
  slotCode: string;
  heureDebut: string;
  heureFin: string;
  effectif: number;
  groupesCouverts: number[];
};

export type GenerationInput = {
  anneeCode: string;
  groupes: EngineGroupe[];
  modules: EngineModule[];
  salles: EngineSalle[];
  enseignants: EngineEnseignant[];
  affectations: Affectation[];
  slots: SlotDef[];
  jours: JourDef[];
  options: GenerationOptions;
};

export type ConflitSeance = {
  type: "salle" | "enseignant" | "groupe";
  semestre: number;
  jour: number;
  slotCode: string;
  ressource: string;
  seances: string[];
};

export type GenerationStats = {
  seances: number;
  cm: number;
  td: number;
  tp: number;
  groupes: number;
  modules: number;
  sallesMobilisees: number;
  enseignantsMobilises: number;
  placesEtudiantes: number;
  nonPlacees: number;
  conflits: number;
  tauxCouverture: number;
  tauxOccupationSalles: number;
  dureeMs: number;
  parSemestre: { semestre: number; seances: number; nonPlacees: number }[];
};

export type GenerationResult = {
  seances: EngineSeance[];
  stats: GenerationStats;
  alertes: string[];
  nonPlacees: {
    semestre: number;
    formationId: number;
    moduleCode: string;
    groupeCode: string;
    typeSeance: string;
    raison: string;
  }[];
};
