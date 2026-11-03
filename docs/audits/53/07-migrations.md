# Livrable 7 — Migrations

Toutes les migrations ont été **appliquées** sur la base de développement (`manage.py migrate`, SQLite via `USE_SQLITE=1`). Aucune n'est destructive : elles n'ajoutent que des champs nullables ou des tables nouvelles.

## 7.1 Migrations `referentiels`

| Fichier | Contenu | Destructive ? | État |
|---|---|---|---|
| `0002_refgradeenseignant_fiabilite_and_more.py` | Ajout de `fiabilite` aux 8 référentiels du socle + création des modèles de la refonte (écoles, mentions, natures de cursus, filières, statuts de vague, types d'enseignement, types d'espace sportif) | Non (champs nullables + `CreateModel`) | Appliquée |
| `0003_refmoduleofficiel.py` | `CreateModel RefModuleOfficiel` | Non | Appliquée |
| `0004_reffiliere_code_dossier.py` | Ajout de `RefFiliere.code_dossier` (F01…F08) | Non (nullable/blank) | Appliquée |
| `0005_alter_refmoduleofficiel_filiere_code_and_more.py` | Ajustement des `help_text` de `filiere_code` et `semestre` pour documenter la réalité des valeurs (EM/APA… ; S1-S3, M1/M2) | Non (métadonnée seule) | Appliquée |

## 7.2 Migrations `formations`

| Fichier | Contenu | Destructive ? | État |
|---|---|---|---|
| `0099_refformation_filiere_refvague_categorie_and_more.py` | FK `RefFormation.filiere`, `RefVague.categorie` | Non | Appliquée |
| `0100_refbatiment_fiabilite_refbatiment_source_document_and_more.py` | `source_document` + `fiabilite` sur `RefSite`, `RefBatiment`, `RefSalle` | Non | Appliquée |

## 7.3 Vérifications

| Contrôle | Résultat |
|---|---|
| `manage.py makemigrations --check --dry-run` | Aucune migration en attente (après `0005`) |
| `manage.py check` | *System check identified no issues (0 silenced)* |
| `manage.py migrate` sur base vierge (tests Django) | Toutes les migrations rejouées sans erreur dans les 40 tests de `referentiels` |
| Suppression de table | Aucune |
| Réinitialisation de base | Aucune |

## 7.4 Ordre d'application

```
formations.0098  →  referentiels.0002  →  0003  →  0004  →  0005
                ↘  formations.0099  →  formations.0100
```

`referentiels.0002` déclare comme dépendances `formations.0098` et `scolarite.0018` (les FK `annee_academique` sont posées dès la création des modèles) ; `formations.0099` dépend de `referentiels.0002` puisqu'elle référence `RefFiliere`. L'ordre est résolu par Django à partir des dépendances déclarées — vérifié par l'application réelle.
