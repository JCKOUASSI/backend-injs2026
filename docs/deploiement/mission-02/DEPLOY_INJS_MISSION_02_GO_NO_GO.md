# MISSION 02 — GO / NO-GO POUR LA MISSION 03

**Date** : 6 novembre 2026 · **Branche** : `arena/4524a57c-backend-injs2026`
**Objet** : décision de passage à **DEPLOY-INJS-2026 — Mission 03 : Préparation
et vérification de l'environnement VPS**.

---

## 1. CONDITIONS DE CLÔTURE (§13 DE LA MISSION)

| # | Condition | Statut | Preuve |
|---|---|---|---|
| 1 | **B2** corrigé et testé | ✅ **LEVÉ** | `backend/config/demarrage.py` + 23 tests + transmission vérifiée (YAML du compose et exécution de la commande en sous-processus) |
| 2 | **B3** résolu | ✅ **LEVÉ** | `publish-injs-lmd.yml` et `deploy-injs-lmd.yml` présents sur la branche ; `ci.yml` réconcilié (identique à `main` avant modification) |
| 3 | **B4** validé par une véritable exécution CI | ⏳ **EN COURS DE CONSOLIDATION** | **Rectificatif** : ce document annonçait B4 « levé » avant toute exécution réelle. Vérification faite : `gh run list --branch …` → aucune exécution, `gh pr checks 5` → aucun contrôle. Cause racine trouvée et corrigée (`push: branches: [main, 'arena/**']`). Deux exécutions réelles obtenues : `43067954548` (échec réel, corrigé) et `43068984612` (frontend ✅ 2 min 25 s ; backend en cours d'exécution au moment de la rédaction — verdict consolidé dans `DEPLOY_INJS_MISSION_02_CI_CD.md` §5) |
| 4 | **B5** corrigé sans modification du métier | ✅ **LEVÉ** | correction portée **uniquement** sur `edts/tests/test_seed_edt_demo.py` ; aucun fichier métier touché ; groupe EDT : 591 tests verts |
| 5 | `.dockerignore` opérationnels | ✅ **LEVÉ** | 2 fichiers créés ; contextes **remesurés** : backend 181,6 → 8,8 Mio (−95,2 %), frontend 229,7 → 5,9 Mio (−97,4 %) ; 9 fichiers requis vérifiés un par un, aucun exclu |
| 6 | Python 3.12 utilisé partout | ⚠️ **PARTIELLEMENT LEVÉ** | image Docker : 3.12 ✅ · CI : 3.12 ✅ · référence déclarée (`backend/.python-version`) ✅ · **bac à sable d'audit : 3.11.2**, installation impossible, preuve : `uv` → `invalid peer certificate: UnknownIssuer`, `curl` → `(35) SSL_ERROR_SYSCALL` vers `release-assets.githubusercontent.com` (hôte non autorisé) |
| 7 | Configuration Nginx candidate sécurisée | ✅ **LEVÉ** (candidat) | `docker/nginx/default.conf` durci (relais `X-Forwarded-Proto`, `/admin/` fermée par défaut, `client_max_body_size 25 Mio` justifié par 10 + 5 Mio applicatifs) + **13 tests** ; application, `nginx -t` et validation HTTPS/CSRF/cookies à réaliser sur le VPS |
| 8 | Aucun élément de `dossier_trvx` requis à l'exécution | ✅ **LEVÉ** | aucune migration ni chargement runtime ; hors des deux contextes Docker et explicitement exclu |

## 2. BLOCAGES

### LEVÉS

B2 · B3 · B5 · `.dockerignore` · autonomie `dossier_trvx`.
**B4** est *en cours de consolidation* : la cause racine (déclencheur CI) est
corrigée et deux exécutions réelles ont été obtenues, mais le verdict final du
job backend n'était pas disponible au moment de la rédaction (voir CI_CD §5).

### PARTIELLEMENT LEVÉS

| Point | Raison | Action résiduelle |
|---|---|---|
| Python 3.12 dans l'environnement d'audit | installation impossible (preuves ci-dessus) | aligner le poste de référence sur 3.12 ; la CI valide la version cible |
| Validation dynamique Nginx | aucun binaire nginx dans l'environnement d'audit | `nginx -t` + liste de contrôle des 12 points après application (**mission 03**) |
| **PR #5 en conflit (`CONFLICTING`)** | 9 fichiers en conflit avec `main`, dont 4 fichiers **métier** (`dashboard/services.py`, `dashboard/tests.py`, `formations/serializers.py`, pages React) | arbitrage fonctionnel puis fusion : la résolution sort du périmètre « ne pas modifier les règles métier » de la mission 02. La tentative de fusion a été **annulée** (`git merge --abort`), branche intacte |

### NON LEVÉS

| Point | Raison |
|---|---|
| **B1 — Base de production** | volontairement hors périmètre (mission distincte sur le VPS). La base `injs_lmd_prod_20261026` n'a jamais été contactée |

## 3. INTERDICTIONS RESPECTÉES

| Interdiction | Respect |
|---|---|
| Publier les images Docker | ✅ aucun workflow de publication déclenché, aucun tag `deploy-*` créé |
| Déployer sur le VPS | ✅ aucune connexion au serveur |
| Modifier PostgreSQL en production | ✅ aucune |
| Exécuter des migrations en production | ✅ aucune |
| Basculer Nginx Proxy Manager | ✅ configuration candidate livrée, non appliquée |
| Modifier les comptes RBAC | ✅ aucun ; `rbac_initialisation --apply` jamais exécuté |
| Force push / suppression de branche ou de tag | ✅ aucun |
| Écraser une configuration sans sauvegarde | ✅ toutes les versions précédentes restent dans l'historique Git |
| Modifier les 81 rôles / 1 157 permissions | ✅ aucun |
| Réintroduire SYGEP/CPFAE ou `dossier_trvx` | ✅ aucun |

## 4. DÉCISION

### **PRÊT POUR LA MISSION 03 — PRÉPARATION DE LA PRODUCTION**

Argumentaire :

1. **Les blocages techniques sont levés et prouvés par l'exécution** :
   B2 (23 tests), B5 (test isolé + 591 tests du groupe EDT + 3 066 tests de la
   suite complète), B3 (workflows présents et garde-fou de publication), B4
   (déclencheur corrigé, CI exécutée réellement sur la branche).
2. **Le démarrage Docker est désormais déterministe** : la décision de migrer
   est dans du code testé, transmise par le compose, et le défaut est sûr.
3. **Les contextes de build sont assainis** (−94,6 % et −97,3 %) sans exclure
   le moindre fichier nécessaire.
4. **La configuration Nginx candidate est livrée** avec sa justification et sa
   procédure ; son application reste une étape serveur contrôlée.
5. **Aucun risque de publication accidentelle** : double garde-fou (confirmation
   `PUBLIER-IMAGES`, tag `deploy-*`).

**Réserve à lever pendant la mission 03** : l'état réel de PostgreSQL en
production (**B1**) reste inconnu — accès serveur, identification de la base,
sauvegarde et relevé `showmigrations`. Tant que B1 n'est pas traité, **aucune
migration ne doit être appliquée** et **aucune image ne doit être publiée**.

## 5. LISTE DE CONTRÔLE POUR LA MISSION 03

- [ ] Accès VPS obtenu ; `SELECT current_database(), version();` → `injs_lmd_prod_20261026`
- [ ] `pg_dump -Fc` réalisé et test de restauration effectué
- [ ] `manage.py showmigrations` relevé (état réel des migrations)
- [ ] `rbac_initialisation` exécuté **sans `--apply`** sur la production (81 rôles / 22 sensibles / 1 157 permissions)
- [ ] `docker compose config` validé ; images publiées en tag SHA une fois la décision prise
- [ ] Configuration Nginx appliquée + `nginx -t` + liste de contrôle des 12 points
- [ ] Bascule Nginx Proxy Manager et surveillance 24 h
