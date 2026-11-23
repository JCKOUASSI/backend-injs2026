# Rapport de validation finale — backend-injs2026

**INJS d'Abidjan — Marcory, Côte d'Ivoire**
**Date :** 29 octobre 2026
**Branche :** `arena/d40e4a41-backend-injs2026` · **HEAD :** `8ce819c`
**Objet :** consolidation contrôlée du travail existant, sans réaudit ni réécriture.

---

## 1. Acquis vérifiés

### Commits (base `5369acf`)

| Commit | Objet | Vérifié |
|---|---|---|
| `b5d0968` | Extraction du référentiel, maquettes UE/ECUE, import idempotent | ✅ |
| `4b08738` | Premier rapport et annexe | ✅ |
| `7edc6dd` | Extraction XLSX, familles de modules, chaîne pédagogique | ✅ |
| `1abbd88` | Classeur officiel + repli `.docx` versionnés | ✅ |
| `986e97e` | API maquettes : lecture des UE, filtres robustes | ✅ |
| `e64b4a6` | Rapport 8 sections, annexe régénérée | ✅ |
| `8ce819c` | **Complétude, notation provisoire, contrôle source↔base** (ce tour) | ✅ |

- Dépôt **propre** au début et à la fin des travaux : aucune modification non commitée, aucun `reset`, aucun `clean`.
- Rapports présents et à jour : `RAPPORT-CONFIGURATION-REFERENTIEL-INJS.md`, `ANNEXE-MAQUETTES-INJS.md`, + les trois nouveaux.

### Résultats de tests : annoncés **vs** mesurés

| Annoncé précédemment | Réellement mesuré | Écart |
|---|---|---|
| 1 020 tests backend | **1 030** sur le sous-ensemble annoncé (scolarite + formations + admissions + edts) | +10 (28 tests de conformité ajoutés, −18 dus à un comptage antérieur imprécis) |
| 1 979 tests frontend | **1 979** (105 fichiers) | conforme |
| 45 tests ajoutés | **73** (45 + 28) | +28 ce tour |

**Correction de documentation** : le rapport précédent annonçait « 1 020 » ; la valeur reproductible est **1 030** pour ce sous-ensemble, et **2 612** pour la suite backend complète. Les chiffres du présent rapport sont ceux mesurés.

---

## 2. Séparation des inscriptions — préservée

La règle `test_la_validation_ne_cree_aucune_inscription_pedagogique` est intacte et **non modifiée**.

| Vérification | Résultat |
|---|---|
| Comportement par défaut | La validation administrative **ne crée rien** (test dédié avec maquette ACTIVE) |
| Paramètre `INJS_AUTO_INSCRIPTION_PEDAGOGIQUE` | Présent, **`False` par défaut** (`config/settings.py`) |
| Régime activé | Génère les inscriptions pédagogiques depuis la maquette ACTIVE (test `@override_settings`) |
| Idempotence | Revalidation et relance : **0 doublon** |
| Journalisation | `INSCRIPTION_PEDAGOGIQUE_GENEREE` / `INSCRIPTION_PEDAGOGIQUE_DIFFEREE` |
| Sans maquette active | Validation **réussit**, génération **différée + journalisée**, jamais contournée |
| Contournement de validation | Aucun : la génération passe toujours par `generer_inscriptions_pedagogiques`, qui exige `inscription.est_valide` |
| Tests existants | Conservés : `test_frontieres_metier` (2 tests) verts |

---

## 3. Master MS — crédits manquants

### Localisation exacte

| Élément | Valeur |
|---|---|
| Maquette concernée | F04 MS, niveau **M1** (identifiant 9) |
| S7 documenté | **9 UE — 30 ECTS** |
| **S8 documenté** | **0 UE — 0 ECTS** |
| Total du niveau | **30 / 60 ECTS** |
| Crédits manquants | **30**, intégralement situés au **semestre 8** |
| Total Master MS | **270 / 300 ECTS** |
| Total filière MS | 73 UE · 94 ECUE · 270 ECTS |

### Cause

Le classeur officiel ne contient **aucune ligne** pour `MS | Semestre 2 (M1/S8)` dans la feuille « 8. Base UE ». Le document passe de « Semestre 1 (M1/S7) » à « Semestre 3 (M2/S9) ». Ce n'est pas un défaut d'extraction : les 39 autres couples filière × semestre totalisent exactement 30 ECTS.

### Conséquences contrôlées

