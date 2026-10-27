# Audit des permissions — module Utilisateurs (LOT 4)

> **Rapport d'audit consolidé** · Date : 2026-09-14 · Branche :
> `arena/01a0a19d-app-injslmd2026demo`
> **Portée** : vérification par tests que les droits sont **correctement bornés**
> (refus croisés du prompt §34) et que la chaîne d'administration fonctionne de
> bout en bout (scénario §35), puis consolidation documentaire.
> **Précédents** : [`docs/audits/2026-09-14-audit-module-utilisateurs.md`](../audits/2026-09-14-audit-module-utilisateurs.md)
> (phase 0, §11/§12 = plan LOT 4), [`docs/curp/05-architecture-completion-module-utilisateurs.md`](../curp/05-architecture-completion-module-utilisateurs.md) §5.
> **Lectures complémentaires** : [`IAM.md`](../architecture/IAM.md),
> [`RBAC.md`](../security/RBAC.md),
> [`administration/utilisateurs.md`](../administration/utilisateurs.md).

---

## 1. Méthode

1. **Lecture du référentiel** avant tout test : catalogues
   (`catalogue_roles.py`, `catalogue_matrice.py`, `catalogue_modules.py`),
   chargement (`charger_referentiel`), puis mesures chiffrées en `dry_run`
   (aucune écriture).
2. **Caractérisation par tests, jamais par modification** : chaque comportement
   observé est figé par un test nommé d'après le fait, y compris lorsqu'il
   s'agit d'un écart (le test documente l'état livré, il ne « corrige » pas le
   produit).
3. **Moteur en mode APPLICATION sur une base de test uniquement**
   (`@override_settings(HABILITATIONS_OBSERVATION=True,
   HABILITATIONS_APPLICATION=True)`), base jetable Django — le dépôt livré reste
   `APPLICATION=false`, donc aucun refus ne peut atteindre l'environnement
   démarré.
4. **Refus d'abord** : aucun geste n'est déclaré « terminé » sans son test de
   refus correspondant (règle du chantier). Les tests d'autorisation sont
   toujours accompagnés de leur symétrique interdit.
5. **Preuve de journalisation** : chaque refus appliqué est vérifié dans le
   journal chaîné (`ACCES_REFUSE`), et l'intégrité de la chaîne est contrôlée
   (`verifier_chaine() == []`).
6. **Garde-fous vérifiés** : abstention sur compte non gouverné, no-op total en
   mode OFF, inertie du défaut livré, fermeture de la console par drapeau même
   pour un super-utilisateur.
7. **Additif uniquement** : deux nouveaux fichiers de tests, quatre nouveaux
   documents, index mis à jour. **Aucun fichier de production modifié**, aucune
   migration, aucun `flush`/`drop`/`truncate`.

### 1.1 Outillage utilisé

| Outil | Usage |
|---|---|
| `charger_referentiel(dry_run=True)` | volumes et anomalies du référentiel sans écrire |
| `habilitations.services.moteur.est_autorise()` | décision motivée, appelée directement (pur) |
| `habilitations.permissions.ExigePermission.pour(code)` | refus DRF journalisé, exercé via `has_permission()` |
| `habilitations.services.journalisation.verifier_chaine()` | intégrité de la piste d'audit |
| `habilitations.services.observation.remettre_a_zero()` | isolation des compteurs entre tests |
| DRF `APIClient` + `force_authenticate` / `credentials` | appels authentifiés, rebasculement d'identité |
| `cache.clear()` | neutralisation du throttle de connexion entre tests |
| `manage.py inventaire_habilitation --comptes`, `habilitations_diag`, `observations_habilitations` | inventaires d'état |

Piège consigné : avec **DRF `APIClient`**, `post(chemin, dict,
content_type='application/json')` envoie le dictionnaire brut (→ 400 *JSON parse
error*). Il faut `format='json'`. Le client Django de `TestCase` tolère
l'ancienne forme, ce qui masque l'erreur.

---

## 2. Volumes mesurés (référentiel, 2026-09-14)

