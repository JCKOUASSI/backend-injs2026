# Audit intégral — Backend INJS Abidjan

**Dépôt** : `JCKOUASSI/backend-injs2026`
**Branche auditée** : `arena/d40e4a41-backend-injs2026` (HEAD au démarrage : `66517c8`)
**Date d'exécution** : 27 octobre 2026
**Périmètre** : `backend/` (Django 5.1.4 + DRF 3.15.2), `frontend/src/` (React 18 + Vite 7),
`qr_badge_mobile/` (tests Dart uniquement — SDK Flutter indisponible, voir §9).

> Toutes les affirmations de ce document s'appuient sur une commande réellement
> exécutée dans le dépôt. Les cases non vérifiables dans cet environnement sont
> explicitement marquées **NON EXÉCUTÉ** (§9) — elles ne sont jamais présentées
> comme conformes.

---

## 1. Environnement d'exécution

| Élément | Valeur constatée |
|---|---|
| Python | 3.11.2 |
| Django | 5.1.4 |
| Django REST Framework | 3.15.2 |
| Base de données utilisée | SQLite (`backend/db.sqlite3`) |
| PostgreSQL | **absent** du bac à sable (`psql`/`postgres` introuvables) |
| Docker | **absent** |
| Node / npm | présents, `frontend/node_modules` installé |

Conséquence assumée : **tous** les contrôles de base de données (transactions,
contraintes, requêtes, migrations) ont été exécutés sur SQLite. Les
comportements spécifiquement PostgreSQL (verrous `SELECT … FOR UPDATE`, index
partiels, `JSONB`, contraintes d'exclusion) sont **NON EXÉCUTÉS** et ne sont
donc pas déclarés conformes.

---

## 2. Inventaire technique

### 2.1 Applications installées

`manage.py` → `settings.INSTALLED_APPS` : **33 entrées**
(23 applications projet + 4 paquets tiers + `django.contrib.*`).

Applications projet : `authentication`, `formations`, `presences`, `exports`,
`dashboard`, `statistiques`, `suiviEvaluation`, `evaluations`, `scolarite`,
`admissions`, `parametres`, `referentiels`, `equivalences`, `jurys`,
`graduation`, `finances_etudiantes`, `stages`, `administrations`,
`ressources_humaines`, `patrimoine`, `edts`, `core`, `habilitations`.

**178 classes de modèles** réparties sur ces applications (script d'inventaire
via `django.apps`).

### 2.2 Routes

Script de parcours du `URLconf` (`django.urls.get_resolver()`) :

| Catégorie | Nombre |
|---|---|
| Motifs d'URL totaux | **1 773** |
| Vues DRF (`APIView` et dérivées) | **910** |
| Vues Django classiques (admin, gabarits, exports fichier) | 863 |
| Routes sous `api/` (préfixes `api/` et `api/v1/`) | 909 |

Principaux préfixes d'API : `api/v1` (287), `api/formations` (96),
`api/referentiels` (70), `api/habilitations` (54), `api/scolarite` (50),
`api/edts` (35), `api/timetable` (35), `api/admissions` (29),
`api/administrations` (21), `api/statistiques` (15), `api/auth` (13).

Le doublon de préfixes `api/…` et `api/v1/…` est **volontaire** (compatibilité
des clients existants) : les deux familles pointent vers les mêmes vues.

### 2.3 Dette d'architecture relevée (non corrigée)

* `backend/referentiel_injs/` contient des modèles et une migration
  `0001_initial` mais **n'est pas dans `INSTALLED_APPS`** : application morte,
  doublon de `referentiels`. Aucune donnée n'y est stockée. Suppression à
  décider par l'équipe (hors périmètre d'un correctif de sécurité).
* Les schémas OpenAPI générés par `drf-spectacular` émettent des collisions
  d'`operationId` (ex. `api_v1_formations_modules_retrieve`). Elles dégradent
  la génération de clients mais pas le fonctionnement de l'API.

---

