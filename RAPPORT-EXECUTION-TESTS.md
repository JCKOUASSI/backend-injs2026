# Rapport d'exécution des tests par groupes

**Date :** 29 octobre 2026 · **Branche :** `arena/d40e4a41-backend-injs2026`
**Objet :** diagnostic du blocage, découpage de la suite, résultats réels.

---

## 1. Diagnostic — le blocage n'était pas un test

### Ce qui a été vérifié avant toute relance

| Vérification | Résultat |
|---|---|
| Processus Django de test actifs (`ps`) | **Aucun** |
| Processus bloqué en attente | **Aucun** |
| Base de test résiduelle (`/tmp`, fichiers temporaires) | **Aucune** |
| Espace disque | 20 Go libres (5 % utilisés) |
| Verrou de base (`db.sqlite3` / SQLite en mémoire) | Aucun verrou |

**Conclusion : aucun processus n'était bloqué.** Le diagnostic a toutefois révélé la **cause racine réelle** :
le bac à sable a été recyclé entre deux tours, et les répertoires exclus des snapshots ont disparu :

| Élément | Avant | Après recyclage |
|---|---|---|
| `backend/.venv/` | présent | **absent** — le répertoire `.venv` est exclu des snapshots |
| `backend/db.sqlite3` | 5,7 Mo | **absent** |
| `backend/staticfiles/` | 830 fichiers | **absent** |
| `frontend/node_modules/` | présent | **absent** |
| `backend/.env` | présent | **absent** |

La commande intégrale n'échouait donc pas sur un test lent : elle ne trouvait plus l'interpréteur
(`.venv/bin/python: No such file or directory`), puis aurait dépassé la fenêtre d'attente de 15 min.

### Reconstruction effectuée

```bash
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
bash arena/bootstrap.sh --write-env          # recrée backend/.env, profil d'aperçu
python manage.py migrate --noinput
python manage.py import_referentiel_injs_lmd
python manage.py qualifier_referentiel_injs_l6
python manage.py configurer_referentiel_injs
python manage.py parametrer_notation_injs
python manage.py collectstatic --noinput
```

**Preuve de reproductibilité** — la base, repartie de zéro, redonne exactement le référentiel attendu :

```
UE         : 323 source / 323 base
ECUE       : 397 source / 397 base
Crédits    : 1170 source / 1170 base
Familles   : 12
Hors LMD   : 34 éléments
Anomalies  : Aucune
```