| Objet | Valeur |
|---|---|
| Rôles | **81** (35 A1 + 46 cibles J2), dont **22 sensibles** |
| Permissions atomiques | **1 155** sur **20 modules** |
| Liaisons matrice (rôle × permission) | **10 440** |
| Permissions critiques (double validation) | **15** |
| Verbes | 13 canoniques → **31 actions** au modèle |
| Types de périmètre | **12** |
| Statuts de compte / canaux | **6** / 3 |
| Types d'événements du journal | **37** |
| Couples d'incompatibilité | **5** |
| Cases matrice | A2 = 35 lignes ; J2 = 46 rôles cibles + 12 lignes provisoires |
| Anomalies de chargement | **0** (rôle sans permission, permission orpheline, rôle indisponible) ; rechargement idempotent |

---

## 3. Résultats — tests de refus croisés (prompt §34)

**Fichier** : `backend/habilitations/tests/test_lot4_refus_croises.py`
**Résultat** : **51 tests, 51 OK** (mode APPLICATION sur base de test).

### 3.1 Enseignant (N2, MODULE_ECUE, canal MOBILE) — 8 tests

| Fait vérifié | Test |
|---|---|
| Autorisé sur **son** module/ECUE | `test_01` |
| **Refusé** sur le module d'un collègue (cible hors périmètre) | `test_02`, symétrie `test_03` |
| N'administre pas la fiche d'un collègue | `test_04` |
| Ne valide pas les notes (`evaluations.note.valider`) | `test_05` |
| Canal MOBILE imposé par le rôle → web refusé (`CANAL_IMPOSE_PAR_ROLE`) | `test_06` |
| Refus fonctionnel **tracé au journal** `ACCES_REFUSE` | `test_07` |
| Un accès autorisé ne produit **aucun** refus journalisé | `test_08` |

### 3.2 Chef de département (N3, périmètre DIRECTION) — 8 tests

| Fait vérifié | Test |
|---|---|
| Autorisé dans sa direction | `test_01` |
| Refusé dans la direction d'un autre chef | `test_02`, symétrie `test_04` |
| Refusé sur un département d'une autre direction | `test_03` |
| Couverture hiérarchique **par résolveur injecté** (département rattaché à la direction) | `test_05` |
| Ne valide pas un jury (`jurys.pv.signer`) | `test_06` |
| Ne crée pas de rôle (`administration.role.creer`) | `test_07` |
| Refus tracé au journal pour le compte concerné | `test_08` |

### 3.3 Étudiant (N1, PROPRE_COMPTE, canal MOBILE) — 8 tests

| Fait vérifié | Test |
|---|---|
| Consulte **son** dossier | `test_01` |
| Ne consulte pas le dossier d'un autre étudiant | `test_02`, symétrie `test_03` |
| Ne modifie pas son dossier | `test_04` |
| Ne force aucun émargement (`presences.emargement.forcer`) | `test_05` |
| Peut déposer un justificatif sur son propre compte | `test_06` |
| Un périmètre `PROPRE_COMPTE` **seul** ne couvre aucune cible nommée (sémantique documentée) | `test_07` |
| Canal WEB refusé à un compte mobile | `test_08` |

### 3.4 Agent de scolarité vs administrateur de rôles — 9 tests

| Fait vérifié | Test |
|---|---|
| Ne crée pas de rôle, ne valide pas d'attribution, n'administre pas la politique | `test_01`–`test_03` |
| Frontière en **lecture seule** sur le module `administration` | `test_04` |
| Garde son périmètre de scolarité ; **refusé hors de son secrétariat** | `test_05`, `test_06` |
| Console des comptes **refusée même drapeau ouvert** (`ExigeDrapeauAdmin`) | `test_07` |
| Un administrateur accède à la console dans le même contexte (contrôle croisé) | `test_08` |
| Refus produit par la **permission DRF** sur un acte d'administration | `test_09` |

### 3.5 Administrateur SI ≠ actes métier sensibles — 8 tests

| Fait vérifié | Test |
|---|---|
| Les 6 rôles du domaine TECHNIQUE (`SYSADMIN`, `DB_ADMIN`, `NETWORK_ADMIN`, `SECURITY_ADMIN`, `API_MANAGER`, `SUPPORT_IT`) ne portent **aucune** permission critique au catalogue | `test_01` |
| Ces rôles sont **hors de tout module métier** (candidatures, scolarité, évaluations, jurys, diplomation, finances…) | `test_02` |
| `SYSADMIN` refusé sur un paiement ; garde la main sur `parametres` | `test_03`, `test_04` |
| Rôle sensible sans seconde signature → refus ; sans MFA actif → refus | `test_05`, `test_06` |
| `DB_ADMIN` ne touche pas aux dossiers étudiants | `test_07` |
| **Écart J2-1 caractérisé** : la ligne A2 d'`ADMIN_SYSTEME` (`N4` sur les 15 modules) lui confère des actes métier critiques — contenu par les contrepoids (rôle sensible, MFA, double validation, motif, journal), **à arbitrer en atelier** | `test_08` |

