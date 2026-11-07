# DEPLOY-INJS-2026 — Mission 03.1 — Audit initial du VPS

**Projet :** INJS Abidjan — `backend-injs2026`
**Domaine cible :** `injs.badge-qr-code.pro`
**Hôte :** `152.228.233.123` (utilisateur `almalinux`)
**Date :** 06 novembre 2026
**Nature :** audit en **lecture seule** — aucune correction, aucune intervention.

---

## 0. Statut réel de cet audit — à lire avant toute autre section

**Aucune commande n'a pu être exécutée sur le VPS.** L'accès SSH est bloqué au
niveau réseau depuis l'environnement de l'agent, et non par un défaut
d'identifiants.

Preuve (deux tentatives, horodatées du 06/11/2026) :

```
$ timeout 12 bash -c 'cat < /dev/null > /dev/tcp/152.228.233.123/22'
→ TCP/22 : OUVERT                       (le port répond)

$ ssh -o BatchMode=yes -o PreferredAuthentications=none almalinux@152.228.233.123 true
kex_exchange_identification: Connection closed by remote host

$ ssh -o BatchMode=yes almalinux@152.228.233.123 'echo OK'
kex_exchange_identification: read: Connection reset by peer
```

Lecture : le TCP aboutit, mais la négociation SSH est interrompue **avant tout
échange de clés**. C'est un filtrage de sortie, pas un refus d'authentification.
Aucune clé privée ni agent SSH n'est par ailleurs présent dans cet environnement.

### 0.1 Convention de statut appliquée dans tout le document

| Statut | Signification stricte |
|---|---|
| **CONFIRMÉ (dépôt)** | vérifiable dans le dépôt Git, au commit `1db2056` |
| **DÉCLARÉ (H1)** | rapporté par vous lors du diagnostic H1, **jamais revérifié** par mes soins |
| **NON MESURÉ** | aucune donnée disponible ; **aucune valeur estimée n'est présentée comme mesurée** |
| **INDÉTERMINÉ** | les indices disponibles ne permettent pas de conclure |

**Conséquence :** les sections 1 à 7 ne sont pas un relevé, mais un **cadre de
mesure**. Les valeurs manquantes sont obtenues par le kit `m3_1_collecte_lecture_seule.sh`
livré avec ce rapport (voir §10).

---

## 1. Architecture réelle du VPS

**Statut : NON MESURÉ** (système, RAM, disque, charge, ports, pare-feu, services).

Seule la topologie applicative est connue, et uniquement par déclaration :

| Conteneur | Rôle | Image | Statut |
|---|---|---|---|
| `injs-db` | PostgreSQL 15 | — | **DÉCLARÉ (H1)** |
| `injs-be` | backend historique | `ophirdesire/injs-be:channel1-latest-amd64` | **DÉCLARÉ (H1)** |
| `injs-be-candidate` | backend candidat | `jckouassi/injs-be:prod-20261026-fix2` | **DÉCLARÉ (H1)** |
| `injs-fe` | frontend | `jckouassi/injs-fe:prod-20261023` | **DÉCLARÉ (H1)** |
| `npm-app-1` | Nginx Proxy Manager | — | **DÉCLARÉ (H1)** |
| `injs-redis`, `injs-rabbitmq`, `injs-worker`, `injs-cron` | services annexes | — | **DÉCLARÉ (H1)** |

À relever : version exacte d'AlmaLinux, architecture CPU, RAM/swap, partitions,
charge, ports en écoute, état du pare-feu (`firewalld`/`nftables`), services
`systemd` actifs. Le kit couvre ces points en section **A**.

---

## 2. Inventaire des conteneurs

**Statut : NON MESURÉ.**

Non établis : nombre exact de conteneurs (y compris arrêtés), politiques de
redémarrage, états de santé, images réellement présentes et leur âge, réseaux,
volumes, consommation CPU/RAM.

