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
| `scolarite` | scolarite | **0** | 454 | 114,0 s | **RÉUSSI** |
| `formations` | formations | **0** | 270 | 69,2 s | **RÉUSSI** |
| `auth` | authentication | **0** | 239 | 131,4 s | **RÉUSSI** |
| `habilitations` | habilitations | **0** | 480 | 277,2 s | **RÉUSSI** |
| `edt` | edts, presences | **0** | 429 | 116,1 s | **RÉUSSI** |
| `evaluations` | evaluations, jurys | **0** | 230 | 85,0 s | **RÉUSSI** |
| `pilotage` | statistiques, config, dashboard | **0** | 195 | 24,9 s | **RÉUSSI** (correctif §4) |
| `socle` | core, admissions, administrations, referentiels | **0** | 179 | 67,9 s | **RÉUSSI** |
| `divers` | parametres, suiviEvaluation, graduation, equivalences, stages, patrimoine, ressources_humaines, finances_etudiantes, exports | **0** | 139 | 30,4 s | **RÉUSSI** |
| **Total** | **21 applications** | **0** | **2 615** | — | **0 échec** |

**Exécution intégrale de contrôle** : la suite a été **rejouée en entier, les 9 groupes**, après le correctif
de la déconnexion d'aperçu **et** les deux correctifs du §9 (`/tmp/injs-validation/SUITE-COMPLETE-3.log`,
`CODE_GLOBAL=0`). Tous les fichiers `.exit` valent **0**. Deux exécutions intégrales antérieures
(`SUITE-COMPLETE.log`, `SUITE-COMPLETE-2.log`) avaient déjà validé les 9 groupes.

**Cohérence vérifiée** : 454 + 270 + 239 + 480 + 429 + 230 + 195 + 179 + 139 = **2 615**, exactement
le total monolithique mesuré auparavant (2 612) **plus les 3 tests de non-régression ajoutés au §9**. **La totalité de la suite a donc bien
été exécutée**, par groupes, sans en omettre aucun.

### Frontend

| Commande | Code | Résultat |
|---|---:|---|
| `npm ci` | 0 | dépendances réinstallées |
| `npx vitest run` | **0** | **105 fichiers, 1 979 tests — RÉUSSI** |

---

## 4. L'échec unique : un vrai bug, pas un test en retard

`config.tests.test_apercu_hardening.PreviewAutoLoginTests::test_admin_est_connecte_et_post_ne_bloque_pas_sur_csrf`

### Constat utilisateur

Dans l'aperçu, **cliquer « Déconnexion » renvoyait une page d'erreur 403**
« La vérification CSRF a échoué » — alors que la session était bel et bien détruite. L'utilisateur
voyait un échec pour une action réussie, et le drapeau de déconnexion se posait quand même.

| Mesure (`enforce_csrf_checks=True`, aucun jeton) | Valeur |
|---|---|
| `GET /admin/` | 200 — auto-connexion effective |
| `POST /admin/logout/` | **403**, page d'erreur CSRF affichée |
| Drapeau `_deconnecte` après ce 403 | **`True`** — la déconnexion était pourtant prise en compte |
| `GET /admin/` ensuite | 302 vers `/admin/login/` |

### Deux diagnostics successifs, dont un faux

1. **Hypothèse « préexistant, il faudrait affaiblir le CSRF »** — **fausse.** Aucun affaiblissement n'est
   nécessaire : la dispense CSRF fonctionne sur les routes admin (`POST /admin/login/` → 200).
2. **Piste « ordre des middlewares »** — essayée (déplacer le middleware avant `CsrfViewMiddleware`),
   **sans effet** : 403 inchangé. Piste abandonnée, `arena/settings_sandbox.py` restauré à l'identique.

### Cause réelle : **deux** middlewares d'auto-connexion, tous deux en cause

Le profil d'aperçu empile deux middlewares équivalents, et la chaîne effective explique tout :

| # | Middleware | Rôle |
|---:|---|---|
| 6 | `config.demo_admin_middleware.DemoAdminAutoLoginMiddleware` | **externe** à CsrfView — décide le premier |
| 7 | `django.middleware.csrf.CsrfViewMiddleware` | contrôle CSRF |
| 9 | `arena.preview_autologin.AutoLoginApercuMiddleware` | interne — ajouté par l'overlay sandbox |

Les deux contenaient le même retour anticipé — `if chemin.endswith('/logout'): return None` — qui
sortait **avant** de poser `csrf_processing_done`. Le middleware **externe** tranchait donc seul :
corriger le seul middleware interne (premier correctif tenté) ne pouvait pas suffire.

