# MISSION 03.2 — Audit technique réel du VPS

**Projet :** INJS Abidjan — `backend-injs2026`
**Commit de référence :** `1db2056` (branche `arena/d90bca00-backend-injs2026`)
**Hôte visé :** `152.228.233.123` (`almalinux`) — `injs.badge-qr-code.pro`
**Date :** 06 novembre 2026
**Nature :** lecture seule. Aucune correction, aucune intervention.

---

## 0. Statut d'exécution — à lire avant tout

**La collecte sur le VPS n'a pas été exécutée.** L'accès SSH reste bloqué au
niveau réseau depuis l'environnement de l'agent :

```
$ ssh -o BatchMode=yes -o PreferredAuthentications=none almalinux@152.228.233.123 true
kex_exchange_identification: Connection closed by remote host
$ ssh -o BatchMode=yes almalinux@152.228.233.123 'echo OK'
kex_exchange_identification: read: Connection reset by peer
```

Le TCP/22 répond, mais la négociation SSH est interrompue **avant l'échange de
clés** : filtrage de sortie, pas refus d'authentification.

**Conséquence assumée :** ce document **n'est pas** le rapport réel de la
mission 03.2. Il contient :

1. les **preuves déjà acquises hors VPS** (§1), qui sont réelles et reproductibles ;
2. le **gabarit probatoire** des LOT 1 à 6 (§2), avec pour chaque point la
   commande exacte et le champ de preuve à coller ;
3. les **anomalies** (§3) et la **décision** (§4).

Les sections « état VPS » restent **NON CONFIRMÉ** tant que le journal de
collecte n'est pas joint. Aucune valeur n'est estimée.

---

## 1. Preuves déjà acquises — CONFIRMÉ

Ces cinq points sont établis par exécution, pas par lecture de fichiers.

### P1 — `migrate` déclenche le provisionnement RBAC, même sans migration à appliquer

Le provisionnement n'est pas une commande : il est accroché au signal
`post_migrate` (`backend/authentication/apps.py`), qui appelle
`ensure_role_groups()`, `sync_all_users_role_groups()` et
`create_superuser_from_env()`.

Expérience sur base **isolée jetable** (`/tmp`, SQLite, jamais une base de
production ni de développement) :

| Étape | Action | Groupes | Utilisateurs |
|---|---|---|---|
| 0 | base vierge, `migrate --plan` | table `auth_group` inexistante | — |
| 1 | `migrate --noinput` | **12** groupes créés | 0 |
| 2 | suppression de `ROLE_ADMIN`, puis `migrate` **sans migration en attente** | **12** (groupe recréé) | 0 |
| 3 | suppression de `ROLE_DIRECTION`, puis `migrate --plan` | **11** (rien recréé) | 0 |

**Lecture :** `migrate` réécrit le RBAC même quand il n'a rien à appliquer ;
`migrate --plan` n'écrit rien.

### P2 — `migrate` peut créer un superutilisateur administrateur

Même dispositif, base isolée neuve :

| Variables fournies | Superusers créés |
|---|---|
| `DJANGO_SUPERUSER_EMAIL` + `DJANGO_SUPERUSER_PASSWORD` | **0** (il manque `USERNAME`, avertissement journalisé) |
| les **trois** variables (`USERNAME`, `EMAIL`, `PASSWORD`) | **1** — `role=ADMIN`, `is_staff=True` |

**Lecture :** lancer `migrate` sur un environnement où ces trois variables sont
présentes **crée un compte administrateur**. Ce n'est pas un risque théorique :
c'est un comportement mesuré.

### P3 — `SKIP_DB_SETUP=true` neutralise l'ensemble

Le harnais `backend/docker_tests/db_setup_policy_test.sh` (41 tests, stubs qui
journalisent les appels) prouve que, dans ce mode, **aucune** commande n'est
lancée : ni `migrate`, ni `collectstatic`, ni création de superutilisateur. Comme
P1 et P2 passent par `post_migrate`, et que `post_migrate` n'est émis que par
`migrate`, **sans `migrate` il n'y a ni RBAC ni superuser**.

Corollaire opérationnel : la réserve « provisionnement RBAC » n'est protégée que
tant qu'aucun `migrate` n'est exécuté. `scripts/migrate_explicit.sh --apply`
**déclenche P1 et P2** — c'est le point de vigilance majeur.

### P4 — Redis n'est qu'un cache, sans Celery

| Constat | Preuve |
|---|---|
| `REDIS_URL` alimente uniquement `CACHES` | `backend/config/settings.py:263-299` |
| Aucune dépendance Celery | `0` occurrence dans `requirements.txt` et dans le code |
| Client `redis==5.2.1` présent | `requirements.txt` |
| Sans `REDIS_URL` : `FileBasedCache` (local au conteneur) | branche `else` de `settings.py:299` |

