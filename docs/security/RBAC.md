# RBAC — Rôles, niveaux, permissions et périmètres (INJS-LMD)

> **Document de consolidation (LOT 4 du module Utilisateurs)** · Date : 2026-09-14
> **Périmètre** : le modèle de contrôle d'accès **cible** porté par l'application
> `habilitations` (chantier CURP), et sa cohabitation avec le dispositif legacy.
> **Sources de vérité** : `backend/habilitations/referentiel/` (catalogues),
> `backend/habilitations/services/moteur.py` (décision),
> [`docs/curp/04-moteur-autorisation.md`](../curp/04-moteur-autorisation.md),
> [`docs/architecture/IAM.md`](../architecture/IAM.md).
> **Chiffres mesurés sur le dépôt** le 2026-09-14 (commandes de rejeu en §11).

---

## 1. Principes

1. **Le backend est la seule autorité** (règle S3). L'interface masque, elle
   n'accorde rien ; chaque vue conserve ses `permission_classes`.
2. **Fermeture par défaut** (*fail closed*) : toute incertitude (permission
   inconnue, aucun octroi valide, cible hors périmètre) produit un refus motivé.
3. **Non-gouvernance = abstention**, pas refus : un `User` sans profil
   `CompteUtilisateur` reste soumis au seul dispositif legacy (bascule
   progressive U8).
4. **Additif et réversible** (R2) : rôles et cases de matrice ajoutés par
   données (migration idempotente), jamais par suppression ; retour arrière =
   désactivation (`desactiver_referentiel()`).
5. **Observation avant refus** (R3) : le mode APPLICATION n'est pas le défaut
   livré ; aucun refus ne peut atteindre une vue métier avant le LOT 5.
6. **Élargissement explicite** (S4) : un retrait ne se lève que par un octroi
   postérieur **et** doublement signé.
7. **Traçabilité** : tout geste sensible porte un motif et finit au journal
   chaîné ; les refus appliqués sont tracés `ACCES_REFUSE`.
8. **Séparation des tâches** : couples de rôles incompatibles, seconde
   signature pour les rôles sensibles, double validation pour les permissions
   critiques.

---

## 2. Niveaux d'accès N0 → N4

| Niveau | Portée décisionnelle | Verbes typiques |
|---|---|---|
| **N0** | Consultation très limitée (périmètre propre compte) | `consulter` |
| **N1** | Lecture et production de documents | `consulter`, `imprimer`, `exporter`, `generer` |
| **N2** | Saisie et traitement courant | `creer`, `modifier`, `soumettre`, `saisir`, `editer`, `deposer`, `ouvrir`, `calculer`, `deplacer`, `remplacer` |
| **N3** | Validation et décision | `valider`, `rejeter`, `publier`, `annuler`, `signer`, `verrouiller`, `instruire`, `decider`, `certifier`, `cloturer`, `resoudre` |
| **N4** | Administration et actes sensibles | `supprimer`, `archiver`, `administrer`, `configurer`, `forcer` |

La table complète est `NIVEAU_VERBE` dans
`backend/habilitations/referentiel/catalogue_modules.py` : **c'est elle qui
transforme la matrice par niveaux (A2) en permissions atomiques**. Un niveau de
module ≥ niveau du verbe ⇒ la permission est accordée au rôle.

Dérogation unique : `NIVEAU_PERMISSION_SURCHARGE = {'exports.export_sensible.generer': 4}`
(un export sensible reste réservé à N4 quel que soit le niveau du module).

Répartition des **81 rôles** par niveau par défaut : N4 = 8, N3 = 31, N2 = 36,
N1 = 5, N0 = 1.

---

## 3. Permissions atomiques

- **Convention de code** : `<module>.<ressource>.<action>`
  (ex. `evaluations.note.valider`, `jurys.pv.signer`).
- **Volume** : **1 155 permissions** sur **20 modules** du catalogue
  (`administration`, `candidatures`, `scolarite`, `pedagogie`, `enseignants`,
  `evaluations`, `jurys`, `diplomation`, `finances_etud`, `finances_form`,
  `stages`, `rh`, `patrimoine`, `edt`, `presences`, `administrations`,
  `statistiques`, `exports`, `parametres`, `referentiels`).
