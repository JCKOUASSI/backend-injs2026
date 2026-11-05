# Audit du Hub « Référentiels » — sous-modules en doublon avec le « Tableau de bord »

**Date :** 05/11/2026 · **Périmètre :** Hub « Référentiels » (menu latéral) et ses
écrans satellites · **Méthode :** recoupement des routes (`App.jsx`), de
l'arborescence de navigation (`menu/arborescence.js`), des descripteurs d'écrans
moteur (`menu/ecrans.js`), du registre backend des référentiels
(`backend/referentiels/registre.py`, payload réel de
`GET /api/referentiels/tableau-de-bord/`) et des modèles réellement servis par
chaque API (vérifiés en base de démonstration).

---

## 1. Le contenu de référence : le « Tableau de bord » (`/referentiels`)

Le sous-module **Tableau de bord** expose **27 référentiels** en 7 catégories,
chacun ouvrant un écran de gestion générique (`/referentiels/gestion/:slug`),
sauf 4 entrées en lecture seule qui délèguent à un écran dédié
(Formations → `/formations`, UE/ECUE → `/scolarite/maquettes`,
Modules officiels et Volumes horaires → générique en lecture).

| Catégorie | Entrées du Tableau de bord |
|---|---|
| Institutionnels | Écoles (2), Mentions (2) |
| Offre de formation | Filières (8), Natures de cursus (5), Formations cycles (16), Modules officiels (227), Volumes horaires (51) |
| Système LMD | Niveaux (8), Parcours (16), Semestres (16), Types de formation (4), UE/ECUE (1 062) |
| Pédagogiques | Types d'enseignement (4), Types d'espace sportif (18), Types d'évaluation (20), Types de décision (4) |
| Ressources humaines | Grades enseignants (28) |
| Organisation pédagogique | Sites (1), Bâtiments (16), Salles et espaces (166), Statuts de vague (5), Vagues (4) |
| Administratif & scolarité | Années académiques (8), Modes de paiement (14), Types de document (56), Types de frais (28), Types de notification (47) |

## 2. Les 13 sous-modules du Hub et leur verdict

Le hub compte 13 enfants au menu. **8 sont en doublon** avec le Tableau de bord,
1 est une délégation assumée, 4 ne le sont pas.

| # | Sous-module (chemin) | Contenu réel (API / modèle) | Verdict |
|---|---|---|---|
| 1 | **Tableau de bord** (`/referentiels`) | Catalogue des 26 référentiels (registre socle) | Référence |
| 2 | **Édition des tables** (`/referentiels/edition`) | CRUD « formations » sur 9 onglets : Formations, Modules, Catégories, Grades, Vagues, Sites, Bâtiments, Salles, Types secrétariat | 🔴 **Doublon majeur** |
| 3 | **Années académiques** (`/referentiels/annees`, écran moteur) | `scolarite.AnneeAcademique` (+ clôturer/rouvrir) | 🔴 Doublon strict |
| 4 | **Établissements & sites** (`/referentiels/etablissements`, 3 onglets) | `formations.RefSite / RefBatiment / RefSalle` | 🔴 Doublon strict ×3 |
| 5 | **Formations** (`/referentiels/formations`, écran moteur) | `formations.RefFormation` | 🔴 Doublon |
| 6 | **Types de formation** (`/referentiels/filieres`, écran moteur) | `scolarite.TypeFormation` | 🔴 Doublon strict (+ confusion de nom, voir §4) |
| 7 | **UE / ECUE** (`/referentiels/ue-ecue`, écran moteur) | Maquettes + UE via `/scolarite/maquettes/` | 🟠 Doublon délégué |
| 8 | **Niveaux** (`/referentiels/niveaux`, écran moteur) | `scolarite.Niveau` | 🔴 Doublon strict |
| 9 | **Semestres** (`/referentiels/semestres`, écran moteur) | `scolarite.Semestre` | 🔴 Doublon strict |
| 10 | **Types de cours** (`/referentiels/types-cours`, 6 onglets) | Catégories, Grades, Vagues (`formations.*`), Types d'évaluation, Types de document (`referentiels.*`), Voies d'accès (admissions) | 🔴 Doublons multiples |
| 11 | Paramètres LMD (`/parametres`) | Paramètres applicatifs | ✅ Non-doublon |
| 12 | Fonctionnalités (drapeaux) (`/parametres/flags`) | Feature flags | ✅ Non-doublon |
| 13 | Planche de style (`/referentiels/planche-de-style`) | Documentation du design system | ✅ Non-doublon (mais hors sujet dans ce hub) |
| — | Imports de données Excel (`/import`) | Import de fichiers | ✅ Non-doublon d'écran (recoupe fonctionnelle à surveiller) |

