# 02 — Architecture et maintenabilité

## 1. Vue d'ensemble

SYGET est un **monolithe modulaire Django** adossé à trois clients : une interface web React, une application mobile Flutter pour le scan de badges, et un gateway Nginx en frontal. Le découpage est *fonctionnel* (une application Django par domaine métier), pas technique : chaque application porte ses modèles, sa logique, ses vues API et ses exports.

```
                        ┌──────────────────────────────┐
   navigateur ─────────▶│ gateway (Nginx)   :443       │
   mobile Flutter ─────▶│  /api/  /admin/  /media/  /  │
                        └──────────┬───────────────────┘
                                   │
                     ┌─────────────┴──────────────┐
                     │ frontend (React/Vite, nginx)│  assets statiques
                     └─────────────┬──────────────┘
                                   │ /api/v1/…
                     ┌─────────────┴──────────────┐
                     │ backend (Django 5.1 / DRF)  │──▶ PostgreSQL 16
                     │  23 applications métier     │──▶ volume media
                     └────────────────────────────┘
```

Le front et le back sont servis par deux conteneurs distincts, réunis par le gateway ; le mobile consomme la même API REST.

## 2. Découpage du backend

**23 applications Django installées**, 176 modèles, 312 migrations, 819 fichiers Python (189 787 lignes hors migrations).

| Domaine | Applications | Rôle |
|---|---|---|
| Référentiel académique | `referentiels`, `formations`, `scolarite`, `edts` | maquettes LMD, UE/ECUE, semestres, emplois du temps |
| Vie de l'étudiant | `admissions`, `equivalences`, `stages`, `graduation`, `finances_etudiantes` | candidatures, admissions, stages, diplômes, frais |
| Ressources humaines | `ressources_humaines`, `habilitations`, `jurys` | agents, enseignants, habilitations, jurys de soutenance |
| Présences & évaluations | `presences`, `evaluations`, `suiviEvaluation` | scan de badges, feuilles de présence, notes, suivi |
| Pilotage | `statistiques`, `dashboard`, `exports` | tableaux de bord, indicateurs, exports CSV/XLSX/PDF |
| Socle transverse | `core`, `authentication`, `parametres`, `administrations`, `patrimoine` | audit, JWT, paramètres, structures, immobilier |

**Point fort** : le découpage suit le vocabulaire métier de l'INJS. Un correctif sur les maquettes ne se disperse pas dans quinze couches techniques.

**Point de vigilance** : chaque application réimplémente ses propres conventions (exports, filtres, sérialiseurs). La mutualisation entamée sur les référentiels (`referentiels/services/`) et les exports (`exports/`) réduit la duplication, mais reste partielle.

**Reliquats** : deux répertoires applicatifs existent sans être installés — `backend/cache/` (vide) et `backend/referentiel_injs/` (modèles et migrations jamais chargés). Ils entretiennent la confusion sur ce qui est réellement actif et alourdissent les recherches. À supprimer ou à documenter.

## 3. Dette structurelle

### 3.1 Fichiers « cathédrale »

Mesure : `wc -l` sur les fichiers suivis par Git.

| Fichier | Lignes | Problème |
|---|---|---|
| `backend/formations/api_views.py` | **5 417** | ~150 vues, mélange lecture/écriture/exports/imports |
| `backend/presences/views.py` | **3 841** | scan, feuilles, justificatifs, statistiques dans un seul module |
| `backend/exports/views.py` | **3 481** | un endpoint par export, logique de mise en forme inline |
| `backend/statistiques/views.py` | **2 121** | agrégations SQL et sérialisation mêlées |
| `frontend/src/pages/Statistiques.jsx` | **5 499** | page unique portant tableaux, filtres, graphiques, exports |
| `frontend/src/pages/ModuleDetail.jsx` | 1 944 | onglets, formulaires et appels API dans un composant |
| `frontend/src/pages/FormationDetail.jsx` | 1 841 | idem |
| `frontend/src/pages/EvaluationsModule.jsx` | 1 831 | idem |
| `frontend/src/menu/arborescence.js` | 1 674 | arborescence de navigation codée en dur |

