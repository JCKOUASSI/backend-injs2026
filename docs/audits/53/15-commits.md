# Livrable 15 — Commits

Branche : `arena/d40e4a41-backend-injs2026` (jamais réécrite, aucun `--force`, aucun `reset --hard`).

## 15.1 Commits de la mission 53

| Ordre | Hash | Message | Contenu |
|---|---|---|---|
| 1 | `c70d87d` | `feat(referentiels): refonte du module Référentiels pilotée par un registre unique` | Backend complet (registre, modèles, migrations, API, import, contrôle de cohérence, tests), frontend (tableau de bord, CRUD générique, styles), 14 livrables, schéma et 16 captures |
| 2 | `49e303b` | `docs(referentiels): rapport des commits de la mission 53` | Ce livrable |
| 3 | `53e50ba` | `docs(referentiels): référencer le hash du commit de documentation` | Complète le tableau ci-dessus |
| 4 | *(ce commit)* | `fix(referentiels): corriger les défauts révélés par la recette de bout en bout` | A-53-09 (réactivation), A-53-10 (traçabilité non persistée), A-53-11 (liens morts), A-53-12 (rechargement) ; migration `0006` ; livrable 16 ; 7 captures |

**Statistiques du commit principal** : 61 fichiers, 8 356 insertions, 4 suppressions.

## 15.2 Répartition du commit principal

| Domaine | Fichiers |
|---|---:|
| Backend — code (`referentiels`, `formations`) | 9 |
| Backend — migrations | 6 |
| Backend — données sources (`data/*.json`) | 5 |
| Backend — commandes de gestion | 2 |
| Backend — tests | 1 |
| Frontend — écrans, styles, script de capture | 4 |
| Frontend — routes et menu | 3 |
| Documentation (livrables + schéma + README) | 17 |
| Preuves visuelles (PNG) | 16 |

## 15.3 Ce que le commit ne contient pas

| Exclu | Raison |
|---|---|
| `backend/db.sqlite3` | Base de développement locale (déjà ignorée) |
| `backend/staticfiles/` | Artefact de `collectstatic` (ignoré par `.gitignore`) |
| `frontend/node_modules/`, `frontend/dist/` | Artefacts de build (ignorés) |
| Scripts de débogage temporaires | Supprimés avant le commit |
| Secrets | Aucun secret, aucune clé : les commandes utilisent des variables d'environnement |

## 15.4 Ce que le commit de correction contient

| Fichier | Correction |
|---|---|
| `backend/referentiels/models.py` | `RefSocle.reactiver()` symétrique de `archiver()` ; action de journal `REACTIVATION` |
| `backend/referentiels/migrations/0006_reactivation_action.py` | Nouvelle valeur de choix sur `ReferentielJournal.action` |
| `backend/referentiels/views.py` | L'action `reactiver` délègue au modèle et renvoie `actif` |
| `backend/referentiels/serializers.py` | `source_document` et `fiabilite` dans le contrat du socle |
| `backend/referentiels/registre.py` | `route_ui` par défaut `/referentiels/gestion/{slug}` ; `None` quand aucun écran n'existe |
| `backend/referentiels/tests/test_refonte.py` | 4 tests ajoutés (44 au total pour l'app) |
| `frontend/src/pages/referentiels/ReferentielGenerique.jsx` | Rechargement silencieux après écriture |
| `frontend/src/pages/referentiels/TableauDeBordReferentiels.jsx` | Pas de lien vers un écran inexistant |
| `frontend/src/styles/referentiels.css` | Style d'état neutre |
| `frontend/scripts/recette-referentiels.cjs` | Recette de bout en bout rejouable |
| `docs/audits/53/13,14,15,16,README` | Anomalies, fichiers, commits, recette |

## 15.5 Vérification avant poussée

| Contrôle | Résultat |
|---|---|
| `git status` avant commit | 25 entrées (10 modifiés, 15 nouveaux) — toutes intentionnelles |
| Recherche de secrets dans le diff indexé | Aucun (seuls des mots de passe de test, générés) |
| Plus gros fichier ajouté | 1,5 Mo (capture mobile pleine page) |
| `eslint`, `vite build`, suites de tests | Passés avant commit (voir livrable 12) |
| Poussée | `98f6121..c70d87d` acceptée par `origin` |