- **Aucune UE, aucun crédit, aucun semestre n'a été créé** pour combler l'écart.
- La maquette M1 reste en `BROUILLON` : elle n'a jamais été activée, donc aucune inscription pédagogique impossible n'est générée.
- `Maquette.controler_completude()` détecte et localise l'incomplet : `complet=False`, `semestres_vides=[8]`, `credits_manquants=30`.
- L'API expose ce diagnostic (`completude`) sur le détail et le workflow de maquette.
- La commande `controler_referentiel_injs` le signale à chaque exécution.

**Statut : BLOQUÉ** — seule une source officielle peut fournir la maquette MS S8.

---

## 4. Filières F05 à F08 — état de complétude

| Code | Filière | École | Cycles | UE documentées | ECUE | Maquette |
|---|---|---|---|---:|---:|---|
| F05 | Andragogie | ENSEP (STASE) | Licence + Master pro | **0** | 0 | ❌ |
| F06 | Loisir | ENSEP (STASE) | Licence + Master pro | **0** | 0 | ❌ |
| F07 | Entrepreneuriat Jeunesse et Conduite de Projets | ENSEP (STASE) | Licence + Master pro | **0** | 0 | ❌ |
| F08 | Gérontologie | ENSEP (STASE) | Licence + Master pro | **0** | 0 | ❌ |

**Confirmé par la source** : existence des filières, école de rattachement, diplômes délivrés (Licence pro + Master pro STASE).
**Absent de la source** : tout tableau UE/ECUE, tout code de filière (le classeur écrit « — »), toute maquette.

### Comportement de l'application

| Exigence | Vérification |
|---|---|
| Enregistrer et consulter les filières | ✅ 4 `RefFormation` en périmètre INJS, visibles en admin et en API |
| Ne pas autoriser d'inscription pédagogique impossible | ✅ `generer_inscriptions_pedagogiques` lève `PedagogieImpossible` (« Aucune maquette active… ») — test dédié |
| Ne générer aucune maquette fictive | ✅ 0 maquette pour F05–F08 (test dédié) |

**Statut : VALIDÉ SOUS RÉSERVE** — consultation opérationnelle ; maquettes **BLOQUÉES** par la source.

---

## 5. Les 34 éléments hors LMD

Voir **`TABLEAU-DECISION-34-ELEMENTS.md`** (livrable complet, ligne par ligne).

| Catégorie | Nombre | Importés en `RefFormation` | Doublons |
|---|---:|---|---|
| Concours « Professorat de collège » | 4 | **Non** | 0 |
| Cycles professionnels | 13 | **Non** | 0 |
| Formations à la carte | 17 | **Non** | 0 |
| **Total** | **34** | **0** | **0** |

- **Rattachement** : tous sont rattachés à une **école** (ENSEPS/ENSEP), aucun à une filière F01–F08. Aucune filière n'a donc été affectée.
- **Compatibilité** : `RefFormation` **peut** stocker ces objets (`type_diplome` accepte `PROFESSIONNALISANT`/`AUTRE`) mais les **confondrait** avec des diplômes LMD, puisqu'aucune distinction de nature n'existe et qu'ils ne peuvent porter ni semestre, ni maquette, ni crédits.
- **Solution proposée, non déployée** : référentiel séparé (`TypeOffre` + `RefOffre`) rattaché à l'école, sans lien avec `Maquette`/`UE`. Le déploiement engagerait l'architecture : il attend un arbitrage.

**Statut : EN COURS** — éléments identifiés, contrôlés, documentés ; importation volontairement non réalisée.

---

## 6. Paramètres de notation — état de validation

| Paramètre | Valeur | Source | Statut | Appliqué ? |
|---|---|---|---|---|
| `notation.poids_controle_continu` | 0,4 | Feuille 11, cellule F2 | **PROVISOIRE** | **Non** |
| `notation.poids_examen` | 0,6 | Feuille 11, cellule H2 | **PROVISOIRE** | **Non** |
| `notation.seuil_validation_ue` | 10 | Feuille 12, « UE validées (>= 10) » | **PROVISOIRE** | **Non** |

### Dispositif mis en place

- Nouveau champ `Parametre.statut_validation` (`VALIDE` / `PROVISOIRE`), migration additive `0011`, **défaut `VALIDE`** pour ne rien changer aux paramètres existants.
- `Parametre.valeur_institutionnelle(cle)` : renvoie la valeur **uniquement** si le paramètre est actif **et** au statut VALIDÉ, sinon `None`. Aucun calcul ne peut donc consommer silencieusement une valeur provisoire.
- Commande `parametrer_notation_injs` : crée les 3 paramètres en PROVISOIRE, **idempotente**, ne détruit jamais une valeur saisie par l'établissement (sauf `--force`), écrit l'historique `ParametreHistorique`, et `--valider` les promeut (décision institutionnelle).
- Champs exposés en API (`/api/parametres/`, statut `PROVISOIRE` visible) et en admin (colonne + filtre).

