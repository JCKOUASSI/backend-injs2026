# Livrable 11 — Bilan des intégrations intermodules

Principe : une intégration n'est déclarée « branchée » que si une **clé étrangère réelle** (ou un appel d'API réel) relie les deux modules. Aucune liaison n'est simulée.

## 11.1 Intégrations effectives

| Module consommateur | Référentiel consommé | Mécanisme | État |
|---|---|---|---|
| **Formations** | `RefFiliere` | FK `RefFormation.filiere` (PROTECT) — migration `formations.0099` | **Branché** |
| **Formations** | `RefStatutVague` | FK `RefVague.statut` (PROTECT) | **Branché** |
| **Formations / EDT** | `RefSite`, `RefBatiment`, `RefSalle` | FK existantes ; `source_document` + `fiabilite` ajoutés | **Branché** |
| **Admissions** | `formations.RefVague` | FK `Candidature.vague`, `Admission.vague` | **Branché (via la vague)** |
| **Scolarité** | `formations.RefFormation`, `RefVague` | FK `Parcours`, `InscriptionLMD` | **Branché** |
| **Maquettes** | `scolarite.Niveau`, `Semestre`, `UE`, `ECUE` | FK existantes | **Branché** |
| **Référentiels** | `formations.RefFormation` | FK `RefModuleOfficiel.formation`, `RefVolumeHoraireFormation.formation` | **Branché** |

## 11.2 Intégrations non branchées (assumées)

| Module | Référentiel attendu | Pourquoi ce n'est pas branché | Risque |
|---|---|---|---|
| **Maquettes / UE-ECUE** | `RefModuleOfficiel` | Le document source ne ventile pas les modules en UE/ECUE. Créer la ventilation serait une donnée fictive. Chaque ligne porte `etat_ventilation = A_VENTILER` | Visible dans l'écran (état « À ventiler ») ; aucune maquette fausse n'est produite |
| **Évaluations / Notes / Jurys** | types d'évaluation, types de décision | Les ViewSets dédiés existent et sont consommés, mais **aucun type d'évaluation ni de décision n'est renseigné** dans la base (0 valeur) : la décision relève de l'INJS | Écrans d'évaluation fonctionnent avec leurs listes actuelles ; les listes de types restent vides et l'indiquent |
| **Diplômes / Statistiques** | mentions, écoles | Les FK existent côté référentiel, mais les diplômes actuels ne portent pas encore `mention`/`ecole` | Aucune agrégation par école n'est possible pour l'instant |
| **GET-INJS / EDT** | volumes horaires | Les volumes sont `MODELISE` (proposition) : ils ne doivent pas alimenter automatiquement la génération d'emploi du temps sans validation | Non branché volontairement |
| **RH pédagogiques** | grades enseignants | Référentiel vide (0 valeur) : la nomenclature des grades n'apparaît dans aucun des 5 documents | Écran vide, signalé « Non renseigné » |

## 11.3 Intégrations vérifiées par test

| Test | Vérifie |
|---|---|
| `test_selecteurs_resolus_par_modele` | Les routes des sélecteurs (école, mention, nature de cursus) sont correctes et réellement servies |
| `test_filieres_rattachees_par_code_dossier` | Un module officiel est rattaché au cycle de **sa** filière (pas de rapprochement par libellé) |
| `test_curp` / tests de permissions | Les 8 ViewSets du socle conservent leurs URLs et leur comportement d'archivage |
| `formations` — 272 tests | La FK `filiere` et `RefVague.categorie` ne cassent aucun écran de formations |
| `scolarite` — 481 tests | Les maquettes, inscriptions et parcours fonctionnent toujours |
| `admissions` — 80 tests | Les vagues et statuts restent compatibles |

## 11.4 Points de vigilance transmis

1. **Ne jamais déduire un rattachement d'un libellé** : la clé est `RefFiliere.code_dossier` (F01…F08). Un rapprochement textuel a produit des erreurs réelles pendant la mission (APA ↔ ES, MS ↔ APA) avant correction.
2. **Les volumes horaires ne sont pas une norme** : toute consommation automatique (charge enseignante, EDT) doit afficher la mention « modélisé ».
3. **`scolarite.TypeFormation` est encore vivant** : toute nouvelle fonctionnalité doit lire `RefTypeCursus`, jamais `TypeFormation`.
