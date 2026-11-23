# Livrable 2 — Matrice de correspondance documents → référentiels

Chaque ligne répond à trois questions : **quelle source** atteste la donnée, **quel référentiel** la porte dans le SI, et **quelle fiabilité** lui est attachée. Aucune ligne ne provient d'une supposition : quand la source est muette, la colonne « Référentiel » indique `— (non renseigné)`.

## 1. Nomenclatures institutionnelles

| Donnée | Valeurs documentées | Source | Référentiel (modèle) | Fiabilité |
|---|---|---|---|---|
| Écoles | ENSEPS, ENSEP | F1 §1 | `referentiels.RefEcole` | OFFICIEL |
| Mentions | STAPS → ENSEPS, STASE → ENSEP | F1 §2 | `referentiels.RefMention` | OFFICIEL |
| Filières métier | F01 EM, F02 APA, F03 ES, F04 MS, F05 AND, F06 LOI, F07 ECJP, F08 GER | F1 §3 | `referentiels.RefFiliere` (+ `code_dossier`) | OFFICIEL |
| Natures de cursus | Cursus LMD ; professionnel, continu, à la carte, concours | F1 §1 + cadrage §5 | `referentiels.RefTypeCursus` | OFFICIEL (LMD) / CADRAGE (4 autres) |

## 2. Offre de formation

| Donnée | Valeurs documentées | Source | Référentiel | Fiabilité |
|---|---|---|---|---|
| Cycles LMD | 8 cycles : F01–F04 × {Licence, Master} | F1 §4 | `formations.RefFormation` (+ FK `filiere`) | OFFICIEL |
| Modules officiels | 227 modules, par filière et semestre quand il est précisé | F1 §5 | `referentiels.RefModuleOfficiel` | OFFICIEL |
| Volumes horaires | CM/TD/TP/stage/total pour EM L, EM M, APA L, APA M | F3 | `referentiels.RefVolumeHoraireFormation` | MODELISE |
| Types d'enseignement | CM, TD, TP, Stage | F3 (en-têtes de colonnes) | `referentiels.RefTypeEnseignement` | OFFICIEL |

## 3. Organisation physique

| Donnée | Valeurs documentées | Source | Référentiel | Fiabilité |
|---|---|---|---|---|
| Site | INJS Marcory | F2 | `formations.RefSite` | OFFICIEL |
| Bâtiments | 16 bâtiments | F2 | `formations.RefBatiment` | MODELISE |
| Espaces | 166 espaces (amphis, salles, labos, gymnases, terrains) | F2 | `formations.RefSalle` | MODELISE |
| Types d'espace sportif | Amphi, gymnase, salle informatique, salle de réunion, salle de TD, terrain extérieur | F2 (vocabulaire des espaces) | `referentiels.RefTypeEspaceSportif` | A_RENSEIGNER (créés avant la refonte, à raccrocher à F2) |

## 4. Scolarité et vie académique

| Donnée | Valeurs documentées | Source | Référentiel | Fiabilité |
|---|---|---|---|---|
| Statuts de vague | Prévisionnelle, Ouverte, En cours, Clôturée, Terminée | F4 | `referentiels.RefStatutVague` | OFFICIEL |
| Vagues | 1re, 2e, 3e vague 2026 | F4 | `formations.RefVague` (écran historique) | OFFICIEL |
| Années académiques | 2026-2027 (année courante) | SI existant | `scolarite.AnneeAcademique` (écran historique) | — (hors source documentaire) |
| Niveaux | L1, L2, L3, M1, M2 | Chaîne LMD (cadrage) | `scolarite.Niveau` | CADRAGE |
| Semestres | S1 → S10 (30 ECTS/semestre, 60/niveau) | Cadrage LMD | `scolarite.Semestre` | CADRAGE |
| Parcours | 7 parcours existants | SI existant | `scolarite.Parcours` | — |
| UE / ECUE | 3 maquettes existantes | SI existant | `scolarite.Maquette/UE/ECUE` | — |

## 5. Ce que les documents ne contiennent pas

| Donnée attendue | Déclaré dans les documents ? | Traitement |
|---|---|---|
| Crédits ECTS par module | Non | Aucune valeur créée ; champ laissé vide côté maquettes |
| Ventilation UE / ECUE des modules officiels | Non | `RefModuleOfficiel.etat_ventilation = A_VENTILER` |
| Règles de jury, seuils, compensations | Non | Aucune règle importée |
| Décisions académiques V01–V14 | Non | Non modélisées comme référentiel |
| Effectifs et calendrier des vagues | Non | Non renseignés |
| Horaires par espace / capacité systématique | Partiel | `capacite` laissée vide quand la source ne la donne pas |

## 6. Règle de non-duplication appliquée

| Cas | Décision |
|---|---|
| F5 duplique F2 | Un seul import (F2) ; F5 reste une pièce justificative |
| `scolarite.TypeFormation` (hérité) vs `referentiels.RefTypeCursus` | Le second devient la référence métier ; le premier reste en place, **signalé** (anomalie A-53-01) tant que ses dépendances (FK `admissions.ReglePiece`, `scolarite.Parcours`) n'ont pas été migrées |
| Modules officiels vs `formations.RefModule` | Deux objets distincts : `RefModuleOfficiel` = nomenclature documentaire (lecture seule) ; `RefModule` = module opérationnel d'une maquette. Aucune fusion : le rapprochement se fera par ventilation explicite, jamais par déduction de libellé |
