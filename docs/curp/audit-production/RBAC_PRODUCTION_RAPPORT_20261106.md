# AUDIT RBAC DE PRODUCTION — INJS Abidjan

**Mission** : RBAC-PROD-01 · **Date** : 6 novembre 2026
**Base cible** : `injs_lmd_prod_20261026`
**Branche** : `arena/4524a57c-backend-injs2026` (tête : `07361cc`)
**Régime** : lecture seule — **aucune initialisation déclenchée**

---

## ⛔ STATUT : MISSION INTERROMPUE EN PHASE 1

> **La base `injs_lmd_prod_20261026` n'est ni identifiable ni joignable depuis
> l'environnement de travail. Conformément à la règle « En cas de doute sur
> l'identité de la base, arrêter la mission », les phases 2 à 5 n'ont PAS été
> exécutées.**

| Compteur de la synthèse finale | Valeur |
|---|---|
| Comptes à examiner (réel production) | **NON MESURABLE** |
| Profils RBAC manquants | **NON MESURABLE** |
| Attributions existantes | **NON MESURABLE** |
| Anomalies RBAC détectées | **0 détectée — AUCUNE mesure n'a pu être faite** (≠ « aucune anomalie ») |
| Anomalies de périmètre | **NON MESURABLE** |
| **Opérations d'écriture effectuées** | **0 — ZÉRO** |

**Aucun chiffre de ce rapport ne provient du bac à sable.** Les mesures du bac à
sable sont reléguées en annexe B, à titre de traçabilité et **explicitement
exclues** des résultats (règle : « ne jamais supposer que les chiffres du bac à
sable correspondent à la production »).

---

## 1. IDENTIFICATION DE LA BASE (Phase 1)

### 1.1 Tableau de vérification

| # | Point exigé | Constat | Verdict |
|---|---|---|---|
| 1 | Serveur PostgreSQL | Aucun binaire (`psql`, `pg_isready`, `pg_dump`, `pg_ctl`, `postgres`, `pg_config`) ; aucun processus PostgreSQL | **ABSENT** |
| 2 | Nom exact de la base | `injs_lmd_prod_20261026` **n'apparaît nulle part** dans le dépôt (hors l'anomalie A7 déjà documentée). Noms réellement configurés : `qr_badge` (défaut `settings.py:245` et CI), `injs_lmd` (`backend/.env.example:28`), `injs` (`deploy/production/.env.example:56`) | **NON CONFIRMÉ** |
| 3 | Version PostgreSQL | Non mesurable (aucun serveur, aucun client)
| 4 | Conteneur utilisé | `docker` et `docker-compose` **absents**. Le compose de production (`deploy/production/compose.yml`) s'exécute **sur le VPS**, hors de portée ici | **INJOIGNABLE** |
| 5 | Identité de connexion | Aucune variable `POSTGRES_*` définie dans l'environnement ; `POSTGRES_HOST` **vide** dans le modèle de production (« valeur à confirmer sur le VPS ») ; aucun `.pgpass` ; `backend/.env` impose `USE_SQLITE=1` | **AUCUN IDENTIFIANT** |
| 6 | Disponibilité effective | Port 5432 **refusé** sur `localhost` et `127.0.0.1` ; résolution DNS impossible pour `postgres`, `db`, `injs-postgres`, `host.docker.internal` | **INACCESSIBLE** |
| 7 | Sortie réseau | Seuls `github.com` et `pypi.org` répondent ; `injs.ci`, `api.injs`, `postgres.example.org`, `10.0.0.5` sont **inaccessibles** (DNS/route refusés) | **BLOQUÉE** |
| 8 | Tunnel SSH | `~/.ssh` **absent**, identité locale `user@e2b.local` | **IMPOSSIBLE** |

### 1.2 Base réellement interrogée par cet environnement

```
ENGINE  : django.db.backends.sqlite3
NAME    : /home/user/backend-injs2026/backend/db.sqlite3
VERSION : SQLite 3.40.1
```

Ce n'est **pas** `injs_lmd_prod_20261026` : c'est la base SQLite de l'aperçu
(bac à sable). Le pilote PostgreSQL n'est d'ailleurs **pas installé**
(`ModuleNotFoundError: No module named 'psycopg'`) : ce dépôt ne peut
structurellement pas ouvrir de connexion PostgreSQL ici.

### 1.3 Autres voies écartées

| Voie | Résultat |
|---|---|
| Sauvegarde / dump de production présent dans l'espace de travail | **Aucun** (pas de `*.sql`, `*.dump`, `*.backup` ; dossier `backups/` vide). Au demeurant, une sauvegarde est **interdite comme substitut** à la production |
| Trace du nom de base dans l'historique Git | Une seule occurrence : le constat d'inaccessibilité (`a4d81e6`) |
| Hôte de production documenté | `POSTGRES_HOST` vide ; aucun hôte joignable cité |