**Conséquence :** la question à trancher sur le VPS n'est pas « quel mot de passe
Redis » mais « `REDIS_URL` est-il défini sur les conteneurs, et Redis est-il
joignable par eux ». Le LOT 5.5 du kit collecte exactement cela.

### P5 — Correction d'attribution (point B de votre message)

Votre message indique que « le rapport recommande d'ajouter un mot de passe
Redis ». **Ce n'est pas ce que dit le rapport M03.1** : le mot `requirepass`
n'y apparaît nulle part (`grep` : aucune occurrence). La seule recommandation
Redis formulée était de **relever les ports exposés et de restreindre au
pare-feu** (anomalie A-06).

La précaution que vous demandez est néanmoins adoptée comme règle : **aucune
modification de configuration Redis** (mot de passe, bind, persistance) avant
d'avoir relevé clients, `REDIS_URL`, cache Django et dépendances inter-conteneurs.

---

## 2. Gabarit probatoire — LOT 1 à 6

Kit : `docs/audits/vps/M03-2-collecte_lecture_seule.sh`
(validé : `sh -n` OK, garde-fous vérifiés mécaniquement, exécution à blanc
exit 0, six sections produites).

| LOT | Objet | Statut | Preuve attendue |
|---|---|---|---|
| 1 | Système (OS, CPU, RAM, disque, charge, `systemctl --failed`, pare-feu, ports) | **NON CONFIRMÉ** | sections 1.1 à 1.12 du journal |
| 2 | Docker (versions, conteneurs, images, réseaux, volumes, restart, health, ressources) | **NON CONFIRMÉ** | sections 2.1 à 2.9 |
| 3 | PostgreSQL (instances, versions, volumes, bases, rôles, extensions, tailles, tables) | **NON CONFIRMÉ** | sections 3.1 à 3.10 |
| 4 | NPM (conteneur, version, ports, réseaux, proxy hosts, destinations, SSL) | **NON CONFIRMÉ** | sections 4.1 à 4.5 |
| 5 | Redis / RabbitMQ (présence, versions, ports, volumes, persistance, connexions) | **NON CONFIRMÉ** | sections 5.1 à 5.5 |
| 6 | Sauvegardes (emplacement, date, taille, type, base, empreinte, restaurabilité) | **NON CONFIRMÉ** | sections 6.1 à 6.6 |

### 2.1 Champs à renseigner pour `injs_lmd_prod_20261026`

La collecte doit produire, sans ambiguïté :

| Champ | Où le lire |
|---|---|
| Serveur PostgreSQL (version) | 3.2 |
| Conteneur propriétaire | 3.1 + 3.10 |
| Volume physique | 3.10 |
| Propriétaire SQL | 3.6 |
| Extensions | 3.4 |
| Nombre de tables | 3.4 |
| Volume de données (lignes des principales tables) | 3.4 (`n_live_tup`) |
| Présence de schémas de session parasites (`pg_temp_*`) | 3.4 |
| Sauvegardes associées | 6.1 à 6.4 |

**Deux ambiguïtés à lever dans le même relevé :**

1. `injs-db` est-il un **conteneur** ou une **base** ? Les deux usages coexistent
   dans les documents d'audit ; 3.1 et 3.3 les distinguent explicitement.
2. `injs_lmd_prod_20261026` est-il une **base vivante** ou le **nom d'une
   sauvegarde** ? 3.3 tranche : la liste de `pg_database` est exhaustive.

### 2.2 Ce que cette mission ne fera pas

Aucune configuration du futur conteneur applicatif pour pointer sur cette base,
même si elle existe : **la présence d'une base portant ce nom n'autorise ni
connexion applicative ni migration**. C'est écrit ici comme une contrainte, pas
comme une intention.

---

## 3. Anomalies

### ANOM-01 — `migrate` provisionne le RBAC et peut créer un administrateur — **CRITIQUE**

* **Constat :** `post_migrate` exécute `ensure_role_groups()`,
  `sync_all_users_role_groups()` et `create_superuser_from_env()`.
* **Preuve :** P1 (12 groupes recréés à vide) et P2 (1 superuser ADMIN créé).
* **Risque :** un `migrate` en production réécrit les groupes, **modifie
  l'appartenance des comptes existants** (`sync_all_users_role_groups`) et peut
  créer un compte administrateur non désiré.
* **Correction recommandée :** avant tout `migrate` en production, faire
  l'inventaire des comptes et groupes, et exécuter avec
  `DJANGO_SUPERUSER_*` **absent de l'environnement**.
* **Précautions :** ne jamais lancer `migrate` sur la base de référence sans
  sauvegarde vérifiée et inventaire préalable ; `--plan` est sûr (P1, étape 3).

### ANOM-02 — Identité et contenu de la base de référence non établis — **CRITIQUE**