### 3.6 Écart de couverture « objet métier » — 4 tests

| Fait vérifié | Test |
|---|---|
| Une cible **dict** `{type, object_id}` est couverte ; la **même cible en objet** ne l'est pas | `test_01` |
| Cause racine : `_decrire_perimetre()` n'expose pas `content_type_id` | `test_02` |
| Le refus sur objet est **quand même tracé** au journal | `test_03` |
| Un **résolveur injecté** par le contexte lève l'écart **sans correctif de production** | `test_04` |

### 3.7 Garde-fous — 6 tests

Compte non gouverné → **abstention** (pas un refus) ; compte suspendu → refus ;
anonyme → refus ; mode OFF → **no-op total** ; les refus ci-dessus sont bien
produits en mode APPLICATION (contrôle de non-régression du mode) ; **le défaut
livré est inerte**.

---

## 4. Résultats — scénario de bout en bout (prompt §35)

**Fichier** : `backend/habilitations/tests/test_lot4_e2e_scenario.py`
**Résultat** : **9 tests, 9 OK** (~7 s).

### 4.1 `test_01_scenario_complet_du_prompt_35` — 11 étapes chaînées

| # | Étape | Vérification |
|---|---|---|
| 1 | Création d'un compte par la console | `POST /comptes/` → 201, personne + compte + attribution, matricule `PERS-…`, journal `COMPTE_CREE` |
| 2 | Attribution du rôle `CHEF_DEPARTEMENT` (N3) | rôle actif, niveau effectif, `ROLE_ATTRIBUE` au journal |
| 3 | Création de l'organisation | Direction « DG » (+ « DAE »), département rattaché |
| 4 | Pose du périmètre DIRECTION | périmètre polymorphe lié à l'attribution |
| 5 | Connexion du nouveau compte | JWT + cookie refresh, `last_login` **et** `derniere_connexion` alimentés, `AuditLog USER_LOGIN` |
| 6 | Menu et capacités projetées | `GET /api/auth/capabilities/` → `habilitations.gouverne=true`, clé `habilitations` purement descriptive |
| 7 | **Accès autorisé** | `scolarite.groupe.modifier` sur la direction DG → autorisé |
| 8 | **Accès interdit** | même code sur une **autre** direction → refus `CIBLE_HORS_PERIMETRE` ; `jurys.pv.signer` → refus (niveau) |
| 9 | Refus par la permission DRF | `ExigePermission` → 403 motivé + `ACCES_REFUSE` journalisé |
| 10 | Modification du rôle + différentiel | simulation (gagnées/perdues/conservées) → `PATCH /modifier/` avec `differentiel_accepte` + `motif` |
| 11 | Recalcul + audit | perte de `scolarite.groupe.modifier`, conservation de `scolarite.dossier_etudiant.consulter` ; `verifier_chaine() == []` |

### 4.2 Étapes isolées (rejouables séparément)

| Test | Fait |
|---|---|
| `test_02` | Menu et projections pour le compte connecté |
| `test_03` | Recalcul après révocation du rôle |
| `test_04` | Piste d'audit complète **et intègre** (chaîne SHA-256) |
| `test_05` | Journal filtrable par compte et par type d'événement |
| `test_06` | Console fermée par drapeau, **même pour l'administrateur** |
| `test_07` | Création refusée sans motif ou avec rôle inconnu — **atomicité** : aucun `User` fantôme |
| `test_08` | Doublon d'identifiant → 409 `IDENTIFIANT_EXISTANT` |
| `test_09` | Suspension du compte → `is_active=False`, accès coupés (`COMPTE_SUSPENDU`) |

---

## 5. Écarts numérotés