- **Verbes** : 13 canoniques + verbes métier = **31 actions** au modèle
  (`PermissionMetier.Action`). Un joker `<ressource>.*` du recueil est expansé
  en les 13 verbes canoniques au chargement.
- **Qualificateurs portés par chaque permission** :
  - `criticite` : NORMALE ou **CRITIQUE** (**15 permissions critiques**,
    liste `PERMISSIONS_CRITIQUES`) → `necessite_double_validation=True`,
    motif obligatoire, journalisation renforcée ;
  - `necessite_motif` : les 15 critiques + les créations d'octrois
    (`PERMISSIONS_AVEC_MOTIF`) ;
  - `portee_maximale` : borne la largeur d'un périmètre de dérogation ;
  - `journalisee` : tout sauf `consulter`.

Les 15 permissions critiques :

```
administration.role.creer            administration.role.modifier
administration.attribution.valider   administration.compte.modifier
evaluations.note.verrouiller         jurys.pv.signer
jurys.resultat.publier               diplomation.diplome.valider
diplomation.diplome.revoquer         finances_etud.paiement.valider
finances_etud.remboursement.valider  presences.emargement.forcer
edt.emploi_du_temps.publier          parametres.parametre.administrer
exports.export_sensible.generer
```

**Qualité du référentiel après chargement** : 0 rôle sans permission,
0 permission orpheline, 0 rôle indisponible, rechargement idempotent
(vérifié par `habilitations/tests/test_referentiel*.py` et
`test_organisation_roles_cibles.py`).

---

## 4. Catalogue des rôles (81)

| Origine | Volume | Statut des données |
|---|---|---|
| Annexe **A1** du recueil | **35** rôles (32 internes + 3 destinataires du service : `ETUDIANT`, `CANDIDAT`, `CONSULTATION`) | validés |
| **Cibles J2** du prompt module Utilisateurs (2026-09) | **46** rôles (ordre ≥ 360) | **provisoires** — niveaux à valider en atelier |

Chaque ligne du catalogue porte : `code`, `libellé`, `domaine`, `niveau_defaut`,
`perimetre_defaut`, `module_requis` (application Django conditionnante),
`sensible`, `canal_impose`, `ordre`, `description`.

- **Domaines** (14) : ADMINISTRATION_GENERALE (12), TECHNIQUE (10), FINANCE (9),
  ADMINISTRATION (7), CANDIDATURES (7), PEDAGOGIE (5), EVALUATIONS (5),
  SCOLARITE (4), ENSEIGNANTS (4), DIPLOMATION (4), RH (4), PATRIMOINE (4),
  STAGES (3), DESTINATAIRES (3).
- **Rôles sensibles** (22) — seconde signature d'attribution exigée, MFA exigé
  par le contrôle 6 du moteur :

```
ADMIN_SYSTEME            DIRECTION_GENERALE      DIRECTION_ETUDES
RESPONSABLE_CONCOURS     RESPONSABLE_JURY        RESPONSABLE_GRADUATION
RESPONSABLE_DIPLOMATION  GESTIONNAIRE_FINANCES_ETUD  VALIDATEUR_FINANCIER
GESTIONNAIRE_VACATIONS   GESTIONNAIRE_RH         SIGNATAIRE
VALIDATEUR_DIPLOMES      BOURSE_MANAGER          RESPONSABLE_FINANCES
CONTROLEUR_FINANCIER     PAIE_MANAGER            SYSADMIN
NETWORK_ADMIN            DB_ADMIN                SECURITY_ADMIN
API_MANAGER
```

- **Périmètres par défaut** : INJS_ENTIER (52 rôles), FORMATION (11),
  PROPRE_COMPTE (6), SECRETARIAT (4), MODULE_ECUE (3), SITE (2), SERVICE (1),
  DIRECTION (1 : `CHEF_DEPARTEMENT`), PARCOURS (1).
- **Canaux imposés** : `ENSEIGNANT` et `ETUDIANT` → MOBILE (le web est refusé
  par le moteur avec le motif `CANAL_IMPOSE_PAR_ROLE`, et par le legacy pour les
  rôles `AUDITEUR`/`FORMATEUR`).

### 4.1 Aucun doublon fonctionnel

Les rôles cibles J2 **ne recréent pas** les rôles A1 équivalents ; les mappages
sont documentés dans le catalogue :