**Conséquence concrète** : sur un fichier de 5 400 lignes, un `git blame` désigne rarement l'auteur d'une régression, l'analyse statique est lente, et le risque de conflit de fusion croît mécaniquement. Le test `Statistiques.test.jsx` fait à lui seul 3 269 lignes — signe que la page est testée par accumulation plutôt que par composition.

**Recommandation** : découper par **cas d'usage**, pas par type technique. Pour `formations/api_views.py`, viser un module par sous-domaine (`ue`, `ecue`, `maquette`, `import`, `export`) avec un routeur par module ; pour `Statistiques.jsx`, extraire les blocs déjà identifiables (filtres, cartes d'indicateurs, tableaux, export) en composants et placer la récupération de données dans des hooks. Cible réaliste : aucun fichier au-delà de 800 lignes, sans réécriture fonctionnelle.

### 3.2 Code hérité encore branché

`backend/dashboard/views_legacy.py` (1 951 lignes) est explicitement nommé « legacy » mais toujours routé. Deux pyramides coexistent donc pour les tableaux de bord (`dashboard` et `statistiques`), avec des indicateurs probablement recalculés deux fois. À trancher : soit on supprime l'ancien, soit on documente pourquoi il reste.

### 3.3 Duplication de la logique d'export

Le dépôt contient un module `exports/` central **et** des exports dans `formations`, `presences`, `statistiques`, `scolarite`. Les correctifs de sécurité type « neutralisation des formules Excel » doivent donc être appliqués à plusieurs endroits ; un oubli suffit à rouvrir la faille. La centralisation récente dans `exports/` est le bon mouvement — elle doit être achevée.

## 4. Frontend

- **147 routes** déclarées, 365 fichiers, 118 755 lignes ; React 18.2, Vite 7, React Query 5, React Router 6.
- Organisation lisible : `pages/`, `components/generique/`, `services/`, `hooks/`, `menu/`, `contexts/`.
- Un composant générique `EcranRessource.jsx` (1 418 lignes) et un `ReferentielGenerique.jsx` (1 397 lignes) portent l'essentiel de la configuration des écrans CRUD — bonne intention (factorisation), mais la configuration est si riche qu'elle devient elle-même un mini-framework à apprendre.
- **144 fichiers de test, 2 258 tests** : le front est mieux testé que la moyenne des projets de cette taille.

**Risque principal** : la page `Statistiques` et les trois pages de détail concentrent la complexité ; toute évolution y est coûteuse et risquée.

## 5. Application mobile

Flutter, 43 fichiers, 8 116 lignes : authentification, scan QR, mise en cache hors ligne, synchronisation. Le découpage (`screens/`, `services/`, `models/`, `providers/`) est classique et sain.

Deux réserves :
1. **3 fichiers de test** seulement pour un parcours critique (scan → présence → synchronisation) : c'est le point le plus faible de la couverture globale.
2. Le **build web** de l'application est versionné dans `.ci/mobile-web` (42 Mo, dont un `app.env`), ce qui alourdit le dépôt et fait échouer le contrôle d'hygiène en CI (voir `06`).

## 6. Documentation

72 fichiers Markdown : 13 à la racine, 59 dans `docs/` (31 Mo, avec captures d'écran de preuve), plus les rapports de ce dossier. La qualité est réelle — runbook de production en 10 sections, guides de déploiement, rapports de correction détaillés — mais **l'absence d'index unique** rend la documentation moins utile qu'elle ne pourrait l'être : on ne sait pas quel document fait autorité sur un sujet donné, et plusieurs rapports se contredisent sur l'état d'avancement.

**Recommandation** : un `docs/README.md` faisant office de table des matières, une section « documents historiques » pour les rapports périmés, et le déplacement des 13 rapports racine dans `docs/rapports/`.

## 7. Synthèse de l'axe

| Critère | Évaluation |
|---|---|
| Cohérence du découpage | **bonne** — aligné sur le métier, stable |
| Taille des unités de code | **insuffisante** — 4 fichiers backend et 1 page front au-delà de 2 000 lignes |
| Duplication | **moyenne** — exports et filtres encore dispersés |
| Documentation | **riche mais non indexée** |
| Testabilité de la structure | **correcte** — services extraits dans les zones récentes |

Note de l'axe : **3 / 5**. La structure n'est pas un frein majeur ; ce sont quelques fichiers qui concentrent le risque.