| ID | Gravité | Écart | Preuve | Traitement |
|---|---|---|---|---|
| **L4-01** | **P0 (bloquant LOT 5)** | `moteur._decrire_perimetre()` omet `content_type_id` → une cible **objet métier** n'est jamais couverte au contrôle 9 (`CIBLE_HORS_PERIMETRE`). Seuls dict, `INJS_ENTIER`, la règle `SECRETARIAT` et un résolveur injecté fonctionnent. Conséquence : `has_object_permission` (donc tout branchement sur `get_object()`) refuserait tout en mode APPLICATION. | `test_lot4_refus_croises.py::CouvertureObjetEcartTests` (4 tests) | Correctif **additif d'une ligne** (exposer `content_type_id`) + tests de non-régression, **au LOT 5 sur feu vert**. Contournement déjà démontré : résolveur injecté (`contexte={'couverture': …}`). |
| **L4-02** | P1 | La console ne pose que des périmètres `SECRETARIAT` (`perimetres_secretariats`) ; tout autre type passe par l'admin Django. | `test_lot4_e2e_scenario.py` étape 4 (périmètre posé par ORM) | Ouvrir le sélecteur de périmètre dans l'assistant (LOT 5), additif. |
| **L4-03** | P2 | Une connexion réussie trace `presences.AuditLog` (`USER_LOGIN`) et les horodatages, mais n'émet pas d'événement `CONNEXION` au journal d'habilitation (type prévu au modèle, jamais émis). | `test_lot4_e2e_scenario.py::test_04` | Arbitrer : double piste assumée ou émission additive de `CONNEXION`. |
| **L4-04** | P2 | `journalisation._resoudre_cible()` exige une **instance** de modèle et lève sur un dict : un refus portant une cible dict n'est pas journalisé avec sa cible. | observations LOT 4 ; les tests de journal utilisent des instances | Rendre `_resoudre_cible` tolérant au format dict du contrat d'API (additif). |
| **J2-1** | Décision humaine | Ligne A2 d'`ADMIN_SYSTEME` = `N4` sur les 15 modules ⇒ actes métier critiques (`jurys.pv.signer`, `diplomation.diplome.valider`, `finances_etud.paiement.valider`) alors que le catalogue dit « sans intervenir sur les décisions métier ». | `test_lot4_refus_croises.py::AdminSiTests::test_08` | **Atelier J2** : restreindre la ligne ou formaliser la politique de contournement. Contenus aujourd'hui par rôle sensible + MFA + double validation + motif + journal. |
| **J2-2** | Décision humaine | `CHEF_DEPARTEMENT` reçoit `administration: N2` ⇒ création/modification de comptes et d'attributions **dans son périmètre**. | `…::ChefDepartementCroiseTests::test_07` | Atelier J2 : confirmer ou abaisser à N1. |
| **J2-3** | Décision humaine | Rôles SI portant un niveau minimal sur `parametres` (placeholder documenté). 0 acte métier sensible, 0 module métier — vérifié. | `…::AdminSiTests::test_01/02` | Atelier J2 : valider le périmètre technique. |
| **J2-4** | Décision humaine | Aucun type de périmètre `DEPARTEMENT` ; `DIRECTION` sert de périmètre par défaut aux rôles de département. Résolveurs hiérarchiques non livrés. | `…::ChefDepartementCroiseTests::test_05` | LOT 5 : ajouter le type + résolveurs (additif), ou assumer `DIRECTION`. |
| **L4-05** | Environnement | Suite backend complète : **1 556 tests, 4 erreurs, 5 ignorés**. Les 4 erreurs sont toutes `dashboard.tests.PublicBadgePage{Enabled,Disabled}Test` et proviennent du `CompressedManifestStaticFilesStorage` sans manifeste (`Missing staticfiles manifest entry for 'img/logo-injs.png'`) — `collectstatic` n'avait pas été joué dans le bac à sable. **Après `collectstatic`, ces 4 tests passent (OK)** : cause d'environnement, sans lien avec le LOT 4. Les 5 ignorés comprennent les 2 tests de déclencheurs d'immuabilité PostgreSQL. | `/tmp/tests_backend_lot4.log` (525 s) ; rejeu ciblé `manage.py test dashboard.tests.PublicBadgePage*` → OK après `collectstatic` | Ajouter `collectstatic` au préalable d'exécution de la suite (CI déjà pourvue) ; rejouer sous PostgreSQL en intégration ; **jamais** masquer l'écart. |
| **L4-06** | Documentation | Homonymie : `flag.lot01_…lot12_…` (lots de construction du produit) ≠ « LOT 1 → LOT 5 » (lots du module Utilisateurs). | seed `parametres/flags.py` vs plan CURP §7 | Clarifié dans [`IAM.md`](../architecture/IAM.md) §13 ; renommage **non** proposé (additif, risque de casse). |
| **L4-07** | P2 — **écart assumé** | La projection `permissions_effectives()` (`habilitations/services/comptes_admin.py`) applique le RETRAIT de façon **prioritaire et sans effet de date** (tri `-date_creation`, puis boucle qui écarte toute ligne déjà couverte), alors que le moteur implémente la règle S4 `_octroi_postérieur` (un OCTROI postérieur à un RETRAIT l'emporte). Les deux réponses peuvent donc différer pour un compte portant un retrait ancien puis un octroi récent. | `test_menu_rbac_mes_acces.py::PermissionsEffectivesTests::test_10_projection_plus_stricte_que_le_moteur_sur_un_retrait_leve` (et `test_09_derogation_retrait_a_la_priorite`) | **Aucune correction** : la projection est *plus fermée* que le moteur (fail-closed) et n'alimente que l'affichage du menu ; le moteur reste l'autorité de décision. Écart documenté, à trancher au LOT 5 (aligner la projection sur S4, additif) si le commanditaire le souhaite. |

---

## 6. Couverture de la suite

| Suite | Tests | État |
|---|---|---|
| `habilitations` (module complet, U1–U5 + LOT 1–3 + **LOT 4**) | **374** (2 ignorés : déclencheurs PostgreSQL) | **OK** (~240 s) |
| — dont `test_lot4_refus_croises.py` | **51** | OK |
| — dont `test_lot4_e2e_scenario.py` | **9** | OK |
| `authentication` (caractérisation U0 + LOT 2 + socle/capacités/throttles) | **207** | **OK** (92 s) |
| **Suite backend complète** (20 apps) | **1 556** | 4 erreurs d'environnement (manifeste `staticfiles` absent) → **OK après `collectstatic`** ; 5 ignorés (dont déclencheurs PostgreSQL) — 525 s |

Rejeu :

```bash
cd backend
./.venv/bin/python manage.py collectstatic --noinput                      # préalable à la suite complète (L4-05)
./.venv/bin/python manage.py test habilitations -v 1                      # 374 tests (~240 s)
./.venv/bin/python manage.py test habilitations.tests.test_lot4_refus_croises -v 2   # 51
./.venv/bin/python manage.py test habilitations.tests.test_lot4_e2e_scenario -v 2    #  9
./.venv/bin/python manage.py test authentication -v 1                     # 207 tests
./.venv/bin/python manage.py test -v 1                                    # 1 556 tests (~525 s)
```

Environnement de mesure : Python 3.11, Django 5.1.4, SQLite (`USE_SQLITE=1`),
bac à sable sans PostgreSQL ni Redis. Les tests de déclencheurs d'immuabilité du
journal sont **ignorés** dans cet environnement et doivent être rejoués sous
PostgreSQL en intégration.

---

## 7. Constat global

**Le bornage des droits est vérifié et tient** : aucun des accès croisés du
prompt §34 n'est accordé (enseignant ↔ enseignant, chef ↔ chef, étudiant ↔
étudiant, agent scolarité ↔ administration des rôles, administrateur SI ↔ actes
métier sensibles), les refus sont motivés par des **codes stables**, journalisés
et produits **uniquement** en mode APPLICATION ; en mode OFF ou avec le défaut
livré, le dispositif est strictement inerte. La chaîne d'administration de bout
en bout (création → rôles → organisation → périmètre → connexion → projection →
accès → modification → recalcul → audit) fonctionne et laisse une piste
d'audit **intègre**.

