# Rapport de génération — kit de remplissage INJS 2026

Généré le 15/11/2026 à 18:33 par `python manage.py generer_kit_remplissage`.

## Dénombrements

- Référentiels du Hub (modules) : **27**
- Fichiers Excel générés : **31** (27 référentiels + guide, index, ordre, démonstration)
- Fichiers CSV générés : **27**
- Fichier PDF : **1** (guide)
- Colonnes de saisie au total : **178**

## Répartition par catégorie

| Catégorie | Dossier | Référentiels | Colonnes |
|---|---|---|---|
| institutionnel | `01_INSTITUTIONNEL` | 2 | 13 |
| offre-formation | `02_OFFRE_DE_FORMATION` | 5 | 45 |
| pedagogique | `03_PEDAGOGIQUE` | 4 | 22 |
| organisation | `04_ORGANISATION_ET_INFRASTRUCTURES` | 5 | 38 |
| ressources-humaines | `05_RESSOURCES_HUMAINES` | 1 | 5 |
| scolarite | `06_SCOLARITE` | 5 | 28 |
| systeme-lmd | `07_SYSTEME_LMD` | 5 | 27 |

## Correspondance modèle par modèle

| Référentiel | Modèle Django | Colonnes | Obligatoires | Liaisons | Importable | Fichier |
|---|---|---|---|---|---|---|
| Écoles | `referentiels.RefEcole` | 6 | 3 | 1 | oui | `Écoles.xlsx` |
| Mentions | `referentiels.RefMention` | 7 | 3 | 2 | oui | `Mentions.xlsx` |
| Natures de cursus | `referentiels.RefTypeCursus` | 5 | 3 | 1 | oui | `Natures_de_cursus.xlsx` |
| Filières | `referentiels.RefFiliere` | 10 | 5 | 4 | oui | `Filières.xlsx` |
| Formations (cycles) | `formations.RefFormation` | 15 | 3 | 1 | oui | `Formations_cycles.xlsx` |
| Modules officiels | `referentiels.RefModuleOfficiel` | 7 | 5 | 1 | oui | `Modules_officiels.xlsx` |
| Volumes horaires (modélisation) | `referentiels.RefVolumeHoraireFormation` | 8 | 3 | 1 | oui | `Volumes_horaires_modélisation.xlsx` |
| Statuts de vague | `referentiels.RefStatutVague` | 6 | 4 | 1 | oui | `Statuts_de_vague.xlsx` |
| Sites | `formations.RefSite` | 5 | 3 | 0 | oui | `Sites.xlsx` |
| Bâtiments | `formations.RefBatiment` | 3 | 3 | 1 | oui | `Bâtiments.xlsx` |
| Salles et espaces | `formations.RefSalle` | 11 | 4 | 3 | oui | `Salles_et_espaces.xlsx` |
| Vagues | `formations.RefVague` | 13 | 3 | 5 | oui | `Vagues.xlsx` |
| Types d'enseignement | `referentiels.RefTypeEnseignement` | 7 | 4 | 1 | oui | `Types_denseignement.xlsx` |
| Types d'évaluation | `referentiels.RefTypeEvaluation` | 5 | 3 | 1 | oui | `Types_dévaluation.xlsx` |
| Types de décision | `referentiels.RefTypeDecision` | 5 | 3 | 1 | oui | `Types_de_décision.xlsx` |
| Types d'espace sportif | `referentiels.RefTypeEspaceSportif` | 5 | 3 | 1 | oui | `Types_despace_sportif.xlsx` |
| Grades enseignants | `referentiels.RefGradeEnseignant` | 5 | 3 | 1 | oui | `Grades_enseignants.xlsx` |
| Types de document | `referentiels.RefTypeDocument` | 5 | 3 | 1 | oui | `Types_de_document.xlsx` |
| Types de frais | `referentiels.RefTypeFrais` | 5 | 3 | 1 | oui | `Types_de_frais.xlsx` |
| Modes de paiement | `referentiels.RefModePaiement` | 5 | 3 | 1 | oui | `Modes_de_paiement.xlsx` |
| Types de notification | `referentiels.RefTypeNotification` | 5 | 3 | 1 | oui | `Types_de_notification.xlsx` |
| Années académiques | `scolarite.AnneeAcademique` | 8 | 6 | 0 | oui | `Années_académiques.xlsx` |
| Niveaux | `scolarite.Niveau` | 6 | 6 | 0 | oui | `Niveaux.xlsx` |
| Semestres | `scolarite.Semestre` | 4 | 4 | 1 | oui | `Semestres.xlsx` |
| Parcours | `scolarite.Parcours` | 5 | 4 | 2 | oui | `Parcours.xlsx` |
| Types de formation | `scolarite.TypeFormation` | 3 | 3 | 0 | oui | `Types_de_formation.xlsx` |
| UE / ECUE | `scolarite.UE` | 9 | 8 | 3 | non | `UE_ECUE.xlsx` |

## Source des données

- Les colonnes proviennent de `colonnes.champs_importables()` : exactement ce que le moteur d'import sait résoudre.
- Les listes de valeurs et les exemples sont lus depuis la base locale, jamais reconstitués.
- Les en-têtes sont vérifiés à la génération : chacun doit rester reconnu par le moteur d'import, sinon la commande échoue.