### 1.4 Décision

L'identité de la base **ne peut pas être confirmée** et la base n'est **pas
joignable**. La mission s'arrête ici. Produire des chiffres reviendrait à
fabriquer des données de production, ce qui est exclu.

---

## 2. PHASES 2 À 5 — NON EXÉCUTÉES

| Phase | Objet | État |
|---|---|---|
| 2 | Inventaire des utilisateurs (totaux, actifs, inactifs, superutilisateurs, comptes RBAC existants / manquants) | **NON EXÉCUTÉE** — aucun accès |
| 3 | Inventaire des attributions (actives, suspendues, révoquées, expirées, en attente, double validation, rôles sensibles + MFA) | **NON EXÉCUTÉE** |
| 4 | Contrôle des périmètres (globaux, locaux, cohérence rôle/périmètre, plafonds, obligatoires, indéterminables, élargissements) | **NON EXÉCUTÉE** |
| 5 | Cohérence au catalogue (81 rôles / 22 sensibles / 1 157 permissions), profils orphelins, doublons, liaisons incorrectes, journaux incohérents | **NON EXÉCUTÉE** |

Rappel des règles qui auraient encadré ces phases et qui demeurent opposables :
aucun rôle déduit de `User.role` ; `CORRESPONDANCE_LEGACY` non utilisée pour
proposer des habilitations ; une attribution historique non considérée comme
valide ; aucune divergence corrigée, seulement documentée.

---

## 3. PREUVES BRUTES (extraits textuels)

```
# Ports en écoute (TCP) — aucun 5432
LISTEN 0.0.0.0:8000  (python, pid 46478)     # Django du bac à sable
LISTEN 0.0.0.0:3000  (node,   pid 48081)     # Vite
LISTEN 0.0.0.0:3001  (python3,pid 30632)     # serveur mobile

# Tentatives de connexion PostgreSQL
psycopg            : ModuleNotFoundError No module named 'psycopg'
localhost          : 127.0.0.1 port 5432 injoignable → ConnectionRefusedError
127.0.0.1          : 127.0.0.1 port 5432 injoignable → ConnectionRefusedError
postgres           : résolution DNS impossible (gaierror)
db                 : résolution DNS impossible (gaierror)
injs-postgres      : résolution DNS impossible (gaierror)
host.docker.internal : résolution DNS impossible (gaierror)

# Sortie réseau
github.com 443 accessible      | pypi.org 443 accessible
postgres.example.org 443 inaccessible | 10.0.0.5 443 inaccessible
injs.ci inaccessible           | api.injs inaccessible

# Variables d'environnement PostgreSQL
(aucune)

# settings.py — la base déclarée ici
if _env_flag('USE_SQLITE', default=False): → sqlite3  # branche active : USE_SQLITE=1
else: POSTGRES_DB = os.environ.get('POSTGRES_DB', 'qr_badge')
```

---

## 4. ANOMALIES (issues de la Phase 1)

Chaque anomalie est **documentée, non corrigée**. Détail également dans
[`RBAC_PRODUCTION_ANOMALIES_20261106.csv`](RBAC_PRODUCTION_ANOMALIES_20261106.csv).

| Id | Nature | Gravité | Conséquence métier | Action corrective recommandée | Autorisation nécessaire |
|---|---|---|---|---|---|
| **P1.1** | Aucun serveur PostgreSQL, aucun client (`psql`), aucun conteneur Docker dans l'environnement d'audit | **CRITIQUE** (audit) | Aucune mesure de production possible | Exécuter l'audit **depuis le VPS** (ou depuis un hôte autorisé) | Habilitation d'accès au serveur de production |
| **P1.2** | Nom de base `injs_lmd_prod_20261026` **absent du dépôt** ; noms configurés : `qr_badge` / `injs_lmd` / `injs` | **CRITIQUE** (identité) | Risque d'auditer une base qui n'est pas la production — interdit par la mission | Confirmer le nom exact **sur le serveur** (`psql -c 'SELECT current_database(), version()'`) et le figer dans `POSTGRES_DB` | DSI INJS |
| **P1.3** | Pilote `psycopg` non installé dans l'environnement | MAJEURE (audit) | Toute connexion PostgreSQL impossible même avec des identifiants | `pip install psycopg[binary]` sur l'hôte d'audit | Responsable technique |
| **P1.4** | `POSTGRES_HOST` **vide** dans `deploy/production/.env.example`, `POSTGRES_PASSWORD=change-me` | **CRITIQUE** (sécurité) | Configuration de production non arrêtée ; mot de passe par défaut | Renseigner l'hôte et un mot de passe fort, hors dépôt, avant toute mise en service | DSI INJS |
| **P1.5** | Sortie réseau restreinte (seuls github.com / pypi.org) ; `injs.ci`, `api.injs`, IP privées injoignables ; `~/.ssh` absent | MAJEURE (audit) | Aucun tunnel ni accès distant | Ouvrir un accès (bastion/VPN) ou exécuter sur place | RSSI / DSI |
| **P1.6** | Aucune sauvegarde de production présente dans l'espace de travail | MINEURE | Aucun plan de repli si l'audit en production devait être interrompu | Produire une sauvegarde **avant** toute opération d'écriture sur la production | DSI INJS |
| **P1.7** | La base effectivement interrogée par l'environnement est **SQLite** (`backend/db.sqlite3`) | MAJEURE (méthode) | Toute commande lancée ici mesurerait le bac à sable, jamais la production | Toujours vérifier `current_database()` avant de publier un chiffre | Responsable technique |