**Le dispositif n'est pas encore branché sur les vues métier** : `ExigePermission`
n'est posée sur aucune vue (0 usage), conformément à la règle « observation
avant refus ». L'autorisation réellement appliquée reste le dispositif legacy
(`ROLE_POLICY` + classes DRF), inchangé.

**Un préalable technique unique** conditionne le branchement : la résolution des
cibles objet (**L4-01**), correctif additif d'une ligne, plus les résolveurs
hiérarchiques (J2-4).

---

## 8. Plan de remédiation (LOT 5) — propositions, aucune exécution sans feu vert

| Ordre | Action | Type | Prérequis |
|---|---|---|---|
| 1 | Exposer `content_type_id` dans `_decrire_perimetre` + tests de non-régression (L4-01) | additif, 1 ligne | — |
| 2 | Rendre `_resoudre_cible` tolérant aux cibles dict (L4-04) | additif | — |
| 3 | Résolveurs hiérarchiques Direction→Département→Service, Formation→Parcours→Groupe→ECUE, injectables par contexte (J2-4) | additif | 1 |
| 4 | Sélecteur de périmètre complet dans l'assistant de création/modification (L4-02) | additif (UI + API) | 3 |
| 5 | Atelier J2 : arbitrer J2-1, J2-2, J2-3 et le type `DEPARTEMENT` | décision humaine | — |
| 6 | Rattachement additif des comptes legacy à un profil CURP (`CORRESPONDANCE_LEGACY`) | additif | 5 |
| 7 | Mode OBSERVATION mesuré sur les vues réelles, synthèse des écarts | mesure | 6 |
| 8 | Branchement `ExigePermission` vue par vue, puis APPLICATION progressive avec repli immédiat | bascule | 7 |
| 9 | Émission de l'événement `CONNEXION` au journal d'habilitation (L4-03) | additif | arbitrage |
| 10 | Rejeu complet sous PostgreSQL (déclencheurs d'immuabilité, baseline référentiels — L4-05) | environnement | — |

---

## 9. Traçabilité de cet audit

| Élément | Emplacement |
|---|---|
| Tests de refus croisés (§34) | `backend/habilitations/tests/test_lot4_refus_croises.py` |
| Tests de bout en bout (§35) | `backend/habilitations/tests/test_lot4_e2e_scenario.py` |
| Socle de fixtures partagé | `backend/habilitations/tests/_u5_fixtures.py` |
| Architecture consolidée | `docs/architecture/IAM.md` |
| Règles de droits consolidées | `docs/security/RBAC.md` |
| Guide d'exploitation | `docs/administration/utilisateurs.md` |
| Audit de phase 0 (antérieur) | `docs/audits/2026-09-14-audit-module-utilisateurs.md` |
| Plan du chantier | `docs/curp/05-architecture-completion-module-utilisateurs.md` |
| Notes de conception | `docs/curp/00-…05-*.md`, `docs/curp/U1…U6-note-conception.md` |

---

## 10. LOT 6 — Barre latérale réorganisée, pilotée par les droits (2026-09-14)

La navigation a été reconstruite sur le modèle en 15 sections fourni par le
commanditaire (Tableau de bord → Audit & Traçabilité). Principe directeur :
**une seule source de vérité** (`frontend/src/menu/arborescence.js`) dont sont
dérivés à la fois la barre latérale (`components/layout/Sidebar.jsx`) et les
routes des écrans génériques (`menu/routesGeneriques.jsx` →
`pages/EcranGenerique.jsx` + `components/generique/*`). Aucun chemin, aucun
droit n'est dupliqué dans un composant.

### 10.1 Modèle de droits (hybride, arbitré avec le commanditaire)

| Compte | Source de la décision d'affichage |
|---|---|
| **Gouverné** (profil CURP + attributions) | `GET /api/habilitations/mes-acces/ → permissions_effectives` (codes `module.ressource.action`) ; une entrée déclarant des codes CURP est évaluée **uniquement** sur eux |
| **Non gouverné** | capacités projetées `GET /api/auth/capabilities/` (`peut(user, module, action)`), repli statique `utils/roles.js` avant chargement |
| Entrée **sans volet CURP** (écrans purement legacy, console CURP) | toujours le volet legacy, quel que soit le compte : personne ne perd d'accès du fait de la réorganisation |

Entrées non autorisées : **masquées** (choix commanditaire) ; une section sans
aucune entrée autorisée disparaît. Une URL saisie à la main vers une entrée
masquée affiche un refus explicite avec les droits requis
(`EcranGenerique`), sans jamais accorder quoi que ce soit (règle S3) : chaque
vue DRF conserve ses `permission_classes`.

### 10.2 Alignement menu ↔ garde serveur (console CURP)

Les endpoints de la console (`/api/habilitations/comptes*`,
`…/organisation/*`, `…/journal*`) sont gardés par `ExigeDrapeauAdmin` :
drapeau `flag.curp_ui_admin` **ouvert** *et* trio d'administration
(`ADMIN`, `CPFAE_ADMIN`, `CHEF_CPFAE_ADMIN`). Cette garde **ne consulte aucune
permission CURP**. Les 17 entrées du menu ouvrant la console ne déclarent donc
**aucun volet `curp`** et exigent la capacité projetée
`habilitations_admin.gerer`, qui reproduit exactement la garde (même drapeau,
même trio — `authentication.capabilities._peut_gerer_console_curp`). Un volet
`curp` y ferait apparaître l'entrée pour un compte gouverné qui recevrait un
403. Un test d'invariant verrouille cette règle
(`menu/arborescence.test.js` → « alignement menu ↔ garde serveur »).

**Verrou kill-switch côté affichage.** La projection des capacités accorde
*toutes* les actions à un super-utilisateur (contrat LOT 2, test
`test_superutilisateur_obtient_toutes_les_actions`), alors que la garde serveur
applique le drapeau **même au super-utilisateur**. Sans verrou, un
super-utilisateur verrait donc des entrées que le serveur refuse tant que le
drapeau est fermé — exactement le symptôme observé en recette (écran
« Intégrité de la chaîne » en 403). Les entrées marquées `console: true`
exigent donc en plus `flag.curp_ui_admin === true` tel que renvoyé par
`GET /api/parametres/flags/` (évalué par le serveur pour le compte courant) :
drapeau fermé ou inconnu → entrée masquée. L'affichage reste ainsi plus fermé
que le serveur, jamais l'inverse (règle S3). Le contrat backend LOT 2 n'est
**pas** modifié.

Corollaire d'exploitation : drapeau fermé (défaut, kill-switch), les entrées
de console sont masquées pour tout le monde ; pour ouvrir la console en
recette, activer `flag.curp_ui_admin` (type booléen, modifiable par le trio)
via l'écran Paramètres ou l'admin Django `Parametres` — jamais en durcissant
le code.

### 10.3 Fixtures de contrat et régénération

Trois fixtures générées depuis le backend verrouillent les références croisées
du menu (`frontend/src/menu/__fixtures__/`) :

| Fixture | Contenu | Garde-fou |
|---|---|---|
| `catalogue-curp.json` | 1 155 codes `module.ressource.action` (table `habilitations_permissionmetier`) | aucun code CURP **inventé** dans l'arborescence (un code faux masquerait l'entrée en silence) |
| `catalogue-capacites.json` | 13 modules / 25 actions de `CAPACITES_DESCRIPTEURS` | aucun couple legacy inexistant |
| `catalogue-endpoints.json` | 486 motifs d'URL issus du résolveur Django | aucun `endpoint` de descripteur pointant vers un 404 |

