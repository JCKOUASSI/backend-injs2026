# Livrable 10 — Bilan frontend du module Référentiels

## 10.1 Ce qui existait

| Écran | État avant la mission |
|---|---|
| `pages/Referentiels.jsx` (~1 000 lignes) | Un écran unique à onglets (Formations, Modules, Catégories, Grades, Vagues, Sites, Bâtiments, Salles, Types de secrétariat) mêlant référentiels institutionnels, offre de formation, lieux et nomenclatures |
| `pages/EcranGenerique.jsx` + `config/ecrans.js` | Écrans de liste pilotés par configuration (`ref_formations`, `ref_filieres`, `ref_niveaux`, `ref_semestres`, `ref_ue_ecue`, `ref_annees`, `ref_etablissements`, `ref_types_cours`) |
| Menu `menu/arborescence.js` | Entrées historiques sous « Référentiels » (9 sous-entrées) |

Constat : aucun de ces écrans ne disait **quelle** donnée officielle était
absente, ni d'où venait une valeur. Rien ne distinguait une valeur attestée par
un document d'une valeur modélisée ou laissée « à renseigner ».

## 10.2 Ce qui a été construit

### Tableau de bord (`pages/referentiels/TableauDeBordReferentiels.jsx`)

- **Indicateurs** : 26 référentiels, 547 valeurs référencées, 20 valeurs à
  renseigner, 96 % de traçabilité — tous calculés par l'API, jamais saisis.
- **Recherche** plein texte sur le catalogue (libellé, description, source).
- **Filtres par catégorie** (7), rendus depuis le registre backend.
- **Cartes de référentiel** : description, volumétrie, taux de complétude,
  provenance suivie ou non, lien d'action contextuel :
  - référentiel éditable → « Gérer » vers `/referentiels/gestion/{slug}` ;
  - référentiel consultable ailleurs → « Consulter » vers l'écran réel ;
  - référentiel sans écran → mention « Sans écran dédié », **jamais** un lien
    mort ;
  - avertissement documentaire affiché tel quel quand la source en porte un
    (volumes horaires = proposition).

### Écran de gestion générique (`pages/referentiels/ReferentielGenerique.jsx`)

Un seul écran sert les 14 référentiels éditables, quel que soit leur modèle :

| Fonction | Comportement |
|---|---|
| Lecture | Lignes chargées depuis la route API déclarée par le registre |
| Recherche | Code, libellé, description, libellés des sélecteurs |
| Filtre d'état | Actifs / inactifs / archivés / tous (masqué en lecture seule) |
| Création | Modale, code obligatoire, fiabilité et source documentaire |
| Modification | Code affiché en lecture seule (immuable côté serveur) |
| Activation | Bascule `actif` avec confirmation implicite par le bouton |
| Archivage | Confirmation explicite (modale dédiée), réversible |
| Réactivation | Remet la valeur en service et la rend de nouveau sélectionnable |
| Sélecteurs dépendants | Mention filtrée par école, etc. (`DEPENDANCES`) |
| Lecture seule | Bandeau de provenance, actions d'écriture absentes, pas de bouton « Ajouter » |
| Retour utilisateur | Toast de succès, erreurs de champ rendues telles que renvoyées par l'API |
| Rechargement | Silencieux après écriture (pastille « Actualisation… »), le tableau ne disparaît pas |

### Habillage (`styles/referentiels.css`)

Styles `.ref-*` strictement additifs, appuyés sur le socle `.cand-*` existant
(cartes, pastilles, tableaux, champs). Aucun framework ajouté, aucune classe
existante modifiée.

## 10.3 Routes

| Route | Écran |
|---|---|
| `/referentiels` | Tableau de bord (nouveau) |
| `/referentiels/edition` | Éditeur historique (conservé : il reste la seule saisie des lieux et catégories) |
| `/referentiels/gestion/:slug` | Gestion générique d'un référentiel du registre |

## 10.4 Ce qui n'a pas été fait, et pourquoi

| Élément | Décision |
|---|---|
| Suppression de `Referentiels.jsx` | **Non** : l'écran reste la seule saisie de certaines tables (catégories, grades, vagues, sites) ; sa suppression aurait ouvert un trou fonctionnel. Il perd son statut de point d'entrée. |
| Réécriture de `EcranGenerique` | **Non** : les écrans `ref_*` restent valides pour les données hébergées par d'autres apps ; le tableau de bord y renvoie. |
| Édition inline | **Non** : toute écriture passe par la modale, pour garder une seule validation (côté serveur) et un seul journal. |
| Nouveau composant de tableau | **Non** : réutilisation des classes `.cand-table`, pour ne pas créer un second langage visuel. |

## 10.5 Contrôles

| Contrôle | Résultat |
|---|---|
| `npx vitest run` | 115 fichiers, **2 073 tests**, 0 échec |
| `npx eslint src` | 0 problème |
| `npx vite build` | ✓ built (avertissement de taille de chunk, antérieur) |
| Erreurs console pendant la recette | 0 |
| Captures bureau 1440 × 960 | 8 + 3 de recette |
| Captures en émulation mobile 390 × 844 | 8 — **émulation**, pas un appareil réel |
