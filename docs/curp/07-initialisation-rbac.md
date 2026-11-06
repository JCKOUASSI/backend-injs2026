# Initialisation contrôlée du socle RBAC — préparation de mise en service

**Statut du document** : mécanisme **prêt, testé et documenté — non activé**.
Aucune écriture n'a été réalisée dans une base de production ; aucune
attribution de rôle n'a été posée sur un compte existant.

**Périmètre** : projet `backend-injs2026`, modules `authentication` (autorité
d'authentification) et `habilitations` (autorisations métier).

---

## 0. Mise à jour du 6 novembre 2026 (consolidation) — À LIRE EN PREMIER

Trois changements rendent obsolètes certaines parties des sections 2 à 8 :

1. **Commande unique.** `previsualiser_initialisation_rbac` et
   `initialiser_rbac` sont **fusionnés et supprimés** ; il reste une seule
   commande :
   `backend/habilitations/management/commands/rbac_initialisation.py`
   (prévisualisation par défaut, `--apply` pour écrire). Aucune commande du
   projet `backend/` : `backend/management/` n'existe pas et `backend` n'est pas
   une application installée — une commande placée là ne serait pas découverte.
2. **Plus aucun rôle déduit de `User.role`.** La table `CORRESPONDANCE_LEGACY`
   n'est plus utilisée pour proposer des attributions. L'initialisation crée
   **des comptes RBAC et rien d'autre** : zéro attribution, zéro proposition,
   zéro modification d'utilisateur Django. Les totaux « 12 attributions /
   6 propositions / 34 rôles bloqués » du §4 sont donc **périmés** : le plan ne
   comporte plus que des créations de comptes. Tout droit reste posé par la
   voie normale (demande d'accès + validation), jamais par import.
3. **Catalogue réconcilié.** `catalogue_roles.py` contient **81 rôles
   (35 A1 + 46 cibles J2), 22 sensibles**, identiques à la base. L'écart 35/81
   et 11/22 est expliqué pièce par pièce dans
   [`08-reconciliation-catalogue-roles.md`](08-reconciliation-catalogue-roles.md).

Le reste du document reste valide pour l'inventaire (§1), les anomalies
produit (§5, A1-A7) et la réversibilité (§7).

## 1. État des lieux du code RBAC existant

### 1.1 Modèles (`backend/habilitations/models/`)

| Modèle | Rôle | Fichier |
|---|---|---|
| `CompteUtilisateur` | Extension **OneToOne** de `authentication.User` (`related_name='profil_habilitation'`) — aucun second modèle d'utilisateur | `compte.py` |
| `Personne` | Identité physique, matricule, détection de doublons | `personne.py` |
| `RoleMetier` | Rôle métier : `niveau_defaut`, `perimetre_defaut`, `sensible`, `module_requis`, `incompatible_avec`, `permissions` (M2M) | `role.py` |
| `PermissionMetier` | Permission atomique `module.ressource.action`, **avec `portee_maximale`** (plafond) | `permission.py` |
| `Perimetre` | Portée polymorphique (`ContentType` + `object_id`), types globaux `INJS_ENTIER` / `PROPRE_COMPTE` | `perimetre.py` |
| `AttributionRole` | Compte ↔ rôle, statut (`PROPOSEE`/`ACTIVE`/`SUSPENDUE`/`EXPIREE`/`REVOQUEE`), `motif` **obligatoire**, `valide_par` (seconde signature), périmètres M2M. Contrainte d'unicité `(compte, role)` en statut `ACTIVE` | `attribution.py` |
| `PermissionAttribuee` | Dérogation OCTROI / RETRAIT | `attribution.py` |
| `DelegationHabilitation`, `DemandeAcces`, `PropositionProvisionnement` | Délégation, demandes, file de provisionnement | `delegation.py`, `demande_acces.py`, `cycle_vie.py` |
| `JournalHabilitation` | Journal **immuable et chaîné** (numéro + empreinte SHA-256) | `journal.py` |
| `PolitiqueSecurite` | Politique singleton (MFA, seuils, inactivité) | `politique.py` |

### 1.2 Services (`backend/habilitations/services/`)

* `moteur.py` — `est_autorise(utilisateur, code_permission, *, canal, cible, contexte, date)` : le mécanisme d'évaluation à utiliser (jamais un contrôle maison).
* `comptes_admin.py` — `creer_compte`, `modifier_compte`, `_appliquer_roles` (pose `valide_par` **uniquement** si `sensible_valide`), `changer_statut`, `simuler_import`.
* `demandes_acces.py` — `creer_demande`, `appliquer_transition` : **séparation demandeur / approbateur** (refus si l'acteur est le demandeur).
* `machine_etats.py` — transitions légales du cycle de vie.
* `journalisation.py` — `journaliser(...)` : écritures chaînées.
* `drapeaux.py` — lecture des drapeaux (un drapeau absent = **éteint**, sans passe-droit superutilisateur).
* `validations.py`, `politique.py`, `impact.py`, `projection.py`, `expirations.py`, `versions_roles.py`, `provisionnement/`.

### 1.3 Commandes existantes (aucune n'a été modifiée)

| Commande | Objet |
|---|---|
| `init_habilitations_injs` | Crée la politique de sécurité singleton (idempotent, `--dry-run`) |
| `charger_referentiel_injs` | Charge rôles A1 / permissions A3 / matrice A2 |
| `rattacher_comptes_legacy` | Rattachement additif des comptes legacy (simulation par défaut, `--appliquer`) |
| `habilitations_diag` | Diagnostic en lecture seule |
| `generer_matrice_habilitations`, `observations_habilitations`, `expirer_habilitations`, `detecter_inactivite`, `provisionnement_scanner`, `verifier_chaine_habilitations` | Matrice, observation, cycle de vie |

### 1.4 API et drapeaux

* conservées telles quelles : `/api/auth/users/`, `/api/auth/capabilities/`, `/api/habilitations/...` (`mes-acces/`, `evaluer/`, `roles/`, `permissions/`, `comptes/`, `demandes/`, cycle de vie,workflow, versions de rôles) ;
* garde des endpoints d'administration : `ExigeDrapeauAdmin` = droit d'administration **et** `flag.curp_ui_admin` ;
* drapeaux du socle : `flag.lot01_socle_referentiels_rbac` (présent, **fermé**), `flag.curp_module_utilisateurs` (**absent** — voir §5).

### 1.5 État mesuré du référentiel (base du bac à sable, 6 novembre 2026)

| Indicateur | Référence annoncée | Mesuré |
|---|---|---|
| Rôles métier | 81 | **81** (81 actifs) |
| Permissions métier | 1 157 | **1 157** |
| Associations rôle ↔ permission | 10 453 | **10 453** |
| Rôles sensibles | 22 | **22** |
| Comptes RBAC | 0 | **0** |
| Attributions / périmètres / délégations | absents | **0 / 0 / 0** |
| Utilisateurs Django | — | 34, dont **2 superutilisateurs** |

---

## 2. Schéma des opérations d'initialisation

```
┌─ 1. PRÉVISUALISATION (lecture seule, aucune transaction d'écriture) ────────┐
│  rbac_initialisation                                                        │
│  · utilisateurs Django SANS profil CURP (profil_habilitation__isnull)       │
│  · superutilisateurs EXCLUS du plan (--inclure-superutilisateurs)           │
│  · AUCUN rôle déduit de User.role (règle : comptes seuls, zéro attribution) │
│  · comparaison du catalogue fichier ↔ base (contrôle de divergence)         │
│  · analyse de périmètre par rôle (déclaré vs plafond des permissions)       │
│  · détection des doublons d'identité, des incohérences de compte            │
│  · sortie : rapport lisible + JSON (--json)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │ validation explicite du rapport
                                    ▼
┌─ 2. INITIALISATION (--appliquer, désactivée par défaut) ────────────────────┐
│  rbac_initialisation --apply                                                │
│  · refus (CommandError) si l'un des deux drapeaux est absent ou fermé       │
│  · par utilisateur, dans UNE transaction :                                  │
│      get_or_create(CompteUtilisateur)          → journal COMPTE_CREE        │
│      AUCUNE attribution, AUCUNE proposition, AUCUN périmètre               │
│  · aucun compte existant modifié, aucun utilisateur Django touché           │
│  · aucune réimportation du catalogue, aucune permission modifiée            │
│  · idempotent : un second passage ne crée plus aucun compte                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Garde-fous applicables à toute exécution**

1. aucune écriture sans `--appliquer` **et** les deux drapeaux ;
2. **aucune attribution automatique**, et en particulier aucun rôle déduit du
   champ historique `User.role` ;
3. aucun élargissement de périmètre ; un périmètre local n'est jamais inventé ;
4. superutilisateurs : profil seul (sur demande explicite), **aucune attribution** ;
5. aucune suppression, révocation ou modification d'un objet existant ;
6. `authentication.User` n'est **jamais** modifié (authentification = autorité) ;
7. le journal enregistre chaque écriture avec l'origine `INITIALISATION_RBAC`.

---

## 3. Commandes livrées

### 3.1 Prévisualisation (sans écriture)

```bash
python manage.py rbac_initialisation                        # rapport (lecture seule)
python manage.py rbac_initialisation --json rapport.json     # + JSON
python manage.py rbac_initialisation --username agent1       # un compte
python manage.py rbac_initialisation --inclure-superutilisateurs
```

### 3.2 Initialisation (idempotente, inactive par défaut)

```bash
python manage.py rbac_initialisation --apply                         # écrit si drapeaux ouverts
python manage.py rbac_initialisation --apply --username agent1
python manage.py rbac_initialisation --apply --ignorer-drapeaux      # recette / bac à sable
```

Sans drapeaux ouverts, `--apply` échoue par `CommandError` **sans rien écrire**.

Emplacement définitif : `backend/habilitations/management/commands/rbac_initialisation.py`.
`backend/management/` n'existe pas et `backend` ne figure pas dans `INSTALLED_APPS` : une
commande projet n'y serait pas découverte. Les 17 applications déclarent chacune leurs
commandes dans leur propre arborescence ; `habilitations` est bien installée
(`config/settings.py`).

---

## 4. Matrice des rôles et périmètres (rapport du 6 novembre 2026)

| Rôle legacy | Rôles CURP visés (table A6) | Périmètre déclaré | Décision |
|---|---|---|---|
| `ADMIN` | `ADMIN_SYSTEME` (sensible) | INJS_ENTIER | **PROPOSÉ** (seconde signature) |
| `DIRECTION` | `DIRECTION_GENERALE` (sensible) | INJS_ENTIER | **PROPOSÉ** |
| `CHEF_INJS_ADMIN` | `ADMIN_SYSTEME`, `DIRECTION_ETUDES` (sensibles) | INJS_ENTIER | **PROPOSÉS** |
| `FINANCE` | `GESTIONNAIRE_FINANCES_ETUD`, `GESTIONNAIRE_VACATIONS` (sensibles) | INJS_ENTIER | **PROPOSÉS** |
| `ARCHIVE` | `ARCHIVISTE` | INJS_ENTIER | **ACTIF** |
| `AUDITEUR` | `ETUDIANT` | PROPRE_COMPTE | **ACTIF** |
| `SECRETARIAT` | `AGENT_INSCRIPTIONS`, `AGENT_ADMISSIONS`, `GESTIONNAIRE_ETUDIANTS` | SECRETARIAT | **BLOQUÉ** — secrétariat à désigner |
| `CHEF_SECRETARIAT` | `SCOLARITE` + les trois ci-dessus | SECRETARIAT | **BLOQUÉ** |
| `INJS_ADMIN` | `SCOLARITE`, `GESTIONNAIRE_COURS` | SECRETARIAT / FORMATION | **BLOQUÉ** |
| `ENCADRANT`, `FORMATEUR` | `ENSEIGNANT`, `GESTIONNAIRE_GROUPES` | MODULE_ECUE / FORMATION | **BLOQUÉ** |
| `SUPERVISEUR` | `RESPONSABLE_PEDAGOGIQUE` | FORMATION | **BLOQUÉ** |

**Totaux du rapport du 6 novembre 2026 (avant la règle « aucun rôle déduit de
`User.role` » — voir §0, point 2. Rapport de remplacement :
[`inventaires/rbac-initialisation-previsualisation.json`](inventaires/rbac-initialisation-previsualisation.json))** :
32 comptes à traiter · 32 profils à créer · **12 attributions** (11 `ETUDIANT` + 1 `ARCHIVISTE`) · **6 propositions sensibles** · **34 rôles bloqués** par un périmètre local (8 `SECRETARIAT`, 3 `FORMATION`, 2 `MODULE_ECUE`) · aucun rôle A6 absent du catalogue · aucun utilisateur sans correspondance.

Rapport complet (périmé sur les attributions) : [`inventaires/initialisation-rbac-previsualisation.json`](inventaires/initialisation-rbac-previsualisation.json).

---

## 5. Anomalies et ambiguïtés — à arbitrer avant toute écriture

| # | Constat | Conséquence | Recommandation |
|---|---|---|---|
| **A1** | **`flag.curp_module_utilisateurs` n'existe ni dans le code ni en base** | le garde-fou demandé ne peut pas être respecté tel quel : la commande le traite comme **fermé** et refuse l'écriture | créer le drapeau (`Parametre`, clé `flag.`, type bool) ou confirmer son abandon |
| **A2** | **100 % des permissions actives ont `portee_maximale = INJS_ENTIER`** | le plafond des permissions ne restreint aucun rôle : la seule borne effective est le **périmètre de l'attribution** | arbitrer : revoir les `portee_maximale` du catalogue, ou assumer que le périmètre d'attribution est la seule borne |
| **A3** | **34 rôles bloqués** faute d'objet métier désignable (secrétariat / formation / module) | 32 comptes sur 34 ne recevraient qu'un profil, sans droit | fournir la correspondance « utilisateur → secrétariat / formation / ECUE », ou créer les attributions via la console |
| **A4** | **2 superutilisateurs** dans la base du bac à sable (la référence en annonce 1) | écart d'inventaire à lever avant initialisation | confirmer le nombre et le rôle exact du compte superutilisateur à préserver |
| **A5** | **Deux chemins de rattachement coexistent** : `rattacher_comptes_legacy` (historique, sans périmètre ni drapeau) et `initialiser_rbac` (supervisé) | risque de doublon fonctionnel | trancher : retenir `initialiser_rbac` comme voie supervisée et réserver l'autre au rattrapage |
| **A6** | L'ordre de largueur des périmètres (`ORDRE_PERIMETRE`) est une **hypothèse** — le modèle ne porte aucune relation d'inclusion | il ne sert qu'à détecter un périmètre déclaré trop large | valider l'ordre avec le métier |
| **A7** | La base de production `injs_lmd_prod_20261026` **n'est pas joignable** depuis l'environnement de travail | les mesures du §1.5 sont celles du bac à sable (catalogue identique) ; l'inventaire des comptes de production reste à faire | exécuter `previsualiser_initialisation_rbac` sur la production et joindre le rapport |

Aucune de ces anomalies n'a été corrigée par supposition : elles sont **signalées**.

---

## 6. Tests automatisés

Fichier : `backend/habilitations/tests/test_initialisation_rbac.py` — **40 tests** répartis en **15 catégories**, tous au vert (`Ran 40 tests — OK`).

| Exigence | Couverture |
|---|---|
| Rapport de prévisualisation | `RapportPreviewTests` (zéro écriture ; séparation utilisateur / compte / attribution ; **concordance catalogue fichier ↔ base**) |

**Non-régression** : groupe `habilitations` — **520 tests, OK** (dont les 40 nouveaux).

| Exigence | Couverture |
|---|---|
| Création idempotente d'un compte | `CreationIdempotenteTests` (2 passages → 1 compte, 1 attribution) |
| Liaison utilisateur ↔ compte | `LiaisonCompteTests` (`user.profil_habilitation`, niveau, motif) |
| Préservation du superutilisateur | `SuperutilisateurTests` (exclu du plan ; inclus → profil **sans attribution** ; compte Django intact) |
| Absence d'attribution automatique non autorisée | `AbsenceAttributionAutoTests` (sensible jamais `ACTIVE` ; périmètre local jamais créé) |
| Conflits de périmètre | `ConflitPerimetreTests` (local bloqué, plafond plus étroit → repli, **aucun élargissement**) |
| Rôles sensibles | `RoleSensibleTests` (motif, `valide_par` nul, journal `PROPOSITION_DEPOSEE`) |
| Double validation | `DoubleValidationTests` (demandeur ≠ approbateur ; l'initialisation ne pose jamais la seconde signature) |
| Révocations | `RevocationTests` (attribution révoquée non ressuscitée ; active jamais révoquée) |
| Journalisation | `JournalisationTests` (numéros croissants et uniques, empreintes, types d'événements) |
| Contrôles d'accès API | `ControleAccesApiTests` (endpoints protégés en anonyme ; `/api/auth/*` toujours servis) |
| Drapeaux | `DrapeauxTests` (refus d'écriture sans drapeaux ; `CommandError` sans rien écrire) |

---

## 7. Réversibilité

Aucune commande livrée ne supprime, ne révoque ni ne modifie une donnée existante. En cas d'initialisation jugée inappropriée, le retour arrière s'appuie sur la trace :

1. repérer les écritures d'origine `INITIALISATION_RBAC` dans le journal (`JournalHabilitation.nouvelle_valeur`) ;
2. passer les attributions concernées au statut `REVOQUEE` **via la console** (jamais par SQL direct) ;
3. désactiver le profil (`SUSPENDU`/`DESACTIVE`) depuis la console ;
4. conserver une sauvegarde exploitable **avant** toute exécution de `--appliquer` (préalable posé par le comité de validation).

---

## 8. Fichiers livrés

| Fichier | Nature |
|---|---|
| `backend/habilitations/services/initialisation_rbac.py` | Service : plan (pur) + application idempotente + analyse de périmètre |
| `backend/habilitations/management/commands/rbac_initialisation.py` | **Commande unique** : prévisualisation par défaut (aucune écriture possible) + `--apply` soumis aux drapeaux |
| `backend/habilitations/tests/test_initialisation_rbac.py` | 40 tests (15 catégories) |
| `docs/curp/08-reconciliation-catalogue-roles.md` | Réconciliation 81/35 rôles, 22/11 sensibles |
| `docs/curp/inventaires/rbac-initialisation-previsualisation.json` | Rapport de prévisualisation **après** la règle « aucun rôle déduit » (6 novembre 2026) |
| `docs/curp/07-initialisation-rbac.md` | Ce document |
| `docs/curp/inventaires/initialisation-rbac-previsualisation.json` | Rapport de prévisualisation (6 novembre 2026) |

Commandes `previsualiser_initialisation_rbac` et `initialiser_rbac` **supprimées** (fusion). Aucune référence SYGEP-CPFAE n'a été ajoutée. Aucune donnée de production modifiée, aucun `DROP`/`RESET`/`FLUSH`, aucune désactivation de rôle.