Régénération (lecture seule côté backend) :

```bash
cd backend && USE_SQLITE=1 .venv/bin/python ../arena/genere-catalogues-menu.py
```

### 10.4 Couverture ajoutée par le LOT 6

| Suite | Tests | Objet |
|---|---|---|
| `habilitations.tests.test_menu_rbac_mes_acces` (backend) | **14** | `mes-acces` : 401 anonyme, abstention (compte non gouverné, attribution révoquée/expirée, dérogation non signée), codes des rôles actifs, priorité RETRAIT, additivité des clés, identité avec le service et l'écran admin |
| `menu/autorisation.test.js` | 29 | résolution de source, filtrage, fermeture par défaut, non-mutation |
| `menu/arborescence.test.js` | 59 | couverture du modèle 15 sections, contrat de droits (CURP + legacy + console), intégrité des descripteurs, non-régression des chemins historiques |
| `menu/ecrans.test.js` | 11 | validité des endpoints/chemins/documents contre le catalogue d'URL |
| `menu/routesGeneriques.test.jsx` | 7 | dérivation des routes, rendu de bout en bout, visiteur non authentifié |
| `components/layout/Sidebar.test.jsx` | 20 | source CURP/legacy, masquage, sections vides, persistance, pied de barre |
| `components/generique/EcranRessource.test.jsx` | 22 | liste, colonnes auto, filtres, actions (confirmation, téléchargement, navigation), détail, 403/500 |
| `pages/EcranGenerique.test.jsx` | 7 | résolution, garde d'URL directe, variantes documents/indicateurs |

