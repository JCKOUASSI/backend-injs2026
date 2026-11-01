# Livrable 11 — Intégrations intermodules

Le module Référentiels n'est utile que s'il est **réellement branché** : chaque
liaison ci-dessous est un champ de base ou un appel d'API vérifié, jamais une
intention.

## 11.1 Liaisons par clé étrangère (base)

| Source | Cible | Mode | Effet |
|---|---|---|---|
| `formations.RefFormation.filiere` (`formations.0099`) | `referentiels.RefFiliere` | `PROTECT`, `SET_NULL` en cas d'absence | Une filière utilisée ne peut plus être supprimée ; les 8 cycles importés pointent sur leur filière (F01→EM … F08→GER) |
| `formations.RefVague.statut` (`formations.0099`) | `referentiels.RefStatutVague` | `PROTECT` | Le statut de vague devient une valeur du référentiel au lieu d'une chaîne libre |
| `formations.RefSite` / `RefBatiment` / `RefSalle` (`formations.0100`) | — | champs ajoutés | `source_document` + `fiabilite` : la provenance des lieux est traçable comme celle des autres référentiels |

## 11.2 Liaisons par API (frontend ↔ backend)

| Écran | Appel | Usage |
|---|---|---|
| Tableau de bord | `GET /api/referentiels/tableau-de-bord/` | Catégories, entrées, volumétrie, traçabilité, routes réelles |
| Gestion générique | `GET/POST/PATCH /api/referentiels/{slug}/` | CRUD du référentiel sélectionné par l'URL |
| Sélecteurs dépendants | `GET` sur la route déclarée par le registre (`route_api` de chaque entrée) | Ex. mentions filtrées par école |
| Écrans de lecture | `GET /api/referentiels/modules-officiels/`, `/volumes-horaires/` | Données importées, non modifiables |
| Journal | `GET /api/referentiels/journal/` | Traçabilité des quatre opérations |

## 11.3 Modules consommateurs existants

| Module | Consommation | État |
|---|---|---|
| `formations` | `RefVague` (candidatures, admissions, groupes, inscriptions), `RefFormation` | **Branché** : les FK existantes continuent de fonctionner ; `statut` et `filiere` ajoutés sont facultatifs |
| `admissions` | `RefVague` sur `Candidature` et `Admission` | **Branché** (aucune modification nécessaire) |
| `scolarite` | `AnneeAcademique`, `Niveau`, `Semestre`, `Parcours`, `UE`/`ECUE` | **Hébergé** : le tableau de bord y renvoie, sans dupliquer les tables |
| `scolarite.pedagogie_validateur` | Liste `FILIERES` **codée en dur** (8 codes) | **Contrôlé** : `verifier_coherence_referentiels` compare la liste du code et la table ; aligné à ce jour, divergence signalée sinon |

## 11.4 Ce qui n'a pas été branché, et pourquoi

| Piste | Décision | Raison |
|---|---|---|
| Remplacer `FILIERES` codé en dur par une lecture de la base dans `pedagogie_validateur` | **Non** | Le module de validation est appelé à l'import de fichiers, parfois sans base initialisée ; un accès DB au chargement du module casserait ce chemin. Le contrôle de cohérence rend la divergence visible sans modifier le pipeline |
| Réécrire `scolarite.TypeFormation` en `RefTypeCursus` | **Non** | Deux tables coexistent : `TypeFormation` porte LICENCE/MASTER/INITIALE/CONTINUE, `RefTypeCursus` les natures de cursus de la refonte. La fusion suppose de migrer des FK utilisées par `admissions` — trop risqué pour être fait sans validation métier. Documenté en anomalie **A-53-01** |
| Consommer les volumes horaires dans la charge enseignant | **Non** | La source qualifie elle-même ces volumes de « proposition ». Les brancher reviendrait à traiter des valeurs non réglementaires comme officielles |
| Générer les maquettes depuis les modules officiels | **Non** | Les modules sont importés avec un état de ventilation `A_VENTILER` : la ventilation UE/ECUE relève d'une décision pédagogique (anomalie **A-53-06**) |

## 11.5 Contrôles exécutés

| Contrôle | Résultat |
|---|---|
| `verifier_coherence_referentiels` | 1 constat : une formation historique sans filière (**A-53-03**) |
| Alignement liste codée en dur ↔ table | 8 codes, alignés |
| Routes déclarées au registre | toutes servies (`test_route_api_declaree_existe_vraiment`) |
| Suppression d'une valeur utilisée | impossible (`PROTECT`) — vérifié par les migrations et les tests `formations` |