## 3. Contrôles Django exécutés

| Commande | Résultat |
|---|---|
| `manage.py check` | `System check identified no issues (0 silenced).` |
| `manage.py makemigrations --check --dry-run` (avant correctif) | **ÉCHEC** — dérive `formations/0098` |
| `manage.py makemigrations --check --dry-run` (après correctif) | `No changes detected` |
| `manage.py showmigrations` | **255 migrations appliquées, 0 en attente** |
| `manage.py check --deploy` (profil production simulé) | 1 033 avertissements, dont **1 seul de sécurité** (`security.W008`) |

Les 1 032 autres avertissements sont des `drf_spectacular.W002` (vues sans
`serializer_class`) : ils concernent la documentation, pas la sécurité.

`security.W008` (`SECURE_SSL_REDIRECT`) est **volontairement désactivé** et
justifié dans `config/settings.py` (redirection TLS assurée par le frontal).
HSTS, cookies `Secure` et `SECURE_PROXY_SSL_HEADER` sont bien configurés.

---

## 4. Identité INJS — références SYGEP / CPFAE

Recherche exhaustive (`grep -ri "sygep\|cpfae"`, hors `node_modules`, `.venv`,
`.git`) : **70 fichiers** contenaient une occurrence. Ils ont été classés en
trois catégories.

### 4.1 Références opérationnelles supprimées (correctif)

| Fichier | Nature | Correctif appliqué |
|---|---|---|
| `backend/authentication/permissions.py` | Message d'erreur d'API affiché à l'utilisateur (« Chef CPFAE Admin », « CPFAE Admin ») | Remplacé par « Chef INJS Admin », « Administrateur INJS » |
| `backend/authentication/models.py` | Méthode `is_chef_cpfae_admin()` (aucun appelant) | Renommée `is_chef_injs_admin()` |
| `backend/authentication/emails.py` | Commentaire sur un logo `logo-sygepcpfae.png` | Supprimé |
| `backend/config/urls.py` | Commentaire « Web dashboard CPFAE » | Remplacé par « Web dashboard INJS » |
| `backend/formations/tests/test_referentiel_injs_l6.py` | Variable de test `cpfae` | Renommée `intruse_obj` |
| `backend/formations/test_finance_recap.py` | Pied de page d'exemple « CPFAE Bouaké » | Remplacé par « INJS Abidjan » |
| `frontend/src/pages/Statistiques.jsx` | En-tête « SYGEP-CPFAE » + import `PointJournalierCPFAE` | En-tête « INJS-LMD », composant renommé |
| `frontend/src/components/PointJournalierCPFAE.jsx` (+ `.test.jsx`) | Nom de composant hérité de l'ancien référentiel | Renommés `PointJournalierINJS.*`, export `PointJournalierTableauINJS` |
| `qr_badge_mobile/test/session_provider_heartbeat_test.dart` | URL de test `api.sygepcpfae.org` | Remplacée par `api.injs.ci` |
| `qr_badge_mobile/test/user_facing_error_test.dart` | Sonde d'erreur citant `sygepcpfae` | Remplacée par `injs.ci` |

Preuve d'exécution après correctif :

```
$ grep -rn -i "sygep\|cpfae" frontend/src --include=*.jsx --include=*.js | grep -v "\.test\."
(aucun résultat hors commentaires historiques listés en §4.2)
```

### 4.2 Mentions historiques conservées et justifiées

