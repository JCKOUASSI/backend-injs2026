# 04 — Qualité et tests

## 1. Un effort de test réel

| Indicateur | Mesure |
|---|---|
| Fichiers de test backend | **234** |
| Cas de test backend | **3 149** `def test_` |
| Vues API exposées | 598 vues / 1 254 routes documentées |
| Fichiers de test frontend | **144** |
| Cas de test frontend | **2 258** tests exécutés en 120,5 s (144 fichiers) |
| Tests Flutter | **3 fichiers** pour 8 116 lignes |
| Ratio de tests | ≈ 5 cas par vue backend, ≈ 1 fichier de test pour 2,5 pages front |

Un total de **5 400 cas de test** place SYGET dans le haut du panier des projets de cette taille. La CI exécute d'ailleurs la suite backend **sur PostgreSQL**, et non sur SQLite — c'est le moteur de production, et c'est la seule manière de vérifier les verrous, contraintes et index réellement utilisés. Ce choix mérite d'être salué.

## 2. Ce que les tests protègent bien

- **Contrat d'API** : `docs/api/contract.snapshot.json` est confronté à 11 tests ; toute route supprimée ou renommée casse la CI. C'est une protection rare et précieuse pour un front qui dépend de 1 254 routes.
- **Sécurité de la connexion** : tests dédiés au throttling (dont fail-open et lecture de `X-Forwarded-For`), au verrouillage de compte, au MFA, aux codes d'erreur.
- **Imports et exports** : les scénarios d'import Excel, de neutralisation de formules et de transaction partielle sont couverts — c'est précisément là que les régressions coûtent cher.
- **Front** : les écrans critiques (statistiques, référentiels, maquettes) disposent de suites substantielles, y compris des tests de composants après refactor.

## 3. Faiblesses de la démarche de test

### QUA-01 — Aucune mesure de couverture, ni backend ni en CI · **Moyen**

Il n'existe **ni `.coveragerc`, ni `pyproject.toml`, ni `setup.cfg`, ni `tox.ini`** dans le dépôt, et `coverage` n'est pas dans `requirements.txt`. Le script `test:coverage` existe côté front (`vitest run --coverage`, provider v8, `include: src/**`), mais **la CI ne l'exécute pas**. Aucun seuil n'est imposé nulle part.

Conséquence : avec 3 149 tests, on ne sait pas si l'on couvre 40 % ou 85 % du code. On ne peut donc pas dire *ce qui* n'est pas testé, et la couverture ne peut pas se dégrader visiblement. Le volume de tests masque les angles morts.

**Correctif** : ajouter `coverage` (ou `pytest-cov`) au backend, un `coverage report --fail-under=70`, et publier les deux rapports en artefact de CI. Commencer par mesurer, fixer un seuil au niveau actuel, puis l'augmenter par palier — ne pas viser 90 % d'emblée, cela pousserait à des tests sans valeur. Effort **M**.

### QUA-02 — Suite lente pour un retour rapide · **Moyen**

Sur le sous-ensemble « scolarité + référentiels » (686 tests, 2 ignorés), l'exécution locale prend **116 secondes** sur SQLite. Sur PostgreSQL en CI, la suite complète de 3 149 tests sera nettement plus longue. Sans exécution parallèle (`manage.py test --parallel`) ni découpage par application, la boucle de retour d'un développeur dépasse la minute avant même d'atteindre les tests front (120 s de plus).

Ce n'est pas bloquant — la CI est là pour ça — mais cela explique pourquoi les développeurs contournent la suite complète et pourquoi les régressions sont découvertes tard.

**Correctif** : activer `--parallel` en CI, découper en jobs (applications indépendantes), et fournir une commande « tests rapides » documentée pour la boucle locale. Effort **S**.

### QUA-03 — Analyse statique Python absente · **Moyen**

La CI vérifie `manage.py check`, les migrations et l'hygiène du dépôt, mais **aucun linter Python** (ruff, flake8), aucun formateur, aucun typage. `ruff` et `flake8` ne figurent même pas dans `requirements.txt`. Côté front, ESLint est bien présent et exécuté.