### Contrôle des valeurs par défaut silencieuses

| Point audité | Constat | Action |
|---|---|---|
| `evaluations/services/calcul.py` | Seuil absent → motif `REGLE_ABSENTE`, aucune valeur supposée | ✅ conforme, inchangé |
| `presences/notes_exports.py` | Repli silencieux **`12`** alors que le reste du code utilise 10 | **Corrigé** : un seuil absent s'affiche « non paramétré » |
| `RegleValidationLMD.seuil_admission` | `default=10`, alimenté par l'import structurel A-4.4 | Conservé : règle LMD existante et documentée, non modifiée |

**Statut : VALIDÉ** — les paramètres sont configurables sans modification de code, leur caractère provisoire est explicite et aucun calcul ne les applique.

---

## 7. Contrôle des 323 UE

Voir **`RAPPORT-CONTROLE-323-UE.md`** (livrable complet).

| Contrôle | Résultat |
|---|---|
| UE source / base | 323 / 323 |
| ECUE source / base | 397 / 397 (+8 archivées) |
| Crédits source / base | 1 170 / 1 170 |
| Clés métier manquantes / dupliquées | 0 / 0 |
| UE sans ECUE, sans crédits, sans famille | 0 / 0 / 0 |
| Semestres ≠ 30 ECTS | 0 |
| Annexe ↔ source (champ par champ, 323 lignes) | **0 écart** |
| Annexe ↔ base (intitulé, ECTS, famille, ECUE) | **0 écart** |
| Doublons de code, orphelines | 0 |

**Traçabilité** : chaque UE conserve la **clé métier officielle** du classeur (`EM|Semestre 1|Sciences de la vie et de la santé`) dans `cle_source`. Les codes `EM-S1-UE01` sont **techniques** et documentés comme tels : le classeur ne publie aucune codification officielle.

---

## 8. Corrections effectuées ce tour

| # | Anomalie | Source | Impact | Correction | Statut |
|---|---|---|---|---|---|
| 1 | `cloner()` perdait la famille des UE | Mon ajout du tour précédent | Nouvelle version inexploitable pour l'analyse des crédits | `famille=ue.famille` + test | ✅ Corrigé |
| 2 | Repli silencieux à **12/20** | `presences/notes_exports.py` (préexistant) | Document affichant un seuil non paramétré | `_seuil_affiche()` → « non paramétré » + tests | ✅ Corrigé |
| 3 | Aucun moyen de détecter une maquette incomplète | Manque fonctionnel | MS M1 à 30/60 invisible | `Maquette.controler_completude()` + API | ✅ Corrigé |
| 4 | Paramètres de notation non distingués d'une règle validée | Manque fonctionnel | Risque d'application silencieuse | `statut_validation` + `valeur_institutionnelle()` + commande | ✅ Corrigé |
| 5 | Aucun contrôle source↔base automatisable | Manque fonctionnel | Dérive silencieuse possible | Commande `controler_referentiel_injs` (`--json`, `--strict`) | ✅ Corrigé |
| 6 | Contrôle dépendant du drapeau « année courante » | Défaut de mon code | Faux `MAQUETTE_ABSENTE` hors base de démo | Sélection par année la plus récente | ✅ Corrigé |
| 7 | 4 erreurs `dashboard` (manifeste statique) | Environnement | Erreurs de test non reproductibles | `collectstatic` (procédure de déploiement) | ✅ Résolu |
| 8 | `PreviewAutoLoginTests::test_admin_est_connecte_et_post_ne_bloque_pas_sur_csrf` | **Préexistant** | 1 test en échec dans la suite complète | **Non corrigé — voir §10** | ⚠️ Ouvert |

---

## 9. Tests exécutés (résultats réels)

| Commande | Résultat |
|---|---|
| `manage.py check` | 0 problème |
| `manage.py test` (suite backend **complète**) | **2 612 tests — 1 échec, 0 erreur, 8 ignorés** |
| `manage.py test scolarite formations admissions edts` | **1 030 OK** (4 ignorés) |
| `manage.py test scolarite parametres presences evaluations jurys` | **916 OK** (2 ignorés) |
| `manage.py test scolarite.tests.test_conformite_referentiel` | **28 OK** |
| `manage.py controler_referentiel_injs --strict` | **0 anomalie**, 9 constats, code 0 |
| `npx vitest run` | **105 fichiers, 1 979 tests OK** |
| `npm run build` | **succès** (4,24 s) |
| Migrations | 3 nouvelles, toutes additives et appliquées : `scolarite/0016`, `scolarite/0017`, `parametres/0011` |