* **Constat :** `injs_lmd_prod_20261026` n'est ni localisée ni caractérisée.
* **Preuve :** §2.1 — aucun relevé VPS ; H7.19 écarté (`pg_temp_3` = session).
* **Risque :** écrire dans la mauvaise base, ou prendre une base vide pour la production.
* **Correction :** collecte LOT 3, puis empreinte figée (tables, lignes).
* **Précautions :** lecture seule ; aucune connexion applicative avant décision.

### ANOM-03 — Sauvegardes non expertisées — **ÉLEVÉ**

* **Constat :** quatre fichiers déclarés, aucune restaurabilité démontrée.
* **Preuve :** rapport H5, colonne contenu = NON EXPERTISÉE ; §6 du kit.
* **Risque :** aucun plan de retour arrière fiable.
* **Correction :** exécuter `h5_expertise_sauvegardes.sh`, puis **une** restauration
  dans une base jetable.
* **Précautions :** jamais par-dessus une base existante ; vérifier l'espace disque.

### ANOM-04 — Deux backends en parallèle, routage inconnu — **ÉLEVÉ**

* **Constat :** `injs-be` et `injs-be-candidate` coexistent (DÉCLARÉ H1).
* **Preuve :** LOT 2.4 + LOT 4.3 à exécuter.
* **Risque :** préparer le mauvais conteneur, ou deux backends sur deux bases.
* **Correction :** relever le proxy host effectif et la base visée par chacun.
* **Précautions :** aucun arrêt de conteneur dans cette phase.

### ANOM-05 — Exposition réseau inconnue — **ÉLEVÉ**

* **Constat :** ports publiés non relevés (PostgreSQL, Redis, RabbitMQ joignables ?).
* **Preuve :** LOT 1.11 et LOT 2.4 à exécuter.
* **Risque :** services de données accessibles depuis Internet.
* **Correction :** relever, puis restreindre au pare-feu **hors audit**.
* **Précautions :** ne pas modifier le pare-feu pendant la collecte.

### ANOM-06 — Configuration nginx du dépôt non conforme si déployée telle quelle — **MOYEN**

* **Constat :** `X-Forwarded-Proto` écrasé, `/admin/` ouvert, `client_max_body_size` à 1 Mo.
* **Preuve :** `docker/nginx/default.conf`, commit `1db2056` ; candidate livrée en M02.
* **Risque :** CSRF/cookies incohérents, 413 dès 1 Mo.
* **Correction :** appliquer la candidate après `nginx -t` et sauvegarde.
* **Précautions :** la candidate n'a jamais été validée syntaxiquement (pas de binaire nginx).

### ANOM-07 — Réserve `SKIP_DB_SETUP` : partiellement levée — **MOYEN**

* **Constat :** la neutralisation est prouvée (P3) **pour le démarrage**, pas pour
  un `migrate` explicite.
* **Preuve :** P1/P2 — les effets de bord passent par `migrate`, quel que soit
  le lanceur.
* **Risque :** croire que `SKIP_DB_SETUP=true` protège encore après un
  `migrate_explicit.sh --apply`.
* **Correction :** documenter et tracer cette limite ; exécuter tout `migrate`
  avec inventaire préalable et `DJANGO_SUPERUSER_*` retiré de l'environnement.
* **Précautions :** ne pas modifier le code de `post_migrate` pendant la phase d'audit.

---

## 4. Décision

| Décision | Statut |
|---|---|
| Clôture de l'audit documentaire M03.1 | **GO** |
| Audit réel du VPS (M03.2) | **GO — mais non exécuté** : bloqué par l'accès SSH |
| Préparation des modifications VPS | **EN ATTENTE** des résultats de collecte |
| Construction des images de livraison | **EN ATTENTE** |
| Connexion à la base de production | **NON AUTORISÉE** |
| Déploiement applicatif | **NON AUTORISÉ** |

### Condition de passage à M03.3

1. Exécuter `M03-2-collecte_lecture_seule.sh` sur le VPS et joindre le journal.
2. Lever les deux ambiguïtés de §2.1 (`injs-db`, `injs_lmd_prod_20261026`).
3. Faire trancher par un humain : quelle base est la référence, quel backend est
   servi, quelle politique pour `/admin/`.
4. Décider du sort de `DJANGO_SUPERUSER_*` dans l'environnement de production
   **avant** tout `migrate` (ANOM-01).

---

## 5. Formule de clôture

**AUCUNE COMMANDE EXÉCUTÉE SUR LE VPS — AUCUN CONTENEUR DÉMARRÉ NI ARRÊTÉ —
AUCUNE ÉCRITURE SQL — AUCUNE MIGRATION — AUCUN PROVISIONNEMENT RBAC — AUCUNE
RESTAURATION — AUCUNE PERMISSION MODIFIÉE — AUCUN SECRET AFFICHÉ.**

Les expériences P1 et P2 ont été menées exclusivement sur des bases SQLite
jetables créées dans `/tmp`, supprimées après usage, sans lien avec une base de
production ou de développement.
