# Livrable 10 — Bilan frontend

## 10.1 Écrans livrés

| Écran | Route | Composant | Rôle |
|---|---|---|---|
| Tableau de bord des référentiels | `/referentiels` | `pages/referentiels/TableauDeBordReferentiels.jsx` | Cartographie par catégorie, recherche transverse, filtres par catégorie, KPI de synthèse, cartes de complétude |
| Gestion d'un référentiel | `/referentiels/gestion/:slug` | `pages/referentiels/ReferentielGenerique.jsx` | CRUD complet, recherche, filtres d'état, archivage, formulaire modal, mode lecture seule |
| Édition des tables (hérité) | `/referentiels/edition` | `pages/Referentiels.jsx` (inchangé) | Gestion des tables historiques (catégories, types de secrétariat, vagues, sites, bâtiments, salles) |

Les écrans métier existants (`/referentiels/niveaux`, `/semestres`, `/formations`, `/ue-ecue`, `/annees`, `/etablissements`, `/types-cours`, `/parametres`, `/parametres/flags`, `/referentiels/planche-de-style`, `/import`) sont **conservés à l'identique**.

## 10.2 Tableau de bord

- **En-tête** : nombre de valeurs du catalogue, nombre de référentiels.
- **KPI** : référentiels suivis, valeurs référencées, valeurs à renseigner, taux de traçabilité (calculé serveur, jamais recalculé côté client).
- **Recherche** : filtre instantané sur libellé, description et slug.
- **Puces de catégories** : 7 catégories + « Toutes » ; état actif visible.
- **Cartes** : icône, libellé, description métier, compteur de valeurs, compteur « à renseigner », état de complétude (Complet / Partiel / Vide), action *Gérer* (éditable) ou *Consulter* (historique), badge de provenance.
- **Légende de fiabilité** : Officiel / Modélisé / Cadrage / À renseigner, affichée en pied de page.

## 10.3 Écran de gestion générique

| Fonction | Détail |
|---|---|
| Recherche | Code, libellé, description et libellés des sélecteurs |
| Filtres d'état | Actifs / Inactifs / Archivés / Tous — masqué en lecture seule |
| Tableau | Colonnes déduites du registre (champs métier + sélecteurs + fiabilité), troncature avec infobulle, état archivé grisé |
| Création | Formulaire modal : code (immuable ensuite), libellé, champs métier, sélecteurs, fiabilité, source documentaire, description, état actif |
| Sélecteurs dépendants | `école → mention`, `école → filière` : la mention est filtrée par l'école choisie ; la route de chaque liste vient du registre (`selecteurs_routes`), jamais d'une table de correspondance côté client |
| Modification | Même formulaire, code verrouillé, `PATCH` partiel |
| Activation / désactivation | Bouton bascule dans la ligne, sans confirmation (réversible) |
| Archivage | Confirmation explicite rappelant que **rien n'est supprimé** et que l'action est réversible |
| Réactivation | Bouton dédié sur les lignes archivées |
| Erreurs | Messages champ par champ (libellé/code obligatoires) et message serveur remonté tel quel (doublon, permission) |
| Lecture seule | Bandeau de provenance, badge « Lecture seule », aucune action d'écriture, colonnes déduites des données servies |

## 10.4 Design system respecté

Aucun composant de bibliothèque externe n'a été introduit. L'écran réutilise les classes existantes `.cand-*` (hero, KPI, panneau, tableau, état vide, champs, boutons) et ajoute un fichier dédié `styles/referentiels.css` **uniquement** pour les pièces propres au module (badges de fiabilité, pastilles, cartes, modale, tableau importé). Toutes les classes ajoutées sont préfixées `.ref-`.

## 10.5 Responsive

| Largeur | Vérification |
|---|---|
| Bureau 1440 × 960 | Captures 01 → 08 (voir `captures/`) |
| Tablette / mobile | Règles CSS à 760 px et 560 px (grille en une colonne, filtres pleine largeur, modale en colonne, en-tête sur deux lignes) — **non vérifié par capture** dans cette mission (voir livrable 12, « non exécuté ») |

## 10.6 Vérifications automatisées

| Contrôle | Résultat |
|---|---|
| `eslint src --ext js,jsx` | 0 erreur, 0 avertissement |
| `vite build` | Succès (bundle produit) |
| `vitest run` (suite complète) | **115 fichiers, 2073 tests — 100 % réussis** |
| Captures réelles via Chromium headless | 8 captures, **0 erreur console** |
