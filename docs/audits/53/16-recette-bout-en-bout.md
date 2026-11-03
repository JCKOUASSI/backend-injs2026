# Livrable 16 — Recette de bout en bout du module Référentiels

Cette recette ne se contente pas de photographier des écrans : elle **agit** dans
l'interface React réelle, reliée à l'API Django réelle et à la base de
l'aperçu, puis vérifie chaque effet à l'écran et dans le corps des réponses.

Script : `frontend/scripts/recette-referentiels.cjs` (Node + `puppeteer-core`,
Chromium fourni par `@sparticuz/chromium`).

## 16.1 Environnement d'exécution

| Élément | Valeur |
|---|---|
| Frontend | build de production servi par `vite preview` sur `http://127.0.0.1:3100` |
| API | `manage.py runserver 0.0.0.0:8000` (`USE_SQLITE=1`, base de l'aperçu) |
| Compte | `admin` / rôle `ADMIN` (super-utilisateur réel) |
| Navigateur | Chromium headless, fenêtre 1440 × 960, `deviceScaleFactor = 1` |
| Référentiel support | `types-evaluation` (route historique du routeur : contrat le plus contraignant) |
| Code et libellé de recette | horodatés (`RECETTE53_HHMMSS` / `Recette de bout en bout HHMMSS`) : la recette est rejouable, l'anti-doublon du module refusant — à raison — deux valeurs homonymes |

Commande :

```bash
cd frontend
LD_LIBRARY_PATH=/tmp/chlibs node scripts/recette-referentiels.cjs
# BASE=… SORTIE=… CODE=… pour rejouer ailleurs
```

## 16.2 Scénario et résultats observés (exécution du 2026-11-01)

| Étape | Action réelle | Vérification | Résultat |
|---|---|---|---|
| 1 | Connexion par `POST /api/auth/login/`, jeton posé comme le fait l'application | rôle renvoyé | `admin ADMIN` |
| 2 | Ouverture du formulaire « Ajouter », saisie code + libellé + fiabilité + source, enregistrement | la modale ne se referme qu'en cas de succès ; ligne présente dans le tableau | `POST /api/referentiels/types-evaluation/ → 201`, ligne `RECETTE53_005853` visible, badge `Officiel` (capture 09) |
| 3 | Clic sur le crayon, modification du libellé, enregistrement | libellé mis à jour à l'écran | `PATCH …/10/ → 200` (capture 10) |
| 4 | Clic sur l'icône d'archivage, **confirmation** dans la modale dédiée | ligne absente des actifs, présente dans le filtre « Archivés » | `POST …/10/archiver/ → 200`, puis filtre « Archivés » : ligne affichée grisée, actions neutralisées (capture 11) |
| 5 | Clic sur l'icône de réactivation | ligne de nouveau visible dans « Actifs » et `actif = true` dans la réponse | `POST …/10/reactiver/ → 200 {"archive":false,"actif":true}` |
| 6 | Lecture du journal | quatre traces pour la valeur de recette | `CREATION`, `MODIFICATION`, `ARCHIVAGE`, `REACTIVATION` |
| 7 | Ouverture de `modules-officiels` (référentiel importé, non éditable) | aucune action d'écriture proposée | 227 lignes, 0 bouton d'action, pas de bouton « Ajouter », bandeau « Lecture seule » |

Appels API observés pendant la recette : 17, tous en `200`/`201`, **aucune erreur
console**.

## 16.3 Preuves visuelles

| Fichier | Contenu |
|---|---|
| `captures/recette/09-recette-creation.png` | valeur créée, colonne « Fiabilité » à `Officiel`, pastille `1 / 1` |
| `captures/recette/10-recette-modification.png` | libellé modifié dans le tableau |
| `captures/recette/11-recette-archivee.png` | filtre « Archivés », ligne grisée, seule la réactivation reste proposée |
| `captures/recette/14-lecture-seule-modules.png` | 227 modules officiels en lecture seule |
| `captures/recette/15-lecture-seule-volumes.png` | 51 volumes horaires en lecture seule |
| `captures/12-tableau-de-bord-liens.png` | tableau de bord : 26 référentiels, 547 valeurs, 96 % de traçabilité |
| `captures/13-systeme-lmd-sans-ecran.png` | référentiels LMD sans écran dédié : mention explicite, aucun lien mort |

## 16.4 Ce que la recette a révélé — et corrigé

La recette a été jouée jusqu'à ce qu'elle passe intégralement. Trois exécutions
ont été nécessaires ; les échecs n'ont pas été contournés dans le script, ils
ont été corrigés dans l'application :

| Exécution | Symptôme | Cause réelle | Correction |
|---|---|---|---|
| 1 | `#ref-filtre-etat` introuvable après l'archivage | le rechargement remplaçait l'écran par un état de chargement | rechargement silencieux + pastille « Actualisation… » (A-53-12) |
| 1 bis | code de recette refusé à la création | le validateur n'accepte que `A-Z 0-9 _` (pas de tiret) — le script utilisait `RECETTE53-HHMMSS` | horodatage avec `_` ; le refus était légitime, le script était fautif |
| 4 | `PATCH` refusé : « valeur déjà en doublon » | une exécution précédente laissait une valeur de même libellé | libellé horodaté comme le code ; l'anti-doublon était légitime |
| 2 | la ligne ne réapparaissait pas dans « Actifs » après réactivation | `reactiver` ne réactivait pas la valeur (A-53-09) | `RefSocle.reactiver()` + journal `REACTIVATION` (migration `0006`) |
| 3 | colonne « Fiabilité » vide malgré la saisie | `fiabilite`/`source_document` absents du sérialiseur des 8 routes historiques (A-53-10) | contrat unique dans `RefSocleSerializer` |

Détail complet : livrable 13 §13.5.

## 16.5 Limites assumées

| Limite | Précision |
|---|---|
| Un seul navigateur | Chromium headless ; le rendu mobile est couvert par les captures en 390 × 844 du livrable 11, pas par cette recette |
| Pas de test de charge | La recette vérifie un parcours utilisateur, pas les performances |
| Permissions | Le rôle `AUDITEUR` en lecture seule est couvert par les tests Django (`test_auditeur_en_lecture_seule`), pas par cette recette |
| Base de l'aperçu | La valeur `RECETTE53_HHMMSS` reste active dans la base de démonstration ; elle n'existe pas dans un environnement de production |
