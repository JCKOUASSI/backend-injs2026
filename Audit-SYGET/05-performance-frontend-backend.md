# 05 — Performance : frontend, backend, réseau

## 1. Frontend

### 1.1 Mesure de référence

`npm run build` (Vite 7, mode production) : **succès en 4,80 s**, avec un avertissement de taille de chunk.

| Actif | Taille | Gzip |
|---|---|---|
| `assets/index-*.js` | **1 668,66 Ko** | **398,30 Ko** |
| `assets/Statistiques-*.js` | 195,75 Ko | — |
| `assets/DashboardEngineView-*.js` | 56 Ko | — |
| `assets/Maquettes-*.js` | 44 Ko | — |
| autres chunks de page | 20–32 Ko | — |

Le découpage par route **existe déjà** : `App.jsx` utilise `lazy()`/`Suspense` et les pages lourdes (`Statistiques`, `Maquettes`, `Inscriptions`, `Equivalences`…) sont bien des chunks séparés. Ce n'est donc pas un problème de configuration de bundler, mais de **répartition des imports**.

### 1.2 Cause identifiée : 80 pages importées en dur dans le routeur

`frontend/src/App.jsx` contient 91 instructions `import`, dont **80 pages importées de manière statique** (`Login`, `Formations`, `FormationDetail`, `ModuleDetail`, `Participants`, `ReferentielGenerique`, `HabilitationsLayout`…), tandis qu'une partie seulement est passée en `lazy()`. Tout ce qui est importé statiquement atterrit dans `index-*.js` : d'où un bundle initial de 1,67 Mo qui doit être téléchargé, analysé et exécuté **avant** le premier rendu utile, y compris pour un utilisateur qui ne consultera qu'un écran.

À noter : le front n'a que **cinq dépendances d'exécution** (`react`, `react-dom`, `react-router-dom`, `@tanstack/react-query`, `qrcode`, plus `bootstrap-icons`). Le poids vient donc du **code applicatif**, pas de bibliothèques tierces. C'est une bonne nouvelle : la correction est mécanique.

**Correctif** : convertir les 80 imports statiques de pages en `lazy()` (même motif que les pages déjà traitées), garder en statique uniquement le layout, le contexte d'authentification et les composants du premier écran. Objectif mesurable : `index-*.js` **< 500 Ko** brut (≈ 130 Ko gzip). Effort **S à M**, sans changement fonctionnel — mais à faire avec la suite de tests, car un `lazy()` mal placé provoque un écran blanc au chargement.

Second levier : `manualChunks` pour isoler `react`/`react-dom`/`react-query` (cache navigateur stable entre déploiements), aujourd'hui absent de `vite.config.js`.

### 1.3 Cache et compression

- `frontend/nginx.conf` : gzip activé, `Cache-Control: public, immutable` sur les actifs à empreinte, 1 an. **Correct.**
- Le HTML (`index.html`) est servi sans `Cache-Control` explicite : comportement par défaut acceptable, mais un `no-cache` explicite éviterait de servir un `index.html` référençant des actifs supprimés après déploiement.

## 2. Backend

### 2.1 Points favorables

- **636 occurrences** de `select_related` / `prefetch_related` : le soin apporté aux N+1 est visible, ce qui est rare à ce volume (176 modèles).
- Pagination par défaut à **50** lignes, avec plafonds explicites sur les endpoints sensibles (200 pour les candidatures paginées, 500 pour les tableaux historiques).
- Cache configuré avec un repli progressif : Redis si `REDIS_URL`, sinon cache fichier, sinon mémoire.

### 2.2 PERF-01 — Aucune compression des réponses API · **Moyen**

`django.middleware.gzip.GZipMiddleware` n'est pas dans `MIDDLEWARE`, et le gateway (`docker/nginx/default.conf`) ne définit **aucun `gzip`**. Seul le conteneur front compresse. Résultat : les réponses JSON de l'API — y compris des pages de 200 à 500 lignes, très redondantes et donc très compressibles — voyagent en clair. Sur une liaison mobile 3G (cas réel : les enseignants utilisent l'application depuis l'établissement ou en mobilité), cela peut doubler ou tripler le temps de chargement d'un écran.

**Correctif** : activer `gzip on` avec `gzip_types application/json` au niveau du gateway, ou ajouter `GZipMiddleware` en tête de pile Django pour les réponses dynamiques. Effort **S**, gain immédiat.

### 2.3 PERF-02 — Cache de limitation de débit sur disque en production · **Faible à moyen**

Le compose de production ne déclare ni service Redis ni variable `REDIS_URL` : le cache retombe sur `FileBasedCache` (`settings.py:298-305`). Or c'est ce cache qui porte les compteurs de limitation de débit. Avec `gunicorn --workers auto` (plusieurs processus), chaque worker lit et écrit des fichiers de compteur : I/O disque sur le chemin de chaque requête limitée, et incréments non atomiques entre processus (les seuils peuvent être dépassés). La limitation de débit reste fonctionnelle mais approximative et coûteuse.

**Correctif** : ajouter un service Redis au compose (déjà supporté par le code, aucun changement applicatif) ou, à défaut, documenter cette limite dans le runbook. Effort **S**.

### 2.4 PERF-03 — Exports synchrones dans la requête HTTP · **Moyen**

Les exports (`exports/views.py`, `formations/api_views.py`) génèrent le fichier **pendant** la requête. Sur un export de masse (toutes les notes d'un semestre, tous les étudiants d'un département), la réponse peut dépasser le `--timeout 120` de Gunicorn, ce qui produit une erreur 502 côté gateway et un worker occupé. Combiné à l'absence de quota sur ces routes (SEC-05), c'est le scénario le plus probable d'indisponibilité partielle en période de délibérations.

**Correctif** : mesurer d'abord (journaliser la durée des exports les plus lourds), puis soit plafonner explicitement la taille, soit basculer les exports massifs en tâche asynchrone avec téléchargement différé. Effort **M à L** — à ne lancer qu'après mesure, pour ne pas complexifier sans preuve.

## 3. Base de données

- 176 modèles, 312 migrations : le schéma a beaucoup évolué, ce qui est normal pour un projet de cette maturité.
- Aucune migration manquante (`makemigrations --check` : « No changes detected »), donc pas de dérive entre le code et la base.
- Les migrations sont **appliquées explicitement par `deploy.sh` après revue** (`SKIP_DB_SETUP=true` par défaut), et non automatiquement au démarrage : bonne pratique pour éviter une migration surprise en production.
- Index : non audités en détail faute d'accès à la base de production ; les requêtes agrégées de `statistiques` et les filtres de `presences` sont les candidats à vérifier en premier (`EXPLAIN ANALYZE` sur les tableaux de bord les plus consultés).

## 4. Synthèse de l'axe

| Critère | Évaluation |
|---|---|
| Taille du bundle initial | **insuffisante** — 1,67 Mo, cause identifiée et correction simple |
| Découpage du code | **partiel** — 80 pages encore statiques |
| Cache statique | **bon** |
| Compression réseau | **absente côté API** |
| Requêtes ORM | **bonnes** — 636 `select_related`/`prefetch_related` |
| Chargement lourd | **risque identifié** sur les exports synchrones, non mesuré |

Note de l'axe : **3 / 5**. Les deux premiers correctifs (lazy loading, gzip) sont peu coûteux et très visibles pour les utilisateurs.