## 3. Détail des doublons, entité par entité

### 3.1 Doublons stricts — même table physique, plusieurs écrans d'édition

Ces écrans éditent **les mêmes lignes** par des APIs différentes, avec des règles
différentes (le socle interdit la suppression physique et suit la fiabilité ;
l'« Édition des tables » autorise un DELETE physique et l'export Excel) :

| Entité (modèle) | Tableau de bord | Autres écrans d'édition |
|---|---|---|
| Sites (`formations.RefSite`) | Gestion générique | Édition des tables · Établissements & sites |
| Bâtiments (`formations.RefBatiment`) | Gestion générique | Édition des tables · Établissements & sites |
| Salles et espaces (`formations.RefSalle`, 166) | Gestion générique | Édition des tables · Établissements & sites |
| Vagues (`formations.RefVague`) | Gestion générique | Édition des tables · Types de cours |
| Formations (`formations.RefFormation`, 16) | Lecture (délègue) | Édition des tables · Formations (écran moteur) |
| Années académiques (`scolarite.AnneeAcademique`) | Gestion générique | Années académiques (écran moteur, + clôture/réouverture) |
| Niveaux (`scolarite.Niveau`) | Gestion générique | Niveaux (écran moteur) |
| Semestres (`scolarite.Semestre`) | Gestion générique | Semestres (écran moteur) |
| Types de formation (`scolarite.TypeFormation`) | Gestion générique | « Types de formation » (écran moteur `ref_filieres`) |
| Types d'évaluation (`referentiels.RefTypeEvaluation`) | Gestion générique | Types de cours (onglet) |
| Types de document (`referentiels.RefTypeDocument`) | Gestion générique | Types de cours (onglet) |

→ **11 entités du Tableau de bord (sur 27) sont éditables depuis 2 ou 3 écrans** (12 avec la délégation UE/ECUE).
Sites, Bâtiments, Salles et Vagues en ont **trois**.

### 3.2 Doublons de concept — deux modèles distincts pour la même notion

Plus insidieux : les écrans ne se contredisent pas sur les mêmes lignes, ils
entretiennent **deux référentiels parallèles divergents** :

| Notion | Modèle du Tableau de bord | Modèle concurrent | État réel des données |
|---|---|---|---|
| Grades (enseignants) | `referentiels.RefGradeEnseignant` — « Grades enseignants », 28 valeurs | `formations.RefGrade` — onglets Grades (Édition des tables, Types de cours), 3 valeurs | **Aucun libellé commun** entre les deux listes |
| Modules | `referentiels.RefModuleOfficiel` — « Modules officiels », 227 valeurs (+ UE/ECUE scolarité, 1 062) | `formations.RefModule` — onglet Modules (Édition des tables) | **0 ligne** : l'onglet Modules de l'Édition des tables est vide alors que le Tableau de bord en affiche 227 |

### 3.3 Doublon délégué

- **UE / ECUE** : le Tableau de bord déclare l'entrée non éditable et renvoie vers
  l'écran Maquettes LMD (`/scolarite/maquettes`) ; le sous-module « UE / ECUE » du
  hub interroge la même API via un écran moteur. Deux écrans, un seul contenu,
  délégation partiellement assumée.

### 3.4 Doublon externe au hub (même famille de contenu)

- **« Référentiels » du hub GET-INJS/EDT** (`/edt/referentiels`) : récapitulatif en
  lecture des filières, formations, maquettes & modules, bâtiments & salles,
  enseignants, groupes & vagues — recoupe en consultation les entrées Filières,
  Formations, Salles/Bâtiments et Vagues du Tableau de bord.

### 3.5 Entrées du Tableau de bord SANS aucun doublon (15)

Écoles · Mentions · Natures de cursus · Filières · Parcours · Statuts de vague ·
Types d'enseignement · Types d'espace sportif · Types de décision ·
Modes de paiement · Types de frais · Types de notification · Volumes horaires ·
Modules officiels (hors doublon de concept §3.2).

## 4. Incohérences associées relevées

1. **Confusion « Filières » / « Types de formation »** : le sous-module libellé
   « Types de formation » porte l'identifiant `ref_filieres` et gère
   `scolarite.TypeFormation` — alors que le Tableau de bord possède une entrée
   distincte « Filières » (`referentiels.RefFiliere`, 8 valeurs officielles).
   Même mot, deux contenus, risque d'édition au mauvais endroit.