| Cible demandée | Rôle existant retenu |
|---|---|
| `SUPER_ADMIN`, `ADMIN_SI` | `ADMIN_SYSTEME` |
| `DIRECTION` | `DIRECTION_GENERALE` |
| `PEDAGOGIE_MANAGER` | `RESPONSABLE_PEDAGOGIQUE` |
| `SCOLARITE_MANAGER` | `SCOLARITE` |
| `ETUDIANT_MANAGER` | `GESTIONNAIRE_ETUDIANTS` |
| `GROUPE_MANAGER` | `GESTIONNAIRE_GROUPES` |
| `NOTE_MANAGER` | `GESTIONNAIRE_NOTES` |
| `JURY_PRESIDENT` | `RESPONSABLE_JURY` |
| `JURY_MEMBER` | `MEMBRE_JURY` |
| `STAGE_MANAGER` | `GESTIONNAIRE_STAGES` |
| `LECTEUR` | `CONSULTATION` |

### 4.2 Correspondance avec les 12 rôles legacy (annexe A6)

`CORRESPONDANCE_LEGACY` (`catalogue_matrice.py`) — appliquée aux comptes lors de
la bascule U8, jamais avant :

| Legacy | Rôles CURP |
|---|---|
| `ADMIN` | `ADMIN_SYSTEME` |
| `CHEF_CPFAE_ADMIN` | `ADMIN_SYSTEME`, `DIRECTION_ETUDES` |
| `CPFAE_ADMIN` | `SCOLARITE`, `GESTIONNAIRE_COURS` |
| `DIRECTION` | `DIRECTION_GENERALE` |
| `CHEF_SECRETARIAT` | `SCOLARITE`, `AGENT_INSCRIPTIONS`, `AGENT_ADMISSIONS`, `GESTIONNAIRE_ETUDIANTS` |
| `SECRETARIAT` | `AGENT_INSCRIPTIONS`, `AGENT_ADMISSIONS`, `GESTIONNAIRE_ETUDIANTS` |
| `FINANCE` | `GESTIONNAIRE_FINANCES_ETUD`, `GESTIONNAIRE_VACATIONS` |
| `ARCHIVE` | `ARCHIVISTE` |
| `ENCADRANT` | `ENSEIGNANT`, `GESTIONNAIRE_GROUPES` |
| `SUPERVISEUR` | `RESPONSABLE_PEDAGOGIQUE` |
| `FORMATEUR` | `ENSEIGNANT` |
| `AUDITEUR` | `ETUDIANT` |

Les 12 rôles legacy sont **figés** (DA-05) : aucun renommage, aucune suppression.

---

## 5. Matrice rôle × module

| Source | Cases | Statut |
|---|---|---|
| **A2** (recueil) | 35 lignes × 15 modules | validées |
| **Cases provisoires J2** (`NIVEAUX_EXTRA_PROVISOIRES`) | 12 rôles × 5 modules absents d'A2 (`administrations`, `finances_form`, `exports`, `parametres`, `referentiels`) | à valider en atelier |
| **Rôles cibles J2** (`NIVEAUX_ROLES_CIBLES`) | 46 rôles | à valider en atelier |
| **Règles dérivées** | `exports` = niveau `statistiques` (si ≥ N1) ; `referentiels` = N1 pour tout rôle non DESTINATAIRES | documentées, origine J2 |

**Résultat** : **10 440 liaisons rôle × permission** après chargement.
`niveaux_du_role(code, domaine)` retourne `(niveaux, origine)` où `origine`
vaut `'A2'` (case écrite au recueil) ou `'J2'` (case provisoire) : **l'origine
de chaque case est traçable**, y compris dans l'écran matrice.

Fusion : A2 → cases J2 supplémentaires → rôles cibles J2 → règles dérivées.

---

## 6. Périmètres

12 types polymorphes (`Perimetre.Type`, référence ContentType + `object_id`,
`reference_lisible` lisible), classés par largeur croissante
(`LARGEUR_PERIMETRE`, utilisée pour borner les dérogations) :