### Le seul échec restant

`config.tests.test_apercu_hardening.PreviewAutoLoginTests::test_admin_est_connecte_et_post_ne_bloque_pas_sur_csrf`

- **Reproduit sur le commit de base `5369acf`**, dans un worktree isolé, **sans aucune de mes modifications** → il préexiste.
- **Nature** : le test poste `/admin/logout/` **sans jeton CSRF** en imposant `enforce_csrf_checks=True`. Le rejet 403 est le comportement **correct** de Django.
- **Pourquoi je ne le corrige pas** : le faire passer supposerait d'exempter la déconnexion du contrôle CSRF, c'est-à-dire d'**affaiblir un contrôle de sécurité** — explicitement interdit. Le test est contradictoire avec la protection qu'il prétend vérifier.
- **Recommandation** : corriger le **test** (poster un `csrfmiddlewaretoken` valide), pas l'application. Décision laissée au responsable technique, car elle touche une suite de tests d'infrastructure d'aperçu.

**NOT EXECUTED** — parcours en navigateur réel : aucun rendu headless disponible (`libnss3` absent). L'API consommée par l'écran est testée ; le rendu visuel ne l'est pas.
**NOT EXECUTED** — CI distante : aucun push effectué.

---

## 10. Décisions institutionnelles encore indispensables

1. **Maquette MS S8** — fournir les UE/ECUE officielles du semestre 2 (M1/S8) de Management du Sport.
   *Impact :* Master MS à 270/300 ECTS. *Après décision :* `python manage.py configurer_referentiel_injs`.

2. **Maquettes F05–F08** — fournir les tableaux UE/ECUE d'Andragogie, Loisir, ECJP et Gérontologie.
   *Impact :* 4 filières consultables mais sans parcours pédagogique possible.

3. **Statut des 34 éléments hors LMD** — confirmer la nature (diplômante ou non) et le modèle de représentation.
   *Impact :* importation en attente. *Après décision :* création du référentiel séparé puis import.

4. **Validation des paramètres de notation** (0,4 / 0,6 / 10) par le règlement des études.
   *Après décision :* `python manage.py parametrer_notation_injs --valider`.

5. **Sort du test CSRF préexistant** — autoriser la correction du test (recommandé) ou assumer un échec documenté.

---

## 11. Données et sécurité

- Base de test **isolée** créée et détruite par le runner Django ; imports réels effectués sur la base de développement locale, **vide de référentiel** avant travaux.
- **Aucune** réinitialisation destructive : pas de `flush`, `reset`, `DROP`, `git reset --hard`, `git clean -fd`.
- Migrations **additives** uniquement ; aucune donnée métier supprimée (8 ECUE surnuméraires **archivées**).
- Aucune valeur officielle inventée : les 3 paramètres de notation sont **provisoires et inertes**.
- Permissions vérifiées : anonyme 401 · rôle non habilité 403 · DIRECTION lecture seule · ADMIN complet.
- **Aucun secret** dans le code, les commits ou les rapports ; `backend/.env` non versionné.

---

## 12. État Git

| | |
|---|---|
| Branche | `arena/d40e4a41-backend-injs2026` |
| HEAD | `8ce819c` |
| Commits de la session | `b5d0968` → `8ce819c` (7 commits) |
| Nouveaux fichiers de ce tour | `parametres/management/commands/parametrer_notation_injs.py`, `parametres/migrations/0011_statut_validation.py`, `scolarite/management/commands/controler_referentiel_injs.py`, `scolarite/tests/test_conformite_referentiel.py`, `TABLEAU-DECISION-34-ELEMENTS.md` |
| Fichiers modifiés | `parametres/{models,admin,serializers}.py`, `presences/notes_exports.py`, `scolarite/{models,api_views}.py`, `scripts/extraire_referentiel_offre_formation.py`, `scolarite/data/referentiel_offre_formation.json` |
| Migrations créées | `scolarite/0016`, `scolarite/0017`, `parametres/0011` |
| Tests ajoutés (total) | **73** |
| Publication | **Aucun push.** PR #1 ouverte, non fusionnée. |

---

## Conclusion

Le référentiel officiel est **intégralement reproductible** : source → extraction → import → contrôle, sans invention. Les trois incomplétudes restantes (MS S8, F05–F08, 34 éléments hors LMD) sont **celles de la source officielle**, désormais détectées, localisées et signalées automatiquement au lieu d'être invisibles.

**Le projet n'est pas déclaré entièrement conforme** : quatre décisions institutionnelles conditionnent la complétude du référentiel, et un test de sécurité préexistant reste en échec pour une raison assumée.