Point d'attention déjà identifié : la **coexistence de deux backends**
(`injs-be` historique et `injs-be-candidate`) est déclarée. Elle n'est pas
anormale en soi (déploiement de validation), mais elle rend **ambigu** le
routage réel : savoir lequel des deux sert `injs.badge-qr-code.pro` est
indispensable avant toute préparation. Voir anomalie **A-04**.

Kit : section **B**.

---

## 3. Inventaire PostgreSQL

**Statut : NON MESURÉ.**

Rien n'est établi sur : version exacte du serveur, ports publiés, volumes et
leur point de montage, bases existantes, rôles et attributs, extensions,
connexions actives, paramètres de persistance (`wal_level`, `archive_mode`),
présence d'une réplication.

### 3.1 La question centrale : `injs_lmd_prod_20261026`

La mission demande de ne pas confondre cette base de référence avec les autres.
**Il faut d'abord établir qu'elle existe.** Deux ambiguïtés doivent être levées
par la collecte, car elles rendent les rapports antérieurs interprétables de
deux façons :

1. `injs-db` est-il le **nom d'un conteneur** ou le **nom d'une base** ? Les deux
   usages apparaissent dans les documents d'audit. Le kit interroge
   `pg_database` et liste les conteneurs séparément : la réponse sera explicite.
2. `injs_lmd_prod_20261026` est-il une base **présente sur le VPS** ou seulement
   le nom d'une **sauvegarde** ? La date `20261026` suggère une capture, pas
   nécessairement une base vivante.

Tant que ces deux points ne sont pas tranchés, **aucune conclusion sur les
données de production n'est possible** — et la mission B1 reste ouverte.

### 3.2 Ce que l'on sait des données présentes

**INDÉTERMINÉ.** L'inventaire H7.19 (`pg_temp_3.h719_inventory`) est **écarté** :
`pg_temp_3` est un schéma de session, jamais exporté par `pg_dump` — H7.19 a
photographié sa propre session, pas la base. La comparaison S3/S4 (H7.21) n'a
jamais pu s'exécuter.

Kit : section **C**, tout en `default_transaction_read_only=on`.

---

## 4. État des sauvegardes

**Statut : DÉCLARÉ (H5), NON EXPERTISÉ.**

Quatre fichiers sont déclarés, aucun n'a été analysé :

| Fichier déclaré | Date | Format | Contenu métier |
|---|---|---|---|
| `/home/almalinux/injs-db-backups/injs_lmd_20261026-133624.dump` | 26/10 | custom | **INDÉTERMINÉ** |
| `/home/almalinux/injs-predeploy-20261026-124700/postgres-all.sql.gz` | 26/10 | texte gzip | **INDÉTERMINÉ** |
| `/home/almalinux/backups/injs-lmd/postgres-20261023-025115.sql` | 23/10 | texte | **INDÉTERMINÉ** |
| `/home/almalinux/backup_injs_production_20261023_170117.sql` | 23/10 | texte | **INDÉTERMINÉ** |

**Aucune conclusion sur la restaurabilité n'est possible.** Un fichier de
plusieurs dizaines de Mo peut ne contenir que du schéma. Seule la mesure
(comptage des `COPY` et des lignes par table) tranche — c'est exactement ce que
fait le kit H5 (`docs/audits/vps/h5_expertise_sauvegardes.sh`, déjà livré et
validé par 35 tests sur artefacts équivalents).

**Aucune restauration n'a été déclenchée, ni même tentée.**

---

## 5. Configuration Nginx et SSL

**Statut : NON MESURÉ** pour le VPS.

Non établis : port(s) publiés par `npm-app-1`, réseaux, liste réelle des proxy
hosts, hôte de destination pour `/` (frontend) et pour `/api/` (backend),
certificat utilisé et sa date d'expiration.

### 5.1 Ce qui est CONFIRMÉ (dépôt) et ne l'est pas du VPS

La configuration `docker/nginx/default.conf` du dépôt présente trois défauts
**réels dans le dépôt**, mais **non déployés à ce jour** :

