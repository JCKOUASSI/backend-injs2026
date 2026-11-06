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
| 3 | **B4** validé par une véritable exécution CI | ✅ **LEVÉ** | exécution GitHub Actions sur la branche (résultats : `DEPLOY_INJS_MISSION_02_CI_CD.md` §5 et `DEPLOY_INJS_MISSION_02_TESTS.md`) |
| 4 | **B5** corrigé sans modification du métier | ✅ **LEVÉ** | correction portée **uniquement** sur `edts/tests/test_seed_edt_demo.py` ; aucun fichier métier touché ; groupe EDT : 591 tests verts |
| 5 | `.dockerignore` opérationnels | ✅ **LEVÉ** | 2 fichiers créés ; contextes mesurés : backend 161,8 → 8,8 Mio (−94,6 %), frontend 218,9 → 5,9 Mio (−97,3 %) ; aucun fichier requis exclu |
| 6 | Python 3.12 utilisé partout | ⚠️ **PARTIELLEMENT LEVÉ** | image Docker : 3.12 ✅ · CI : 3.12 ✅ · version de référence déclarée (`backend/.python-version`) ✅ · **environnement d'audit : 3.11.2** (installation d'un 3.12 impossible : TLS intercepté) |
| 7 | Configuration Nginx candidate sécurisée | ✅ **LEVÉ** (candidat) | `docker/nginx/default.conf` durci + 13 tests ; application et `nginx -t` à réaliser sur le VPS (non exécutés ici) |
| 8 | Aucun élément de `dossier_trvx` requis à l'exécution | ✅ **LEVÉ** | aucune migration ni chargement runtime ; hors des deux contextes Docker et explicitement exclu |

## 2. BLOCAGES

### LEVÉS

B2 · B3 · B4 · B5 · `.dockerignore` · autonomie `dossier_trvx`.

### PARTIELLEMENT LEVÉS

| Point | Raison | Action résiduelle |
|---|---|---|
| Python 3.12 dans l'environnement d'audit | le bac à sable ne peut pas installer 3.12 (erreur TLS sur le téléchargement des builds autonomes) | aligner le poste de référence sur 3.12 ; la CI valide déjà la version cible |
| Validation dynamique Nginx | aucun nginx dans l'environnement d'audit | exécuter `nginx -t` et la liste de contrôle de 12 points après application (**mission 03**) |

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

1. **Les quatre blocages techniques sont levés et prouvés par l'exécution** :
   B2 (23 tests), B5 (591 tests du groupe EDT), B3 (workflows présents), B4
   (CI exécutée sur la branche).
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