| Emplacement | Justification |
|---|---|
| `backend/authentication/migrations/0008…0024` | Les migrations sont un **journal immuable** : réécrire des `choices` historiques casserait la reproductibilité. Les libellés affichés sont déjà en terminologie INJS (`migrations/0022_migration_roles_injs`). |
| `backend/authentication/models.py` (docstring), `role_groups.py` (commentaire) | Documentent la **rétrocompatibilité** de la chaîne `CPFAE_ADMIN` (rôle historique) et son refus de persistance. |
| `backend/statistiques/point_journalier.py` (`titre` « …_POINT DES PRÉSENCES_CPFAE ») | **Format de rapport officiel** attendu par les destinataires historiques ; le libellé est un intitulé de document, pas une référence système. **À faire trancher par la direction** (voir §8.2). |
| `backend/dashboard/views_legacy.py` | Application Django historique montrant les libellés legacy ; messages déjà annotés « ancien périmètre, hors INJS actuel ». |
| `backend/scripts/generate_test_*.py`, `build_import_from_donnees.py` | Générateurs de **fichiers d'import de démonstration** : la valeur `CPFAE` y est une donnée d'exemple (site d'origine), pas une dépendance d'exécution. |
| `dossier_trvx/*.txt` | Documents de travail historiques. |

Aucune URL, aucun domaine de repli, aucune variable d'environnement, aucun
paramètre applicatif ne dépend de SYGEP-CPFAE : le backend est **exclusivement
INJS Abidjan** en exécution.

---

## 5. Sécurité

### 5.1 Authentification et permissions par défaut

`REST_FRAMEWORK` : `DEFAULT_AUTHENTICATION_CLASSES` = JWT (en-tête
`Authorization` **et** `X-JWT-Access`) + session ; `DEFAULT_PERMISSION_CLASSES`
= `IsAuthenticated`. Une vue qui oublie ses permissions est donc fermée par
défaut.

Analyse statique des 910 vues DRF :

* vues **sans aucune permission** : **2** — `/api/auth/token/refresh/` et
  `/api/v1/auth/token/refresh/` (renouvellement de jeton : `AllowAny` par
  conception, le refresh token est lui-même vérifié) ;
* vues **explicitement sans authentification** : **12** — `login` (×2),
  `token/refresh` (×2), `scan` (×2), `scan/offline-data` (×2),
  `formations/<uuid:token>/offline-data` (×2), `scan/check-status` (×2).
  Chacune est protégée par un throttle dédié et par un jeton opaque.

Vérification des endpoints publics `offline-data` (qui exposent des noms de
participants) : le service refuse un jeton inconnu (`404`), expiré (`400`),
désactivé (`400`) ou rattaché à une séance terminée (`400`)
(`presences/views.py:3089-3125`). Le payload se limite à `numero`, `nom`,
`prenom`, ce qui est le minimum nécessaire au pointage hors ligne.

### 5.2 Contrôle d'accès au niveau objet (IDOR)

Sonde exécutée sur le serveur réel (`:8000`) avec trois comptes distincts
(`p001` auditeur, `p002` auditeur, `superviseur1`) :

| Requête (jeton `p001`, participant `1` = DIALLO) | Cible | Réponse |
|---|---|---|
| `GET /api/participant/2/historique/` | participant `2` (TRAORE) | **403** |
| `GET /api/participant/2/fiche-admin/` | participant `2` | **403** |
| `GET /api/participant/2/notes-fiche/` | participant `2` | **403** |
| `GET /api/scolarite/etudiants/` | liste scolarité | **403** |
| `GET /api/scolarite/etudiants/1/` | dossier | **403** |
| `GET /api/auth/users/` | comptes | **403** |
| `GET /api/statistiques/rapports/` | rapports | **403** |
| `GET /api/me/fiche/` | **son** dossier | 200 |

Le contrôle objet est donc effectif : un auditeur n'accède qu'à ses propres
données, et les endpoints d'administration lui sont fermés. Aucun IDOR n'a été
trouvé sur le périmètre testé.

Analyse statique complémentaire : seules **8** vues exposent
`Model.objects.all()` sans filtrage — toutes des nomenclatures (`RefTypeEvaluation`,
`RefTypeDocument`, `RefGradeEnseignant`, `RefTypeFrais`, `RefModePaiement`,
`RefTypeDecision`, `RefTypeNotification`, `RefTypeEspaceSportif`), c'est-à-dire
des référentiels non nominatifs.

### 5.3 Fichiers téléversés — faille corrigée

**Constat.** Aucun champ fichier du projet n'imposait de limite de taille ni de
liste d'extensions. `deposer_piece()` affectait directement le fichier reçu.
Un exécutable, une page HTML (contenu actif) ou un fichier de plusieurs
centaines de Mio étaient acceptés.

**Correctif.** Nouveau module `backend/core/validators.py` :

* extensions autorisées : `.pdf`, `.jpg`, `.jpeg`, `.png` ;
* taille maximale : 10 Mio (pièce de candidature), 5 Mio (preuve de paiement) ;
* appliqué **au modèle** (`validators=[…]`, donc admin et formulaires) **et
  dans les services** (`admissions/services.deposer_piece`,
  `finances_etudiantes/services.confirmer_paiement`), car les validateurs de
  champ ne s'exécutent pas sur `Model.save()`.

Migrations associées (métadonnées seulement, aucune donnée touchée) :
`admissions/0003_alter_piececandidature_fichier`,
`finances_etudiantes/0002_alter_paiement_preuve`.

**Preuve avant/après** (test `core.tests.test_validators_fichiers`) :

```
avec correctif      : Ran 9 tests — OK
sans le contrôle de service (neutralisé) : FAIL test_le_service_refuse_un_executable
```

Le test de paiement existant qui téléversait `preuve.txt` a été aligné sur
`preuve.pdf` : il encodait l'absence de tout contrôle et non une règle métier.

### 5.4 Déni de service — garde-fou rétabli

`DATA_UPLOAD_MAX_NUMBER_FIELDS` valait **`None`** (protection de Django
désactivée : un POST multipart avec des dizaines de milliers de champs pouvait
saturer un worker). Remplacé par une valeur bornée, configurable par
environnement, `5 000` par défaut — très au-dessus des formulaires métier.

### 5.5 Secrets et configuration

* Aucun `.env` versionné ; seuls des `.env.example` le sont (5 fichiers).
* Recherche de secrets en dur (`SECRET_KEY|API_KEY|PASSWORD|TOKEN = "…"`) :
  **aucun résultat** hors fichiers de test/exemple.
* `DEBUG` : valeur par défaut **False** (`_env_flag('DJANGO_DEBUG', 'DEBUG', default=False)`).
* `SECRET_KEY` : lue depuis l'environnement, aucune valeur de repli en dur.
* `ALLOWED_HOSTS` : résolution explicite, `'*'` filtré, aucun hôte de
  production implicite.
* CORS : `CORS_ALLOW_ALL_ORIGINS = False`, origines en liste blanche.
* Cookies : `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS 1 an avec
  sous-domaines et preload (bloc production).

### 5.6 Limitation de débit

`login` 20/min, `scan` 60/min, `offline-data` 60/min (surchargeables par
variables d'environnement). **Vérifié en exécution** : une rafale de connexions
depuis le même client a renvoyé `HTTP 429`.

---

## 6. Conformité métier LMD / INJS

### 6.1 Référentiel des filières

`backend/formations/referentiel_injs_l6.py` déclare les **8 filières** avec
traçabilité de la source métier (`docs/audits/A-4.5-DOSSIER-VALIDATION-METIER-INJS-LMD-2026-09-27.md` §2) :

| Code | Sigle | Libellé | École | Diplômes attestés |
|---|---|---|---|---|
| F01 | EM | Éducation et Motricité | ENSEPS | Licence, Master |
| F02 | APA | Activités Physiques Adaptées | ENSEPS | Licence, Master |
| F03 | ES | Entraînement Sportif | ENSEPS | Licence, Master |
| F04 | MS | Management du Sport | ENSEPS | Licence, Master |
| F05 | AND | Andragogie | ENSEP | Licence |
| F06 | LOI | Loisir | ENSEP | Licence |
| F07 | ECJP | Entrepreneuriat Jeunesse et Conduite de Projets | ENSEP | Licence |
| F08 | GER | Gérontologie | ENSEP | Licence |

Aucun intitulé n'a été inventé : le module cite sa source et exclut
explicitement le corpus étranger (périmètre `LEGACY`) sans le supprimer.

### 6.2 Structure LMD

`backend/scolarite/pedagogie_validateur.py` fixe les constantes attendues :

```
ECTS_SEMESTRE = 30   ECTS_NIVEAU = 60   ECTS_LICENCE = 180
ECTS_MASTER  = 120   ECTS_CYCLE  = 300
NIVEAUX = {L1…M2} ; SEMESTRES = {S1…S10} ; NIVEAU_PAR_SEMESTRE S1→L1 … S10→M2
```

La commande `init_referentiels_lmd` crée L1→M2 avec les semestres S1→S10 dans
l'ordre attendu (Licence S1–S6, Master S7–S10).

### 6.3 Étapes du parcours — vérifiées par test

Les quatre étapes (admission → inscription administrative → validation →
inscription pédagogique) sont **disjointes**. Le fichier
`backend/scolarite/tests/test_frontieres_metier.py` (9 tests, tous verts)
démontre que :

1. une inscription **validée** ne crée **aucune** ligne pédagogique ;
2. la génération pédagogique est **explicite** et **idempotente** ;
3. la conversion d'admission est **idempotente** (voir §7.1) ;
4. une **radiation** n'est jamais déduite d'une anomalie technique : elle exige
   un appel explicite, un acteur, un motif, et produit une entrée
   `EvenementScolarite` + `JournalScolarite` ;
5. une inscription non validée ne peut pas être radiée.

### 6.4 Emplois du temps

`edts/services.detecter_conflits()` couvre les conflits internes **et**
inter-EDT, réactive/clôture les conflits automatiques et **ne touche jamais**
aux signalements manuels (`type_conflit = MANUEL`). La génération n'écrit que
les EDT demandés : aucune publication implicite.

---

## 7. Défauts corrigés (avec preuve d'exécution)

### 7.1 Conversion d'admission non idempotente — **critique**

**Constat.** `convertir_admission_en_inscription()` ne vérifiait pas si une
inscription existait déjà pour l'admission. Un double clic ou un rejeu réseau
créait :

* avec `valider=True` : une exception de validation (500/409 côté API) ;
* avec `valider=False` : **une seconde inscription `BROUILLON` silencieuse**
  (aucune contrainte d'unicité en base).

**Correctif.** Recherche préalable d'une inscription vivante (hors `ANNULEE` /
`REJETEE`) pour la même admission : elle est retournée telle quelle ; un rejeu
« avec validation » la fait progresser jusqu'à `VALIDEE` sans jamais réactiver
un dossier suspendu.

**Preuve.**

```
avec correctif : Ran 9 tests — OK
garde-fou neutralisé :
  ERROR test_conversion_rejouee_ne_cree_pas_de_seconde_inscription
  FAIL  test_rejeu_sans_validation_ne_cree_pas_de_doublon_silencieux
        AssertionError: 2 != 3      (deux inscriptions créées)
```

### 7.2 Dérive de schéma / migrations

`makemigrations --check` échouait : `formations/0098` manquait (métadonnées
`help_text`/`choices` et index `db_index` sur `refformation.perimetre`).
Migration générée et appliquée : plus aucune migration en attente (255/255).

### 7.3 Requête N+1 sur la liste des comptes — **performance**

`GET /api/auth/users/` exécutait une requête de groupes **par utilisateur**
(21 requêtes pour 20 comptes). Correctif : `select_related('secretariat')` +
`prefetch_related('groups')` sur les deux querysets concernés.

```
avant : 21 requêtes SQL pour 20 comptes
après :  4 requêtes SQL (3 via /api/v1/)
```

Test de non-régression ajouté (`authentication/test_performance_comptes.py`) :
le nombre de requêtes est identique pour 5 et pour 40 comptes.

### 7.4 Preuve de paiement `.txt` dans le scénario de fumée — détectée par le correctif

Le contrôle de fichiers du §5.3 a immédiatement révélé une utilisation
incorrecte préexistante : la commande `smoke_test_injs` (scénario de bout en
bout en 23 étapes) téléversait une preuve de paiement nommée
`preuve-smoke.txt`, donc un format qui n'aurait jamais dû être accepté pour une
pièce justificative. Après bascule sur `preuve-smoke.pdf`, les 5 tests de
`scolarite.tests.test_smoke_command` repassent au vert. Cela confirme que le
contrôle s'applique bien au chemin réel (service) et pas seulement au modèle.

### 7.5 Références d'identité SYGEP/CPFAE

Voir §4.1.

---

## 8. Points ouverts

### 8.1 Non exécuté dans cet environnement (**NON EXÉCUTÉ**)

| Contrôle | Raison |
|---|---|
| Vérification PostgreSQL (verrous, index partiels, contraintes avancées) | Pas de serveur PostgreSQL |
| Migration sur base de production | Interdit sans autorisation explicite |
| Suite de tests Flutter (`qr_badge_mobile`) | SDK Flutter indisponible, `pub.dev` inaccessible |
| Parcours de paiement réel (mobile money, passerelles) | Pas d'accès aux fournisseurs |
| Test de charge / volumétrie réelle | Pas d'outil de charge, base de démonstration vide |

### 8.2 Décisions à faire trancher (non tranchées par l'audit)

1. **Intitulé du rapport « POINT DES PRÉSENCES_CPFAE »** : format historique
   conservé. Faut-il le renommer pour l'INJS ? Cela change un **livrable
   officiel** : décision institutionnelle, non technique.
2. **Périmètre des rôles historiques** : `CPFAE_ADMIN` reste accepté en lecture
   pour la rétrocompatibilité des données ; faut-il le supprimer définitivement
   (migration de données) ?
3. **Application `referentiel_injs`** : code mort à supprimer ou à fusionner
   avec `referentiels` ?
4. **Données de démonstration** : la base du bac à sable ne contient aucun
   `RefFormation` LMD ; aucune conclusion n'est tirée sur le volume ou la
   qualité des données réelles.

### 8.3 Recommandations non bloquantes

* Ajouter une étape `makemigrations --check` en CI (la dérive du §7.2
  n'aurait jamais dû passer).
* Résorber les collisions d'`operationId` OpenAPI (documentation client).
* Supprimer `backend/referentiel_injs/` ou l'enregistrer réellement.

---

## 9. Résultats des suites de tests

| Suite | Commande | Résultat |
|---|---|---|
| Backend | `USE_SQLITE=1 .venv/bin/python manage.py test` | **2 449 tests — 0 échec, 9 ignorés** (voir §9.1) |
| Frontend | `npx vitest run` | **101 fichiers / 1 915 tests — OK** |
| ESLint | `npm run lint` | 0 erreur, 0 avertissement |
| Hygiène dépôt | `check_repo_hygiene` | CONFORME |

Tests ajoutés par cet audit (20) :

* `scolarite/tests/test_frontieres_metier.py` — 10 tests (frontières métier,
  idempotence y compris via l'API, radiation) ;
* `core/tests/test_validators_fichiers.py` — 9 tests (extensions, taille,
  application par les services) ;
* `authentication/test_performance_comptes.py` — 1 test (N+1).

### 9.1 Résultat exact de la suite backend

```
Ran 2449 tests in 698.101s

OK (skipped=9)
```

---

## 10. Conclusion

Le backend est **fonctionnel, correctement cloisonné et conforme au référentiel
INJS-LMD** sur le périmètre vérifiable ici. Trois défauts réels ont été trouvés
**et corrigés** avec preuve d'exécution : idempotence de l'inscription
(doublons silencieux), absence totale de contrôle des fichiers téléversés, et
requête N+1 sur la liste des comptes. La dérive de migrations est résorbée.

Les limites de cet audit sont explicites : aucune vérification PostgreSQL, ni
Flutter, ni charge, ni production.