| Largeur | Type | Objet porté |
|---|---|---|
| 0 | `PROPRE_COMPTE` | global (son propre dossier) |
| 1 | `ETUDIANT` | `scolarite.DossierEtudiant` |
| 2 | `MODULE_ECUE` | module / ECUE |
| 3 | `GROUPE` | `scolarite.Groupe` |
| 4 | `NIVEAU`, `PARCOURS` | `scolarite.Niveau`, `Parcours` |
| 5 | `FORMATION` | `formations.RefFormation` |
| 6 | `SECRETARIAT`, `SITE` | `formations.Secretariat`, `RefSite` |
| 7 | `SERVICE` | `ressources_humaines.Service` |
| 8 | `DIRECTION` | `administrations.Direction` (et départements rattachés, via résolveur) |
| 9 | `INJS_ENTIER` | global |

Résolution de la **couverture d'une cible** (contrôle 9), dans l'ordre :

1. périmètre `INJS_ENTIER` → toujours couvrant ;
2. **cible au format dict** `{'type': …, 'object_id': …}` → égalité de type et
   d'identifiant (c'est le format du contrat d'API `POST evaluer/`) ;
3. **cible objet métier** → égalité ContentType + `object_id` ;
4. règle générique `SECRETARIAT` → l'objet cible porte un `secretariat_id`
   égal au périmètre ;
5. **fonction de couverture injectée** dans le contexte d'appel
   (`contexte={'couverture': f(perimetre, cible)}`) — point d'extension prévu
   pour les résolveurs hiérarchiques.

> ⚠️ **État livré (constat LOT 4, écart L4-01)** : la voie 3 ne fonctionne pas
> aujourd'hui. Les périmètres d'un octroi sont sérialisés en dicts par
> `moteur._decrire_perimetre()` **sans `content_type_id`**, si bien que la
> comparaison de type échoue toujours pour un objet métier : la décision tombe
> en `CIBLE_HORS_PERIMETRE`. Les voies 2, 4 et 5 sont opérationnelles. C'est un
> **prérequis bloquant du LOT 5** (branchement de `has_object_permission`) ;
> le correctif est additif et tient en une ligne. Preuve :
> `backend/habilitations/tests/test_lot4_refus_croises.py::CouvertureObjetEcartTests`.

Il n'existe pas de type `DEPARTEMENT` : les rôles cibles de département
(`CHEF_DEPARTEMENT`) utilisent `DIRECTION` comme périmètre par défaut (note J2).

---

## 7. Les dix contrôles du moteur (ordre contractuel)

| # | Contrôle | Motifs stables |
|---|---|---|
| 1 | Session authentifiée | `NON_AUTHENTIFIE` |
| 2 | Compte gouverné (profil CURP) | abstention (`gouverne: false`), pas un refus |
| 3 | Statut du compte | `COMPTE_INVITE`, `COMPTE_SUSPENDU`, `COMPTE_DESACTIVE`, `COMPTE_VERROUILLE`, `COMPTE_EXPIRE` |
| 4 | Expiration du compte | `COMPTE_EXPIRATION_ATTEINTE` |
| 5 | Canal (profil puis rôle) | `CANAL_NON_AUTORISE`, `CANAL_IMPOSE_PAR_ROLE` |
| 6 | MFA (politique ou rôle sensible) | `MFA_REQUIS_NON_ACTIF` |
| 7 | Octroi valide (rôle via matrice, OCTROI dérogatoire, délégation) | `PERMISSION_INCONNUE`, `AUCUNE_ATTRIBUTION_PERMETTANTE`, `MODULE_REQUIS_ABSENT`, `ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE`, `ROLES_INCOMPATIBLES`, `NIVEAU_INSUFFISANT`, `PERIMETRE_SECRETARIAT_MANQUANT`, `DEROGATION_*`, `DELEGATION_*` |
| 8 | Priorité du RETRAIT explicite | `PERMISSION_RETIREE` |
| 9 | Couverture de la cible | `CIBLE_HORS_PERIMETRE` |
| 10 | Délégation : titulaire toujours habilité | `DELEGATION_SANS_TITULAIRE_VALIDE` |

Les libellés français des motifs (`LIBELLES_MOTIFS` dans
`habilitations/services/codes.py`) font partie du **contrat d'API** : ils sont
repris tels quels par l'API REST et les journaux.

Sources d'octroi (contrôle 7) : **rôle** (attribution ACTIVE, dans ses dates,
saine), **dérogation OCTROI** (bornée ≤ `duree_max_derogation_jours` = 90 j,
dans la `portee_maximale`, signée si critique), **délégation** (bornée, signée
si critique, délégant encore titulaire **directement** — profondeur 1,
re-délégation interdite).