2. **Règles d'écriture contradictoires selon l'écran** : suppression physique
   autorisée dans « Édition des tables » (DELETE), interdite par principe dans
   le socle du Tableau de bord (archivage/désactivation) — pour les **mêmes**
   tables (§3.1). Une salle protégée par des séances d'EDT peut donc disparaître
   par un écran et être intouchable par l'autre.
3. **Provenance (fiabilité, source) suivie uniquement par le socle** : les
   éditions faites par les écrans parallèles ne portent pas la même traçabilité.

## 5. Recommandations (par priorité)

1. **Faire du Tableau de bord l'unique porte d'entrée d'édition** pour les
   11 entités du §3.1 : retirer du menu les sous-modules « Édition des tables »,
   « Années académiques », « Établissements & sites », « Formations »,
   « Types de formation », « Niveaux », « Semestres » et les onglets redondants
   de « Types de cours » (ou les transformer en liens profonds vers
   `/referentiels/gestion/:slug`).
2. **Conserver comme exceptions explicites** ce que le générique ne sait pas
   faire : clôture/réouverture d'année (à porter dans l'écran générique ou en
   action dédiée), import/export Excel de l'« Édition des tables ».
3. **Trancher les doublons de concept** : un seul référentiel de grades
   (fusionner `formations.RefGrade` dans `RefGradeEnseignant` ou l'inverse) ;
   supprimer l'onglet Modules vide de l'Édition des tables ou le brancher sur
   `RefModuleOfficiel` en lecture.
4. **Renommer** le sous-module « Types de formation » (`ref_filieres`) pour
   lever la confusion avec l'entrée « Filières » du Tableau de bord.
5. Reclasser « Planche de style » hors du hub métier (documentation du socle).

---

*Annexes — preuves : `frontend/src/menu/arborescence.js` (13 enfants du hub),
`frontend/src/menu/ecrans.js` (`ref_annees`, `ref_etablissements`,
`ref_formations`, `ref_filieres`, `ref_ue_ecue`, `ref_niveaux`, `ref_semestres`,
`ref_types_cours`), `frontend/src/pages/Referentiels.jsx` (9 onglets de
l'Édition des tables, `URL_MAP`), `backend/referentiels/registre.py` (modèle de
chaque entrée), comptages en base : RefGrade=3 / RefGradeEnseignant=28 /
RefModule=0 / RefModuleOfficiel=227.*

---

## 6. Suite donnée — suppression des doublons (05/11/2026, commit à suivre)

Décision du commanditaire : supprimer les sous-modules en doublon dès lors que
le contenu du Tableau de bord n'en est pas perturbé. Fait :

- **Arborescence** : les 9 enfants doublons du hub sont retirés (Édition des
  tables, Années académiques, Établissements & sites, Formations,
  Types de formation, UE / ECUE, Niveaux, Semestres, Types de cours). Le hub
  conserve : Tableau de bord, Paramètres LMD, Fonctionnalités (drapeaux),
  Planche de style, Imports de données (Excel). Leurs routes moteur
  disparaissent avec eux (`routesGeneriques()` dérive de l'arborescence).
- **Écrans moteur** : les 8 descripteurs `ref_*` correspondants sont supprimés
  de `menu/ecrans.js` (les formulaires partagés `FORMULAIRE_*` sont conservés,
  ils servent d'autres écrans).
- **Édition des tables** : route et écran (`pages/Referentiels.jsx`, 747 lignes)
  supprimés avec leurs tests. L'import/export Excel par onglets disparaît avec
  l'écran — les imports du hub (« Imports de données ») et les commandes
  d'import backend sont inchangés.
- **Anciennes URL redirigées** vers l'écran du Tableau de bord correspondant
  (ex. `/referentiels/annees` → `/referentiels/gestion/annees`,
  `/referentiels/ue-ecue` → `/scolarite/maquettes`) : aucun lien existant
  n'aboutit à une page morte.
- **Tableau de bord vérifié intact après coup** : 7 catégories, 27 référentiels,
  aucune donnée ni aucune route de gestion modifiée (backend intact).

Restent ouverts (non traités, à arbitrer) : la fusion des référentiels Grades
(`formations.RefGrade` vs `RefGradeEnseignant`) et l'onglet Modules — disparu
avec l'écran Édition ; le concept `formations.RefModule` (0 ligne) reste en
base sans écran.