Conséquence : imports morts, variables inutilisées, complexité croissante et incohérences de style ne sont détectés par personne. Sur des fichiers de 5 400 lignes, c'est exactement ce qui accélère la pourriture. À noter en revanche une règle maison intéressante : `check_repo_hygiene` **interdit `print()`** dans le code de runtime Django, et la règle est appliquée en CI.

**Correctif** : `ruff` avec une configuration minimale (`E`, `F`, `I`, `B`), en avertissement d'abord, bloquant ensuite ; `ruff format --check`. Effort **S** à **M** (le premier passage produira beaucoup de bruit).

### QUA-04 — Angle mort mobile : 3 tests pour le parcours critique · **Moyen**

L'application Flutter porte un parcours à forts enjeux : authentification, scan du QR, ouverture de séance, mise en cache hors ligne, synchronisation. Elle est couverte par **3 fichiers de test** pour 8 116 lignes, soit un ratio sans commune mesure avec le reste du projet. Le comportement en cas de perte de réseau, de double scan ou de conflit de synchronisation n'est donc pas protégé.

**Correctif** : au minimum un test d'intégration bout-en-bout du scan et trois tests unitaires sur la file de synchronisation et la déduplication. Effort **M**.

### QUA-05 — Non-déterminisme observé sur les tests de maquettes · **À confirmer**

Lors des premières exécutions ciblées de `scolarite.tests.test_maquettes_admin_api` (34 tests), **4 échecs** ont été observés, puis **1** lors d'un second essai, puis **0** au troisième. Les messages variaient : maquette « LICENCE STAPS – L1 » considérée comme verrouillée alors qu'elle ne devrait pas l'être, code 400 au lieu de 200 sur un import.

Les mêmes tests passent intégralement quand l'application `scolarite` est exécutée en entier (555 tests, 92,5 s, 2 ignorés, OK). Cela suggère une **dépendance à l'état résiduel de la base de test** ou à l'ordre d'exécution, plutôt qu'un défaut fonctionnel.

Pourquoi c'est important : la CI n'a pas atteint l'étape « Tests » depuis le 18 novembre. La première exécution verte de `FIX-01` risque donc de révéler des échecs de ce type. Il faut s'y attendre et **ne pas** les considérer comme un nouvel incident.

**Action** : après `FIX-01`, lancer la suite complète sur PostgreSQL et comparer avec une exécution sur SQLite ; si le non-déterminisme persiste, isoler les fixtures fautives (`setUpTestData` partagé, données créées par une commande de seed). Effort **M**.

### QUA-06 — Tests volumineux plutôt que ciblés · **Faible**

`src/pages/Statistiques.test.jsx` fait **3 269 lignes** pour tester une page de 5 499 lignes. Le ratio est cohérent, mais la maintenance devient coûteuse : un changement d'interface casse des dizaines d'assertions couplées au rendu. Le découpage de la page (voir `02`) mécanisera aussi le découpage des tests.

## 4. Qualité perçue du code

| Signal | Observation |
|---|---|
| `print()` en runtime | interdit et vérifié en CI — bonne discipline |
| `TODO`/`FIXME` | seulement 4 occurrences dans tout le code — signe d'un nettoyage réel |
| Commentaires | nombreux, souvent explicatifs (« risque R6 », « A5 »), utiles |
| Exceptions | gestionnaire d'erreur unifié avec code machine en en-tête — bonne pratique |
| Erreurs silencieuses | quelques `except Exception: pass` dans le front (stockage, refresh) — à surveiller |
| Code mort | `dashboard/views_legacy.py` (1 951 lignes) toujours routé |

## 5. Synthèse de l'axe

| Critère | Évaluation |
|---|---|
| Volume de tests | **très bon** (5 400 cas) |
| Pertinence des scénarios | **bonne** sur le back et le front, **insuffisante** sur le mobile |
| Mesure de la couverture | **absente** — le point le plus préoccupant de cet axe |
| Vitesse de la boucle de retour | **moyenne** |
| Analyse statique | **partielle** (front seulement) |
| Qualité de la CI | **conçue correctement, actuellement hors service** (voir `06`) |

Note de l'axe : **4 / 5** sur l'effort, ramenée à **3,5** compte tenu de l'absence de mesure et de la CI rouge.