Suite frontend complète après LOT 6 : **80 fichiers, 1 697 tests, OK**.

---

## 11. Suivi LOT 5 (2026-09-15) — statut des écarts

Le LOT 5 (U8, bascule CURP) a été exécuté sur feu vert du commanditaire
(« relance le lot 5 »). Tout est **additif et réversible** ; le défaut livré
(OBSERVATION) n'a pas changé et la bascule applicative reste progressive.

| ID | Devenu | Comment |
|---|---|---|
| **L4-01** | ✅ **corrigé** | `moteur._decrire_perimetre` expose `content_type_id` **et** `id` ; la voie objet (`has_object_permission`) résout le contrôle 9 par rapprochement exact. La classe témoin `CouvertureObjetEcartTests` a été **inversée** en verrou de non-régression (5 tests, dont refus tracé sur objet hors périmètre et chaîne d'audit intacte). |
| **L4-02** | ✅ **livré** | La console accepte `perimetres: [{type, object_id}]` sur chaque ligne d'attribution (`comptes_admin._perimetre_borne`, types bornables du registre `resolveurs.TYPES_OBJETS`, objet vérifié — sinon 400 `PERIMETRE_INCONNU`, atomicité préservée). L'alliage `perimetres_secretariats` reste accepté. UI : sélecteurs « Directions couvertes / Départements couverts » dans l'assistant de création et l'écran de modification (`PerimetresOrganisation.jsx`) ; les types pédagogiques restent posables par l'API (l'admin Django demeure le repli universel). |
| **L4-03** | ✅ **livré** | La connexion réussie d'un compte gouverné émet `CONNEXION` au journal d'habilitation (`connexion_sure.finaliser_connexion`, best effort — une panne du journal ne bloque jamais la connexion). La double piste est **assumée** : `presences.AuditLog` reste l'horodatage métier, le journal CURP la trace de gouvernance. |
| **L4-04** | ✅ **corrigé** | `journalisation._resoudre_cible` accepte la cible dict du contrat d'API (journalisée avec son type/object_id/référence, sans ContentType). |
| **J2-4** | ✅ **traité** | Type de périmètre `DEPARTEMENT` ajouté (migration `habilitations/0013`, alter de choices seul) + **résolveurs hiérarchiques livrés** (`services/resolveurs.py`) : Direction ⊃ Département ⊃ Service RH ; Formation ⊃ Parcours ⊃ Groupe/Niveau/SITE ; maquette ⊃ UE ⊃ ECUE ; ETUDIANT ⊃ ses inscriptions. Le moteur les applique par défaut sur la voie objet et accepte toujours un résolveur injecté (prioritaire). `DIRECTION` reste le périmètre par défaut des rôles de département (aucune réécriture des octrois existants). |
| **J2-1 / J2-2 / J2-3** | ⏸ atelier | inchangés par le LOT 5 — aucun contenu de matrice n'a été modifié unilatéralement ; les refus croisés restent verrouillés par les tests du LOT 4. |
| **L4-07** | ⏸ maintenu | La projection `permissions_effectives()` garde sa priorité au RETRAIT (fail-closed, affichage seulement). Alignement sur S4 non engagé : le moteur reste l'autorité ; à trancher si un usage d'affichage l'exige. |