| Défaut | Preuve (dépôt, commit `1db2056`) |
|---|---|
| `X-Forwarded-Proto` écrasé par `$scheme` | 3 occurrences dans `default.conf` ; NPM termine le TLS → Django ne voit jamais `https` |
| `/admin/` sans restriction d'adresse | bloc `location /admin/` sans `allow`/`deny` |
| `client_max_body_size` absent | défaut nginx = 1 Mo, alors que `TAILLE_MAX_PIECE = 10 Mio` |

Une configuration candidate corrigée existe déjà :
`deploy/production/nginx/injs-lmd.candidate.conf` (mission 02). **Elle n'est pas
appliquée** et ne peut pas l'être sans `nginx -t` sur le VPS.

Kit : section **D**.

---

## 6. État Redis / RabbitMQ

**Statut : NON MESURÉ.**

Non établis : versions, persistance (`appendonly`, `save`), volumes, nombre de
clients, files RabbitMQ et leurs messages en attente, liens réels avec les
applications. Point à trancher : **ces services sont-ils effectivement utilisés**
par le backend déployé, ou présents sans usage ? Une file RabbitMQ vide avec
zéro consommateur changerait la nature de la dépendance.

Kit : section **E**.

---

## 7. Analyse de sécurité

### 7.1 Points vérifiables dans le dépôt — CONFIRMÉ

| Point | Constat | Statut |
|---|---|---|
| Secrets dans le dépôt | `.gitignore` exclut `.env`, `*.sqlite3`, `credentials_mobile.txt` ; `.dockerignore` exclut `.env`, `*.key`, `*.pem`, `*.crt` | **CONFORME** |
| Secrets dans les images | aucun `COPY` de secret ; la clé `build-time-only` ne sert qu'au `collectstatic` | **CONFORME** |
| Paramètres TLS applicatifs | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS posés dès que `DEBUG=False` | **CONFORME** |
| Avertissement `W008` | `SECURE_SSL_REDIRECT=False` assumé : la redirection est au proxy | **CONFORME (documenté)** |

### 7.2 Points non mesurables

Utilisateurs système, appartenance au groupe `docker` (équivalent root de fait),
permissions des répertoires applicatifs, ports publiés sur `0.0.0.0`, secrets
présents dans les environnements de conteneurs, configuration TLS effective.

Kit : section **F** — les variables d'environnement n'y sont listées que **par
nom**, jamais par valeur.

---

## 8. Anomalies et risques

Aucune de ces anomalies n'a été « constatée sur le VPS » : elles portent sur
l'**état de connaissance**. C'est précisément le risque dominant de cette étape.

### A-01 — Identité et contenu de la base de production non établis — **CRITIQUE**

* **Constat :** on ne sait pas si `injs_lmd_prod_20261026` existe comme base, ce
  qu'elle contient, ni si elle porte les données métier réellement exploitées.
* **Preuve :** §3.1 et §3.2 ; inventaire H7.19 écarté (`pg_temp_3` = session) ;
  H7.21 jamais exécuté (SSH bloqué).
* **Risque :** toute préparation qui écrirait dans la mauvaise base, ou qui
  considérerait une base vide comme la production, détruirait la référence.
* **Correction recommandée :** exécuter le kit section C, puis figer une
  empreinte (nombre de tables, lignes par table) **avant** toute autre action.
* **Précautions :** lecture seule ; ne jamais restaurer par-dessus une base
  existante ; ne pas prendre l'ancienneté d'un nom pour une preuve de contenu.

### A-02 — Aucune sauvegarde n'a de restaurabilité démontrée — **CRITIQUE**

* **Constat :** quatre fichiers déclarés, zéro expertise.
* **Preuve :** §4 ; rapport H5, colonne « contenu » = NON EXPERTISÉE.
* **Risque :** absence de plan de retour arrière fiable pendant la bascule.
* **Correction recommandée :** exécuter `h5_expertise_sauvegardes.sh` sur le VPS ;
  restaurer **une seule fois** dans une base jetable, puis détruire cette base.
