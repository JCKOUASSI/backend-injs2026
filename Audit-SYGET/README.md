# Audit technique — SYGET / INJS-LMD

**Dépôt :** `JCKOUASSI/backend-injs2026` · **Branche auditée :** `arena/c9ce7261-backend-injs2026` (commit `8245d9c`)
**Date :** 23 novembre 2026 · **Type :** audit technique statique + mesures d'exécution locales
**Périmètre :** backend Django (23 applications), frontend React/Vite, application mobile Flutter, CI/CD et déploiement

---

## 1. Verdict en une page

Le socle est **solide sur le fond** : modèle de permissions centralisé et appliqué, journalisation d'audit métier, pipeline de déploiement très garde-foué, couverture de tests inhabituellement élevée pour un projet de cette taille (3 149 tests backend, 2 258 tests frontend). Ce n'est pas un projet « à reconstruire ».

En revanche, **la chaîne de qualité ne protège plus rien** : l'intégration continue est **rouge depuis le 18 novembre 2026**, y compris sur `main`. L'étape fautive est toujours la même — « Hygiène du dépôt » — mais le fichier incriminé a changé : d'abord un CSV de travail versionné dans `livrables/`, aujourd'hui un fichier d'environnement réinjecté à chaque build mobile par un workflow qui force l'ajout de 42 Mo d'artefacts (`git add -f .ci`). Autrement dit : les garde-fous existent, mais ils sont débranchés de fait, et le prochain défaut de modèle ou de sécurité passera sans alerte.

Second point saillant, indépendant de la CI : le gateway de production sert `/media/` **sans authentification**, alors que la configuration du backend affirme le contraire. Les relevés de notes, pièces justificatives et documents RH sont donc accessibles à qui connaît l'URL — c'est-à-dire à peu près personne au hasard, mais à toute personne à qui un lien a été transmis, et à tout moteur d'indexation si le répertoire est listé. La correction tient en quelques lignes de configuration.

| Axe | Note | Lecture |
|---|---|---|
| Architecture & maintenabilité | **3 / 5** | monolithe modulaire cohérent, mais quelques fichiers « cathédrale » (5 400 lignes) |
| Sécurité applicative | **3 / 5** | permissions par défaut saines, mais des médias exposés et des jetons trop durables |
| Qualité & tests | **4 / 5** | volumes de tests élevés, absence de mesure de couverture, suite lente |
| Performance | **3 / 5** | 636 `select_related`/`prefetch_related` (bon signe), mais bundle initial de 1,67 Mo |
| CI/CD & exploitation | **1,5 / 5** | pipeline bien conçu, **actuellement cassé**, artefacts versionnés |
| Documentation & gouvernance | **3,5 / 5** | documentation abondante et exigeante, mais dispersée (72 fichiers Markdown) |

**Note globale : 3 / 5 — bon socle, discipline d'exploitation à rétablir d'urgence.**

---

## 2. Les constats majeurs