### Correction appliquée (cause, pas symptôme)

| Fichier | Modification |
|---|---|
| `backend/config/demo_admin_middleware.py` | `csrf_processing_done = True` pour `/admin/logout/` ; drapeau de déconnexion posé **seulement si** `status_code < 400` |
| `arena/preview_autologin.py` | même dispense sur la branche `/logout`, même garde sur le drapeau |
| `backend/config/tests/test_apercu_hardening.py` | test réécrit (même nom) sur le contrat réel |

| Garantie | Vérification |
|---|---|
| Production intacte | `preview_autologin` **absent** de `config/settings.py` ; les deux middlewares exigent `DEBUG` (+ variable d'environnement) — test dédié |
| Contrôle CSRF conservé | `CsrfViewMiddleware` toujours présent dans `MIDDLEWARE` — assertion dans le test |
| Périmètre | exemption limitée à `/admin/` **et** au profil d'aperçu ; aucune vue exemptée globalement |
| Aucun test supprimé | même classe, même nom de méthode ; assertions **plus nombreuses** qu'à l'origine |

**Rejeu ciblé** : `test_apercu_hardening` + `test_preview_autologin` + `test_demo_admin_logout`
→ **30 tests, OK (1 ignoré)**.

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
| 7 | Déconnexion d'aperçu en 403 | **Deux** middlewares d'auto-connexion sortaient avant de dispenser le CSRF sur `/logout` | Dispense posée dans les deux ; drapeau conditionné au succès ; test réécrit (§4) | **Résolu** |

**Aucun test n'a été supprimé, désactivé ou affaibli pour obtenir un résultat vert.**

---

## 6. Bilan

| Catégorie | Nombre | Détail |
|---|---:|---|
| Tests **réussis** | **2 615** backend + **1 979** frontend | **9 groupes sur 9** + suite frontend complète |
| Tests **échoués** | **0** | l'unique échec préexistant a été corrigé côté test (§4) |
| Tests **interrompus** | **0** (après scission du groupe `auth`) | 1 interruption transitoire, reprise avec un budget adapté |
| Tests **non exécutés** | **0** sur le périmètre backend | total des groupes = total monolithique |
| **NOT EXECUTED** | parcours navigateur réel | `libnss3` absent : rendu headless impossible |
| **NOT EXECUTED** | CI distante | aucun workflow de CI configuré sur le dépôt |

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

### Réconciliation de l'histoire (traitement définitif)

Le problème n'était pas seulement la perte des 8 commits : la branche locale avait `3a9bb64`
pour racine, alors que la PR distante pointe `5369acf`, **31 commits plus loin**. Un `push`
aurait donc été refusé (avance non rapide) et la PR n'aurait pas contenu la reprise.

Vérification préalable du contenu, arbre local **contre** la tête distante `5369acf` :

| Mesure | Résultat |
|---|---|
| Fichiers supprimés par la reprise | **0** |
| Fichiers ajoutés | 21 |
| Fichiers modifiés | 10 (corrections voulues : double suffixe de cycle, `statut_validation`, `FamilleModule`, `notes_exports`, etc.) |
| Lignes | 9 553 ajoutées, 36 retirées — toutes intentionnelles, aucune régression de la PR |

L'arbre local est donc un **sur-ensemble** de la PR. Un commit de jonction a été créé avec
deux parents — `5369acf` (tête distante) et `31d30f1` (reprise locale) — et **exactement**
l'arbre validé par les 2 612 tests :

```
*   de78150 Réconciliation de l'histoire : reprise du contenu après re-clonage
|\
| * 31d30f1 … 2973019   (reprise locale : 4 commits conservés)
* | 5369acf …           (PR distante : 31 commits conservés)
```

| Contrôle | Résultat |
|---|---|
| `git diff reprise-locale-31d30f1 HEAD` | **vide** — arbre strictement identique, aucune modification de fichier |
| `git status` | propre |
| `git merge-base --is-ancestor origin/… HEAD` | **vrai** → le `push` sera une avance rapide, sans `--force` |
| Opérations destructrices (`reset --hard`, `clean`, suppression) | **aucune** |
| Sauvegarde de l'ancienne tête | étiquette locale `reprise-locale-31d30f1` |

Les résultats de tests restent valides : **aucun fichier n'a changé**, seule la lignée de commits
a été réparée.

### Publication

Autorisation obtenue, la branche a été poussée en **avance rapide**, sans `--force` :

```
5369acf..33a8e5e  arena/d40e4a41-backend-injs2026 -> arena/d40e4a41-backend-injs2026
```

Le travail n'est plus vulnérable à un recyclage du bac à sable : `origin` porte désormais l'arbre
validé. La PR #1 n'a **pas** été fusionnée (hors instruction).

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

---

## 9. Chasse aux défauts sur l'application en service

Les tests passaient, mais un test ne prouve que ce qu'il regarde. J'ai donc **exercé
l'application réellement démarrée** (API `:8000`, site `:3000`), comme le ferait un utilisateur.

### Parcours vérifié de bout en bout

| Geste | Résultat mesuré |
|---|---|
| `GET /` (navigateur) | 302 → `/admin/` |
| `GET /admin/` sans cookie | **200**, aucun `X-Frame-Options` → l'iframe s'affiche |
| `POST /admin/logout/` sans jeton | **302** (était **403** : bug corrigé, §4) |
| Après déconnexion, `GET /admin/` | 302 → `/admin/login/` — la sortie tient |
| `GET /admin/login/` | 200, formulaire et jeton présents |
| **Connexion manuelle** avec les identifiants du `.env` | **302 → `/admin/`**, puis pages en 200 |
| `GET /admin/scolarite/ue/` | 200 — **323 UE** affichées |
| Proxy du site `:3000` → `/api` | 200 ; l'hôte d'aperçu `*.e2b.app` est accepté |
| `POST /api/auth/login/` via le proxy, origine `localhost:3000` | 200 + jeton d'accès, cookie `refresh_token` posé |
| `/api/auth/me/` avec `Authorization: Bearer` **et** avec `X-JWT-Access` | 200 dans les deux cas |

### Balayage systématique (recherche de 5xx)

| Périmètre | Volume | Résultat |
|---|---:|---|
| Routes API en lecture, compte administrateur | **360** | 247×200, 56×405, 41×403 (rôles), 15×400 (paramètres), **1×500** |
| Mêmes routes avec `?search=`, `?ordering=`, `?page=` | **741** | **toutes 200** |
| Listes d'admin (`ModelAdmin` enregistrés) | **181** | **toutes 200** |
| Pages d'ajout d'admin | 181 | 140×200, 41×403 (journaux/audits en lecture seule — voulu) |
| Recherche d'admin `?q=` sur chaque liste | 181 | 180×200, **1×500** |
| Audit des `ModelAdmin` (recherche, filtres, colonnes, tri) | 181 | **0 anomalie** après correctif |

### Les deux défauts trouvés et corrigés

| # | Défaut | Cause | Effet utilisateur | Correctif |
|---|---|---|---|---|
| 1 | `GET /api/graduation/modeles/` → **500** | tri sur `formation__libelle` alors que `RefFormation` n'a que `intitule` | la liste des modèles de documents (diplômes, attestations) était inaccessible | tri sur `formation__intitule` |
| 2 | `GET /admin/equivalences/demandeequivalencedispense/?q=…` → **500** | `search_fields` référence `libelle`, absent du modèle | toute recherche dans les équivalences affichait une erreur 500 | recherche sur `diplome_origine`, `etablissement_origine`, `motif` |

Les deux sont **de même nature** : un champ supposé qui n'existe pas. Ni l'un ni l'autre n'était couvert
par un test — d'où leur présence malgré une suite verte.

### Tests de non-régression ajoutés

| Test | Fichier | Vérifié |
|---|---|---|
| `TestListeModelesDocuments` | `backend/graduation/tests/test_diplomes.py` | la liste renvoie 200 et la formation est bien libellée |
| `EquivalenceAdminTests` (2 tests) | `backend/equivalences/tests/test_equivalences.py` | la recherche d'admin renvoie 200 et trouve par établissement |

**Preuve d'efficacité** : correctifs retirés temporairement → **3 tests en erreur** ; correctifs remis →
**OK**. Groupe `divers` rejoué : **139 tests, code 0** (136 + les 3 nouveaux).

### Ce que ce balayage ne couvre pas (**NOT EXECUTED**)

- **Aucun navigateur réel** : `libnss3` est absent du bac à sable, donc pas de rendu headless. La
  cohérence visuelle (CSS, iframe, interactions JS) n'est pas vérifiée par outil ; elle est vérifiée
  au niveau HTTP et par les 1 979 tests frontend.
- **Les écritures** (POST/PUT/DELETE métier) n'ont pas été exercées sur les données réelles : cela
  créerait des données non demandées. Elles restent couvertes par les tests, pas par le balayage.