* **Précautions :** aucune restauration dans une base existante ; vérifier
  l'espace disque **avant** (un dump de 118 Mo peut demander plusieurs Go).

### A-03 — Audit réalisé sans mesure : décisions futures à l'aveugle — **ÉLEVÉ**

* **Constat :** cet audit ne contient aucune mesure VPS.
* **Preuve :** §0.
* **Risque :** valider une préparation sur la base d'un document déclaratif.
* **Correction recommandée :** exécuter le kit depuis un hôte autorisé, joindre le
  journal à la mission 03.2.
* **Précautions :** le journal contient des noms de bases et d'utilisateurs
  internes — à ne pas publier sur un dépôt public sans relecture.

### A-04 — Deux backends en parallèle, routage réel inconnu — **ÉLEVÉ**

* **Constat :** `injs-be` et `injs-be-candidate` coexistent (DÉCLARÉ H1).
* **Preuve :** §1, §2.
* **Risque :** préparer le mauvais conteneur ; deux backends pointant sur deux
  bases différentes produiraient des données divergentes.
* **Correction recommandée :** relever le proxy host effectif et la base visée
  par chaque backend (kit D.3 et H2 §2.9).
* **Précautions :** ne rien arrêter ; le simple arrêt d'un conteneur est une
  modification d'état interdite dans cette mission.

### A-05 — Configuration nginx du dépôt non conforme si déployée telle quelle — **ÉLEVÉ**

* **Constat :** `X-Forwarded-Proto` écrasé, `/admin/` ouvert, corps limité à 1 Mo.
* **Preuve :** §5.1 (dépôt, `docker/nginx/default.conf`).
* **Risque :** cookies `Secure` incohérents, CSRF instable, 413 sur les pièces
  de candidature dès 1 Mo.
* **Correction recommandée :** appliquer la candidate de la mission 02 après
  `nginx -t` et sauvegarde.
* **Précautions :** la candidate **n'a jamais été testée syntaxiquement** (aucun
  binaire nginx dans l'environnement d'audit).

### A-06 — Exposition réseau des ports non mesurée — **ÉLEVÉ**

* **Constat :** on ignore quels ports sont publiés sur `0.0.0.0`.
* **Preuve :** §1, §7.2.
* **Risque :** PostgreSQL, Redis ou RabbitMQ joignables depuis Internet.
* **Correction recommandée :** relever `docker ps` et `ss -tulpn` (kit A.6, F.5),
  puis restreindre au pare-feu.
* **Précautions :** ne pas modifier le pare-feu pendant un audit.

### A-07 — Sauvegardes sans planification vérifiée — **MOYEN**

* **Constat :** existence d'une sauvegarde périodique non établie.
* **Preuve :** §4 ; aucune crontab ni timer relevé.
* **Risque :** reprise à partir d'une capture ancienne en cas d'incident.
* **Correction recommandée :** relever crontab et timers (kit G.2).
* **Précautions :** ne pas ajouter de tâche planifiée sans validation.

### A-08 — Discordance documentaire sur les chiffres RBAC — **FAIBLE**

* **Constat :** le catalogue annonçait « onze rôles sensibles » et un test
  « 1 155 permissions » ; les valeurs réelles sont **22** et **1 157**.
* **Preuve :** corrigé au commit `1db2056` (`catalogue_roles.py`,
  `test_lot4_refus_croises.py`) ; 480 tests `habilitations` OK.
* **Risque :** audits ultérieurs fondés sur des chiffres faux.
* **Correction :** **déjà appliquée** (documentaire uniquement).
* **Précautions :** ne pas en déduire une conformité métier des habilitations.

### A-09 — Éléments conformes — **CONFORME**

`.dockerignore` opérationnels (backend −94,3 %, frontend −97,2 %) ; aucun secret
versionné ; démarrage Docker sans migration implicite (B2, 41 tests) ;
publication d'images verrouillée (`INJS_PUBLISH_ENABLED`) ; CI verte en Python
3.12 (run `42344821705`).

---

## 9. Dépendances entre services