---

## 5. PROCÉDURE PRÊTE À EXÉCUTER SUR LE SERVEUR DE PRODUCTION

À exécuter **par un opérateur habilité, sur le VPS**, après validation humaine.
Toutes les commandes sont **en lecture seule** (prévisualisation par défaut).

```bash
# 0. SE CONNECTER AU SERVEUR DE PRODUCTION (à adapter selon l'accès fourni)
ssh <utilisateur>@<hôte-de-production>

# 1. IDENTIFIER SANS AMBIGUÏTÉ LA BASE — ne pas aller plus loin si ce n'est pas la bonne
docker exec -it <conteneur-postgres> psql -U "$POSTGRES_USER" -c "SELECT current_database(), version();"
#   → la ligne DOIT afficher : injs_lmd_prod_20261026

# 2. CONTRÔLE DE COHÉRENCE DU RÉFÉRENTIEL (81 / 22 / 1 157)
docker compose -f deploy/production/compose.yml exec backend \
  python manage.py rbac_initialisation --json /tmp/RBAC_PRODUCTION_INVENTAIRE_20261106.json

# 3. RAPPORT DE PRÉVISUALISATION (aucune écriture — la commande est en lecture seule par défaut)
#    → fournit : utilisateurs, comptes RBAC existants / manquants, attributions par statut,
#      rôles sensibles, anomalies de périmètre, opérations qui SERAIENT effectuées.

# 4. UTILISATEURS SANS PROFIL RBAC ET ATTRIBUTIONS (contrôles complémentaires en lecture)
docker compose -f deploy/production/compose.yml exec backend python manage.py shell -c "
from authentication.models import User
from habilitations.models import CompteUtilisateur, AttributionRole, RoleMetier, PermissionMetier
print('utilisateurs', User.objects.count(), '| actifs', User.objects.filter(is_active=True).count(),
      '| superusers', User.objects.filter(is_superuser=True).count())
print('comptes RBAC', CompteUtilisateur.objects.count())
print('sans profil  :', list(
    User.objects.filter(is_active=True, profil_habilitation__isnull=True)
    .exclude(is_superuser=True).values_list('username', flat=True)))
print('attributions par statut :', dict(
    (s, AttributionRole.objects.filter(statut=s).count())
    for s in ('PROPOSEE','ACTIVE','SUSPENDUE','EXPIREE','REVOQUEE')))
print('rôles', RoleMetier.objects.count(), '| sensibles', RoleMetier.objects.filter(sensible=True).count())
print('permissions', PermissionMetier.objects.count())
"
```

Sorties attendues : `RBAC_PRODUCTION_INVENTAIRE_20261106.json` (inventaire), la
liste des comptes sans profil (→ CSV « comptes manquants ») et les compteurs
d'attributions (→ CSV « anomalies » une fois analysés).

> **Remarque** : l'export CSV direct n'existe pas encore dans la commande
> `rbac_initialisation`. Si vous le souhaitez, j'ajoute une option `--csv`
> **en lecture seule** (aucune écriture) qui produit directement les deux CSV
> attendus ; cette évolution est proposée, **non exécutée** (voir §6.C).

---

## 6. CONCLUSION

### A. Situation conforme

1. **Régime lecture seule respecté intégralement** : aucune commande
   `--apply`, aucun INSERT/UPDATE/DELETE, aucun DROP/RESET/FLUSH, aucune
   migration, aucun profil créé, aucune attribution ni révocation, aucun rôle
   ni permission modifié, aucun changement de statut, aucun élargissement de
   périmètre. **0 opération d'écriture.**
