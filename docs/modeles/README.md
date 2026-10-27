# Modèles d'import (P00-02)

Ces fichiers sont les **seuls modèles d'import versionnés** dans le dépôt. Ils ne contiennent
que les en-têtes de colonnes et **une ligne d'exemple fictive et non nominative**.

| Fichier | Destination (`manage.py import_excel …`) | Contenu |
|---|---|---|
| `modele_formations.csv` | `import_formations.xlsx` | catalogues formations / modules / salles / dates |
| `modele_formateurs.csv` | `import_formateurs.xlsx` | formateurs (numéro, identité, coordonnées, spécialité) |
| `modele_participants.csv` | `import_participants.xlsx/.csv` | participants / auditeurs |
| `modele_seances.csv` | `import_seances.xlsx` | séances d'emploi du temps |

## Règles

1. **Aucune donnée réelle ou nominative** (noms, e-mails, téléphones de vraies personnes) ne doit
   être collée dans ces fichiers ni dans Git. Les jeux de données réels restent hors dépôt
   (ils sont ignorés par `.gitignore` : `*.xlsx`, `*.csv`, `*.numbers`, sauf ce dossier).
2. Pour les versions Excel (`.xlsx`), générer les classeurs avec
   `python backend/scripts/generate_import_template.py` (configuré pour écrire dans ce dossier).
3. Les imports métier s'effectuent via la commande
   `python manage.py import_excel <fichier>` ou l'API d'import, qui lisent un fichier fourni à
   l'exécution (jamais un chemin codé en dur vers le dépôt).
4. La fixture synthétique de tests `backend/test_import_formations_seances.xlsx` reste versionnée :
   elle est générée par `backend/scripts/generate_test_import.py`, ne contient aucune donnée
   nominative et est exigée par la suite de tests.

Voir aussi [`../SECURITE_DONNEES.md`](../SECURITE_DONNEES.md) et la commande
`python manage.py check_repo_hygiene`.