| # | Constat | Gravité | Effort | Réf. |
|---|---|---|---|---|
| SYG-01 | CI rouge depuis le 18/11/2026 (étape « Hygiène du dépôt »), y compris sur `main` ; fichier fautif actuel : `.ci/.../app.env` | **Bloquant** | S | `06` |
| SYG-02 | 42 Mo d'artefacts de build versionnés via `git add -f`, dont un `app.env` | **Élevé** | S | `06` |
| SYG-03 | Le gateway sert `/media/` **sans authentification**, alors que la configuration affirme le contraire : relevés, pièces RH et justificatifs accessibles par URL | **Élevé** | S | `03` |
| SYG-04 | Jeton accepté en paramètre d'URL (`?access_token=`) dans tous les environnements, sans `Referrer-Policy` | **Élevé** | S | `03` |
| SYG-05 | Access token de 12 h en `localStorage`, sans CSP ; déconnexion sans révocation serveur | **Moyen à élevé** | M | `03` |
| SYG-06 | Pas de limitation de débit globale : seules la connexion, le scan et les données hors ligne sont limitées | **Moyen** | S | `03` |
| SYG-07 | 3 vulnérabilités modérées sur `react-router` (chaîne d'exécution du front) | **Moyen** | S | `03` |
| SYG-08 | Bundle initial de 1,67 Mo (398 Ko gzip) servi d'un bloc, sans découpage | **Moyen** | M | `05` |
| SYG-09 | Aucune mesure de couverture ; suite longue (686 tests ≈ 116 s pour 2 apps) | **Moyen** | M | `04` |
| SYG-10 | Fichiers monolithiques : `Statistiques.jsx` 5 499 lignes, `formations/api_views.py` 5 417 lignes | **Moyen** | L | `02` |
| SYG-11 | Flutter : 3 fichiers de test pour 8 116 lignes, alors que le scan QR est un point d'entrée | **Moyen** | M | `04` |
| SYG-12 | Documentation dispersée : 13 rapports à la racine + 59 fichiers dans `docs/`, sans index unique | **Faible** | S | `02` |

Détail complet et plan d'action : voir `07-plan-action-priorise.md`.

---

## 3. Ce qui est déjà bien fait (à ne pas casser)

1. **Permissions par défaut fermées.** DRF est configuré avec `IsAuthenticated` par défaut (`config/settings.py:368`). Le balayage des 598 vues (`@api_view`, `APIView`, `ViewSet`) ne relève **aucune** `@api_view` sans décorateur de permission ; les 9 points d'entrée publics (connexion, rafraîchissement, santé, scan public, vérification de diplôme) sont justifiés.
2. **Traçabilité métier.** Un modèle d'audit immuable (`core/models.py:62`, avec `JournalImmuableError`) et quatre journaux métier distincts (`presences.AuditLog`, `referentiels.ReferentielJournal`, `scolarite.JournalScolarite`, `scolarite.MaquetteJournal`), journalisation structurée console en développement et fichier rotatif en production.
3. **Défense contre l'injection de formules** dans les exports CSV/Excel et **imports transactionnels** en deux temps (analyse sans écriture, puis application en une transaction), désormais mutualisés pour maquettes, référentiels et UE/ECUE.
4. **Déploiement prudent** : images tirées par digest, double opt-in pour l'automatique, garde-fou statique interdisant `down -v`, `DROP DATABASE`, `flush`, `prune` (`deploy/production/deploy.sh`), instantanés avant/après.
5. **Contrat d'API versionné** (`docs/api/contract.snapshot.json`) vérifié par 11 tests : une suppression de route casse la CI.
6. **Hygiène du code Python** : aucun `eval` exécutable, aucun `exec`, `os.system`, `shell=True`, SQL brut ni `mark_safe` ; le seul `eval` est un `ast.literal_eval` dans un script d'outillage.

---

## 4. Plan d'action en trois temps

**Immédiat (cette semaine)**
- Protéger `/media/` : supprimer l'`alias` public du gateway et servir les fichiers via la vue authentifiée, ou signer les URL. C'est une correction de configuration de quelques lignes.
- Retirer du suivi `.ci/mobile-web/assets/assets/app.env`, compléter `.gitignore`, corriger le workflow mobile pour exclure le fichier — **CI verte**.
- Vérifier que la branche auditée passe la CI avant toute fusion sur `main`.

**Sprint suivant (30 jours)**
- Conditionner l'authentification par `?access_token=` à l'aperçu, ajouter `Referrer-Policy` ; réduire la durée de vie de l'access token à 30 min et activer la révocation (`token_blacklist`).
- Activer un throttling global et des quotas sur les exports/imports.
- Passer `react-router-dom` en 7.18.x (l'avis modéré couvre toutes les 6.x) et activer `npm audit` en CI.
- Mesurer la couverture backend (seuil indicatif 70 %) et frontend, et suivre la tendance.

**Trimestre**
- Passer en chargement paresseux les 80 pages encore importées en dur, puis découper les fichiers au-delà de 2 000 lignes (4 backend, 1 front).
- Étoffer les tests Flutter du parcours scan, au minimum un test d'intégration bout-en-bout.
- Fusionner les rapports d'audit épars dans une documentation indexée.

---

## 5. Contenu de ce dossier

| Fichier | Contenu |
|---|---|
| `01-perimetre-et-methode.md` | périmètre, sources, commandes, limites de l'exercice |
| `02-architecture.md` | structure, volumétrie, dette de conception, documentation |
| `03-securite.md` | authentification, autorisations, secrets, dépendances, durcissement |
| `04-qualite-tests.md` | inventaire des tests, temps d'exécution, couverture, angles morts |
| `05-performance-frontend-backend.md` | bundle, requêtes, pagination, exports |
| `06-ci-cd-exploitation.md` | CI, workflows, déploiement, sauvegardes, incident en cours |
| `07-plan-action-priorise.md` | matrice gravité × effort, lots, critères de sortie |
| `annexes/preuves-et-commandes.md` | sorties brutes et commandes reproductibles |

---

*Audit réalisé sans accès à la production ni aux journaux d'exécution distants ; toutes les mesures sont reproductibles localement et consignées en annexe. Les constats de sécurité portent sur le code et la configuration versionnés, pas sur l'état du serveur.*