> Note : les 8 ECUE « archivées » signalées aux tours précédents n'apparaissent plus, car la base
> neuve crée directement les 397 ECUE correctes (l'archivage ne concernait que la migration
> depuis l'ancienne extraction `.docx`). Le compte final est identique : **397 ECUE actives**.

---

## 2. Méthode : exécution par groupes

Harnais versionné : **`arena/tests_par_groupe.sh`**.

Caractéristiques :

- un groupe = une ou plusieurs applications Django réelles ;
- chaque groupe borné par `timeout` (budget propre) ;
- **journal distinct** : `/tmp/injs-validation/<groupe>.log` ;
- **code de sortie conservé** : `<groupe>.exit` (0 = succès, 124 = interrompu, autre = échec) ;
- aucun `|| true`, aucun `tail` sur le code de sortie : un échec reste un échec ;
- exécution **séquentielle** (jamais deux suites en parallèle sur la même base de test) ;
- réutilisable : `./arena/tests_par_groupe.sh scolarite`.

---

## 3. Résultats réels

| Groupe | Applications | Code | Tests | Durée | Résultat |
|---|---|---:|---:|---:|---|
| `scolarite` | scolarite | 0 | 454 | 111 s | **RÉUSSI** |
| `formations` | formations | 0 | 270 | 69 s | **RÉUSSI** |
| `auth` | authentication | 0 | 239 | 136 s | **RÉUSSI** |
| `habilitations` | habilitations | 0 | 480 | 271 s | **RÉUSSI** |
| `edt` | edts, presences | 0 | 429 | 117 s | **RÉUSSI** |
| `evaluations` | evaluations, jurys | 0 | 230 | 86 s | **RÉUSSI** |
| `pilotage` | statistiques, config, dashboard | 1 | 195 | 26 s | **ÉCHOUÉ** (1 test) |
| `socle` | core, admissions, administrations, referentiels | 0 | 179 | 68 s | **RÉUSSI** |
| `divers` | parametres, suiviEvaluation, graduation, equivalences, stages, patrimoine, ressources_humaines, finances_etudiantes, exports | 0 | 136 | 26 s | **RÉUSSI** |
| **Total** | **21 applications** | — | **2 612** | — | **1 échec** |

**Cohérence vérifiée** : 454 + 270 + 239 + 480 + 429 + 230 + 195 + 179 + 136 = **2 612**, exactement
le total de la suite monolithique mesurée au tour précédent. **La totalité de la suite a donc bien
été exécutée**, par groupes, sans en omettre aucun.

### Frontend

| Commande | Code | Résultat |
|---|---:|---|
| `npm ci` | 0 | dépendances réinstallées |
| `npx vitest run` | **0** | **105 fichiers, 1 979 tests — RÉUSSI** |

---

## 4. Le seul échec

`config.tests.test_apercu_hardening.PreviewAutoLoginTests::test_admin_est_connecte_et_post_ne_bloque_pas_sur_csrf`

| | |
|---|---|
| **Source** | `backend/config/tests/test_apercu_hardening.py:188` |
| **Nature** | Le test poste `/admin/logout/` **sans jeton CSRF** avec `enforce_csrf_checks=True` et exige un code ≠ 403 |
| **Réponse obtenue** | **403** — comportement correct de Django |
| **Préexistence** | **Prouvée** : reproduit sur le commit de base `5369acf` dans un worktree isolé, sans aucune modification de ce travail |
| **Correction appliquée** | **Aucune, volontairement** |
| **Justification** | Faire passer ce test exigerait d'exempter la déconnexion du contrôle CSRF, c'est-à-dire d'affaiblir un contrôle de sécurité. Interdit par les consignes. |
| **Recommandation** | Corriger le **test** (envoyer un `csrfmiddlewaretoken` valide), pas l'application |
| **Statut** | **OUVERT** — décision du responsable technique |

---

## 5. Blocages rencontrés et traités

| # | Incident | Cause | Traitement | Statut |
|---|---|---|---|---|
| 1 | Interpréteur introuvable | `.venv` non persistant (snapshot) | Reconstruction du venv + `requirements.txt` | **Résolu** |
| 2 | Base absente | `db.sqlite3` non persistant | `migrate` + chaîne d'import complète | **Résolu** |
| 3 | Manifeste statique manquant (4 erreurs `dashboard`) | `staticfiles/` non persistant | `collectstatic` | **Résolu** |
| 4 | `node_modules` absent | Non persistant | `npm ci` | **Résolu** |
| 5 | Groupe `auth` interrompu à 420 s | `authentication` (188 s) + `habilitations` (355 s) = 543 s > budget | **Scission en deux groupes** (budgets 300 s et 600 s) | **Résolu** |
| 6 | Séparateur `read` du harnais | Bug de mon script (`apps` ne prenait que le 1ᵉʳ mot) | Séparateur `\|` | **Résolu** |
| 7 | CSRF `PreviewAutoLoginTests` | Préexistant | Non corrigé (sécurité) | **Ouvert** |

**Aucun test n'a été supprimé, désactivé ou affaibli pour obtenir un résultat vert.**

---

## 6. Bilan

| Catégorie | Nombre | Détail |
|---|---:|---|
| Tests **réussis** | **2 611** backend + **1 979** frontend | 8 groupes sur 9 + suite frontend complète |
| Tests **échoués** | **1** | CSRF préexistant, documenté |
| Tests **interrompus** | **0** (après scission du groupe `auth`) | 1 interruption transitoire, reprise avec un budget adapté |
| Tests **non exécutés** | **0** sur le périmètre backend | total des groupes = total monolithique |
| **NOT EXECUTED** | parcours navigateur réel | `libnss3` absent : rendu headless impossible |
| **NOT EXECUTED** | CI distante | aucun push effectué |

La suite backend **a été exécutée intégralement** (2 612 tests, par groupes). Elle n'est pas
« entièrement verte » : un test échoue, pour une raison préexistante et assumée.

---

## 7. Incident Git — re-clonage en cours de session

### Constat

En fin de tour, `git log` ne présentait plus que `3a9bb64` (base) comme ancêtre de la branche :
les **8 commits** des tours précédents (`b5d0968` → `0dc7588`) avaient disparu de `.git`.

### Cause

Le reflog est sans ambiguïté :

```
HEAD@{2}: clone: from https://github.com/JCKOUASSI/backend-injs2026.git
HEAD@{1}: checkout: moving from main to arena/d40e4a41-backend-injs2026
HEAD@{0}: commit: ...
```

Le répertoire `.git` a été **recréé par un clone neuf** en cours de session (même phénomène que
la disparition de `.venv`, `db.sqlite3`, `staticfiles`, `node_modules` et `.env`).
Les objets des commits locaux n'existaient plus dans la nouvelle base d'objets ; ils n'avaient
jamais été poussés, donc aucun distant ne les conservait.

### Impact réel : **aucune perte de contenu**

L'arbre de travail avait conservé l'intégralité des fichiers. Vérification fichier par fichier :

| Contenu critique | Présent |
|---|---|
| `FamilleModule`, `controler_completude`, clonage de la famille | ✅ |
| `INJS_AUTO_INSCRIPTION_PEDAGOGIQUE` (services + réglages) | ✅ |
| Complétude exposée dans l'API | ✅ |
| `statut_validation` / `valeur_institutionnelle` | ✅ |
| `_seuil_affiche` (aucun seuil inventé) | ✅ |
| `_cycle_de_intitule` (double suffixe corrigé) | ✅ |
| 6 rapports, 4 commandes, 1 script, 1 harnais de tests | ✅ |

Les 2 612 tests exécutés par groupes l'ont été **sur ce contenu exact** : leurs résultats restent valides.

### Traitement

| Action | Détail |
|---|---|
| Aucun `reset --hard`, aucun `clean`, aucune suppression | Respecté |
| Consolidation | `edc9569` — tout le contenu dans un commit unique et documenté |
| Classeur officiel | `2524a40` — ajout forcé (`.gitignore` ligne 48), branche autosuffisante |
| Fusion avec `origin/main` | **Refusée par Git** : histoires non liées (`3a9bb64` n'est pas un ancêtre de `c4886b8`). Aucune fusion forcée. |
| Vérification | Extraction rejouée depuis la branche : **19 feuilles, 323 UE** — fonctionne sans dépendre de `main` |

### Conséquence à retenir

Le travail reste **local et non poussé**. Un nouveau recyclage du bac à sable effacerait
définitivement ces commits. Une publication vers `origin/arena/d40e4a41-backend-injs2026`
est la seule protection durable.

---

## 8. Rejeu

```bash
cd /home/user/backend-injs2026
./arena/tests_par_groupe.sh                 # tous les groupes, séquentiel
./arena/tests_par_groupe.sh scolarite       # un seul groupe
./arena/tests_par_groupe.sh --lister        # inventaire des groupes

# Détail d'un groupe
cat /tmp/injs-validation/<groupe>.log
cat /tmp/injs-validation/<groupe>.exit
```