**Étape 1 de la bascule (IAM §10)** : commande `rattacher_comptes_legacy`
— simulation par défaut, `--appliquer` pour écrire ; profil + attributions
non sensibles issues de la table A6 ; **jamais d'auto-validation d'un rôle
sensible** (ADMIN/ADMIN_SYSTEME restent à traiter dans la console, double
signature) ; idempotent (un second passage ne fait rien) ; `--role` filtre
le lot. Rejeu démo mesuré : 8 comptes posés, rejoués → 0.

**Étapes 2-3** : le mode OBSERVATION (défaut des réglages,
`HABILITATIONS_OBSERVATION=true`) est mesuré sur les vues réelles ; deux
vues pilotes portent `ExigePermission` — `GET /api/scolarite/inscriptions/`
(`scolarite.inscription_administrative.consulter`) et
`POST /api/finances-etudiantes/paiements/<id>/confirmer/`
(`finances_etud.paiement.valider`). En OBSERVATION leurs réponses sont
inchangées (écarts comptés via `observations_habilitations`) ; seul le mode
APPLICATION rendrait les refus effectifs, et la progression reste vue par
vue avec repli immédiat par drapeau (kill-switch verrouillé LOT 6).

**Couverture de tests ajoutée** : `habilitations.tests.test_lot5_bascule`
(**26** tests : résolveurs hiérarchiques, console périmètres, cible dict
journalisée, `CONNEXION`, commande de rattachement, vues pilotes inertes en
observation) + inversion de `CouvertureObjetEcartTests`. Suite
`habilitations` après LOT 5 : **415 tests OK** (2 ignorés, déclencheurs
PostgreSQL) ; `authentication` + `scolarite` + `finances_etudiantes` :
**467 tests OK** ; frontend `pages/habilitations` : **63 tests OK** dont 6
nouveaux sur le sélecteur de bornage.