2. **Aucune initialisation RBAC déclenchée** — la commande n'a été exécutée
   qu'en mode prévisualisation, et seulement sur le bac à sable (annexe B) pour
   vérifier l'identité de la base.
3. **Règles d'audit respectées** : aucun rôle déduit de `User.role`,
   `CORRESPONDANCE_LEGACY` non utilisée, aucune sauvegarde substituée à la
   production.
4. **Référentiel de référence inchangé** : 81 rôles, 22 sensibles, 1 157
   permissions (état de référence confirmé le 6 novembre 2026, aucune
   divergence catalogue ↔ base, cf. `08-reconciliation-catalogue-roles.md`).

### B. Anomalies nécessitant une investigation

- **P1.2 (critique)** : le nom de base de production n'est confirmé nulle part ;
  il doit être vérifié sur le serveur avant tout audit.
- **P1.4 (critique)** : configuration de production incomplète et mot de passe
  par défaut (`change-me`) dans le modèle déployé.
- **P1.1 / P1.3 / P1.5 (majeures)** : l'environnement d'audit ne dispose d'aucun
  chemin d'accès à PostgreSQL.
- **P1.6 / P1.7** : pas de sauvegarde à disposition ; risque méthodologique de
  confondre SQLite de l'aperçu et production.

### C. Actions correctives proposées — **NON EXÉCUTÉES**

| # | Action | Prérequis |
|---|---|---|
| C1 | Confirmer sur le VPS le nom exact de la base et la version PostgreSQL | Accès serveur |
| C2 | Renseigner `POSTGRES_HOST` / `POSTGRES_DB` / `POSTGRES_PASSWORD` (hors dépôt) | DSI INJS |
| C3 | Installer `psycopg[binary]` sur l'hôte d'audit et ouvrir l'accès réseau (bastion/VPN) | RSSI / DSI |
| C4 | **Exécuter la procédure du §5** et publier les quatre livrables réels | Validation humaine |
| C5 | Ajouter l'option `--csv` (lecture seule) à `rbac_initialisation` pour produire nativement les deux CSV | Validation humaine |
| C6 | Réaliser une sauvegarde complète **avant** toute écriture en production | DSI INJS |
| C7 | Ne lancer **aucune** initialisation (`--apply`) avant la validation de ce rapport | Comité de validation |

### Synthèse finale

| Indicateur | Production `injs_lmd_prod_20261026` |
|---|---|
| Base identifiée | **NON** (nom absent du dépôt, serveur injoignable) |
| Base effectivement interrogée | `backend/db.sqlite3` (SQLite — **bac à sable**) |
| Nombre réel de comptes à examiner | **NON MESURABLE** |
| Profils RBAC manquants | **NON MESURABLE** |
| Attributions existantes | **NON MESURABLE** |
| Anomalies RBAC détectées | **0 détectée (aucune mesure possible — pas « 0 anomalie »)** |
| Anomalies de périmètre | **NON MESURABLE** |
| Anomalies d'accès à l'audit (Phase 1) | **7** (2 critiques, 3 majeures, 1 mineure) |
| **Opérations d'écriture effectuées** | **0 — ZÉRO** |

**Recommandation :** comme vous le préconisez, **aucune initialisation ne doit
être lancée** avant validation. À ce stade, l'initialisation ne peut de toute
façon pas être déclenchée : la cible n'est pas joignable.

---

## Annexe A — Contenu des livrables

| Fichier | Contenu |
|---|---|
| `RBAC_PRODUCTION_RAPPORT_20261106.md` | Ce rapport |
| `RBAC_PRODUCTION_INVENTAIRE_20261106.json` | **NON PRODUIT** — structure et statut d'indisponibilité, aucune donnée inventée |
| `RBAC_PRODUCTION_COMPTES_MANQUANTS_20261106.csv` | **NON PRODUIT** — ligne de statut, aucune ligne de compte |
| `RBAC_PRODUCTION_ANOMALIES_20261106.csv` | 7 anomalies réelles **d'accès à l'audit** (Phase 1), aucune anomalie RBAC produite |

## Annexe B — Mesures du bac à sable (HORS PRODUCTION — à ne pas confondre)

Rappelées **uniquement pour mémoire** : elles décrivent la base SQLite de
l'aperçu, **jamais** la production. Aucune de ces valeurs ne doit être retenue
comme un chiffre de production.

| Mesure | Bac à sable |
|---|---|
| Utilisateurs | 34 (tous actifs, 2 superutilisateurs) |
| Comptes RBAC | 0 |
| Attributions | 0 |
| Rôles / sensibles | 81 / 22 |
| Permissions | 1 157 |