`CANAL_IMPOSE_PAR_ROLE` est le seul motif **non bloquant** par lui-même : il
écarte l'octroi concerné (donc un refus suit en pratique via
`AUCUNE_ATTRIBUTION_PERMETTANTE`), sans interdire un autre octroi valide sur un
canal compatible.

---

## 8. Séparation des tâches et contrepoids

### 8.1 Couples incompatibles (5, bilatéraux)

```
GESTIONNAIRE_NOTES        ↔ RESPONSABLE_JURY
AGENT_INSCRIPTIONS        ↔ GESTIONNAIRE_FINANCES_ETUD
GESTIONNAIRE_FINANCES_ETUD ↔ VALIDATEUR_FINANCIER
AGENT_CANDIDATURE         ↔ AGENT_CONTROLE_DOSSIERS
RESPONSABLE_GRADUATION    ↔ GESTIONNAIRE_NOTES
```

Effet : motif `ROLES_INCOMPATIBLES` (refus) et avertissement non bloquant dans
le différentiel de la console (`_avertissements_roles`).

### 8.2 Contrepoids appliqués

| Contrepoids | Où |
|---|---|
| **Seconde signature** d'attribution (`valide_par`) pour les 22 rôles sensibles | contrôle 7 → `ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE` |
| **Double validation** des 15 permissions critiques (dérogations, délégations) | `DEROGATION_SANS_SECONDE_SIGNATURE`, `DELEGATION_NON_SIGNEE` |
| **MFA TOTP** pour tout rôle sensible octroyant, ou les rôles listés dans `PolitiqueSecurite.roles_mfa_obligatoire` | contrôle 6 → `MFA_REQUIS_NON_ACTIF` |
| **Garde des deux administrateurs** : impossible de retirer le dernier rôle `ADMIN_SYSTEME` si le parc descend sous le seuil | `_verifier_seuil_admin()`, avertissement `SEUIL_ADMINISTRATEURS` |
| **Différentiel obligatoire** avant toute modification de droits | `DIFFERENTIEL_REQUIS` (409) |
| **Motif obligatoire** sur les gestes sensibles | `MOTIF_REQUIS` |
| **Verrouillage de compte** (5 échecs / 15 min) et révocation de sessions | LOT 2, machine à états A5 |
| **Journal chaîné** vérifiable | `verifier_chaine()`, `GET journal/integrite/` |

---

## 9. Écarts et cases à arbitrer en atelier (J2)

Ces points sont **documentés, non corrigés** : les modifier changerait des
droits, ce qui relève d'une décision humaine.

| # | Écart | État | Test de caractérisation |
|---|---|---|---|
| **J2-1** | La ligne A2 d'`ADMIN_SYSTEME` est `{module: N4}` sur les 15 modules : le rôle porte donc les actes métier critiques (`jurys.pv.signer`, `diplomation.diplome.valider`, `finances_etud.paiement.valider`) alors que sa description catalogue dit « sans intervenir sur les décisions métier ». La politique « ne pas contourner les validations métier » (prompt §17) reste à formaliser. | Contenus par : rôle **sensible** (seconde signature), MFA exigé, permissions **critiques** (double validation + motif), journalisation renforcée | `test_lot4_refus_croises.py::AdminSiTests::test_08_ecart_j2_ligne_a2_de_admin_systeme_a_arbitrer` |
| **J2-2** | `CHEF_DEPARTEMENT` (cible J2) reçoit `administration: N2` ⇒ création/modification de comptes et d'attributions **dans son périmètre**. À confirmer ou restreindre en atelier. | Lecture N1/N2 bornée par le périmètre DIRECTION | `…::ChefDepartementCroiseTests::test_07_…` |
| **J2-3** | Les rôles SI (`SUPPORT_IT` … `API_MANAGER`) portent un niveau minimal sur `parametres` : *placeholder* documenté, aucune emprise métier devinée. | Vérifié : **0 acte métier sensible**, **0 module métier** | `…::AdminSiTests::test_01/02` |
| **J2-4** | Pas de type de périmètre `DEPARTEMENT` ; `DIRECTION` sert de périmètre par défaut aux rôles de département. | Couverture hiérarchique à industrialiser (résolveurs, LOT 5) | `…::ChefDepartementCroiseTests::test_05_sonde_hierarchique…` |
| **L4-01** | Cibles « objet métier » non résolues par le contrôle 9 (voir §6). | **Prérequis bloquant du LOT 5** ; correctif additif d'une ligne proposé | `…::CouvertureObjetEcartTests` |
| **L4-02** | La console ne pose que des périmètres **secrétariat** (`perimetres_secretariats`) ; les autres périmètres passent par l'admin Django. | À ouvrir avec le LOT 5 | `test_lot4_e2e_scenario.py` (étape 4, posée par ORM) |
| **L4-03** | Une connexion réussie alimente `last_login`/`derniere_connexion` et trace `presences.AuditLog` (USER_LOGIN), mais n'émet pas d'événement `CONNEXION` au journal d'habilitation (type prévu, non émis). | À arbitrer (piste d'audit double) | `test_lot4_e2e_scenario.py::test_04_…` |