Topologie **déclarée** (aucune vérification possible) :

```
Internet ──HTTPS──► npm-app-1 (TLS)
                        ├── /      → injs-fe
                        └── /api/  → injs-be OU injs-be-candidate  ← À TRANCHER
                                          │
                                          ├── injs-db (PostgreSQL 15) ── volumes
                                          ├── injs-redis              ── volumes ?
                                          └── injs-rabbitmq           ── volumes ?
                        injs-worker, injs-cron → mêmes services
```

Ce qui doit être établi avant toute préparation :

1. quel backend sert réellement le domaine public ;
2. quelle base chaque backend vise (`POSTGRES_DB` de chacun) ;
3. quels volumes contiennent les données, et lesquels sont sauvegardés ;
4. si Redis et RabbitMQ sont réellement consommés ;
5. si `injs-worker`/`injs-cron` écrivent dans la même base que le backend servi.

---

## 10. Recommandations de préparation

**Kit livré :** `docs/deploiement/mission-03/m3_1_collecte_lecture_seule.sh`

* exécutable sur le VPS, POSIX `sh`, sans dépendance ;
* couvre les sections A (système), B (Docker), C (PostgreSQL), D (NPM/SSL),
  E (Redis/RabbitMQ), F (sécurité), G (sauvegardes) ;
* **garde-fous vérifiés mécaniquement** : aucune commande de cycle de vie Docker,
  aucune instruction SQL destructrice, PostgreSQL interrogé en
  `default_transaction_read_only=on`, variables d'environnement listées par nom ;
* validation à blanc effectuée : syntaxe `sh -n` OK, exécution sur une machine
  sans Docker ni PostgreSQL → dégradation propre, code retour 0.

Séquence recommandée :

1. exécuter le kit et joindre le journal à la mission 03.2 ;
2. exécuter le kit H5 sur les quatre sauvegardes (§4) ;
3. lever l'ambiguïté `injs-db` conteneur / base et l'identité de
   `injs_lmd_prod_20261026` ;
4. seulement ensuite, préparer la technique (réseau, volumes, tags d'images).

---

## 11. Décision finale

### NO-GO — PRÉPARATION TECHNIQUE NON ENGAGEABLE EN L'ÉTAT

Motif : les six questions auxquelles la mission doit répondre (ce qui
fonctionne, ce qui est mal configuré, quelles bases existent, quels volumes
portent les données, si les sauvegardes sont exploitables, si nginx achemine
correctement) **restent toutes sans réponse mesurée**. Décider maintenant
reviendrait à préparer un déploiement sur un environnement décrit de mémoire.

### Corrections nécessaires (aucune n'a été effectuée)

1. Exécuter la collecte lecture seule (kit §10) et joindre le journal.
2. Établir l'identité et le contenu de `injs_lmd_prod_20261026`.
3. Démontrer la restaurabilité d'**une** sauvegarde, dans une base jetable.
4. Établir le routage réel NPM → backend, et la base visée par chaque backend.
5. Relever l'exposition réseau (ports `0.0.0.0`) et l'état du pare-feu.
6. Valider `nginx -t` sur la configuration candidate avant toute application.

### Points nécessitant une validation humaine

* Décision sur **quelle base** est la production de référence, après collecte.
* Décision sur le **sort du backend historique** `injs-be` (conservation,
  arrêt, ou coexistence prolongée).
* Politique d'accès à `/admin/` (liste d'IP ou tunnel).
* Autorisation d'exécuter une **restauration de test** dans une base jetable.
* Validation de la **fenêtre de bascule** et du plan de retour arrière.

### Formule de clôture

**AUCUNE COMMANDE EXÉCUTÉE SUR LE VPS — AUCUN CONTENEUR DÉMARRÉ NI ARRÊTÉ —
AUCUNE BASE INTERROGÉE EN ÉCRITURE — AUCUNE RESTAURATION — AUCUN FICHIER
MODIFIÉ — AUCUN SECRET AFFICHÉ.**