---

## 10. Exploitation sécurisée

| Action | Moyen |
|---|---|
| Ouvrir/fermer la console CURP | drapeau `flag.curp_ui_admin` (kill-switch immédiat, sans passe-droit super-utilisateur) |
| Mesurer avant d'appliquer | `HABILITATIONS_OBSERVATION=true` (défaut) + `GET /api/habilitations/observations/synthese/` + commande `observations_habilitations` |
| Appliquer les refus | `HABILITATIONS_APPLICATION=true` (**LOT 5 uniquement, feu vert explicite**) |
| Revenir en arrière | repasser la variable à `false` : le dispositif redevient inerte, sans redéploiement |
| Vérifier l'intégrité de la piste d'audit | `python manage.py verifier_chaine_habilitations`, `GET /api/habilitations/journal/integrite/` |
| Diagnostiquer un compte | `python manage.py habilitations_diag`, `GET /api/habilitations/mes-acces/`, `POST /api/habilitations/evaluer/` |
| Expirer / suspendre automatiquement | `expirer_habilitations`, `detecter_inactivite` (drapeaux U5) |

Drapeaux du module (tous livrés **éteints**) : `flag.curp_ui_admin`,
`flag.curp_verrouillage_connexion`, `flag.curp_mfa_active`,
`flag.curp_mfa_obligatoire_sensibles`, `flag.curp_provisionnement_auto`,
`flag.curp_import_masse`, `flag.curp_suspension_inactivite`,
`flag.curp_expiration_auto` et les 7 déclencheurs
`flag.curp_declencheur_*`.

---

## 11. Preuves et rejeu

```bash
cd backend

# Référentiel : volume, anomalies (0 rôle sans permission, 0 orpheline)
python manage.py shell -c "from habilitations.referentiel.chargement import charger_referentiel as c; print(c(dry_run=True).as_dict())"
python manage.py charger_referentiel_injs          # idempotent, réversible

# LOT 4 — refus croisés §34 (mode APPLICATION sur base de test) et E2E §35
python manage.py test habilitations.tests.test_lot4_refus_croises -v 2
python manage.py test habilitations.tests.test_lot4_e2e_scenario -v 2

# Suite complète du module
python manage.py test habilitations authentication -v 1
```

| Suite | Volume | Rôle |
|---|---|---|
| `habilitations/tests/test_lot4_refus_croises.py` | **51 tests** | §34 : enseignant A≠B, chef de département A≠B, étudiant A≠B, agent scolarité ≠ admin rôles, admin SI ≠ actes métier sensibles ; + écart de couverture objet ; + garde-fous (abstention, OFF) |
| `habilitations/tests/test_lot4_e2e_scenario.py` | **9 tests** | §35 : création → rôles → organisation → périmètre → connexion → menu → accès autorisé/interdit → modification → recalcul → audit |
| `habilitations/tests/` (U1–U5, LOT 1–3) | 314 tests | modèle, moteur, référentiel, cycle de vie, console, imports, délégations, journal, organisation, rôles cibles |
| `authentication/` (caractérisation U0 `tests_caracterisation/`, LOT 2 `test_lot2_securite.py`, socle, capacités, throttles) | **207 tests** | état legacy de référence (rôles, groupes, canaux, permissions effectives, cloisonnement secrétariats), verrouillage, MFA TOTP, horodatages, drapeaux éteints = no-op |

Détail des constats et de la méthode d'audit :
[`docs/audit/permissions.md`](../audit/permissions.md).
