# Administration des utilisateurs — guide d'exploitation (INJS-LMD)

> **Document de consolidation (LOT 4 du module Utilisateurs)** · Date : 2026-09-14
> **Public** : administrateurs du SI, direction des études, scolarité, RH.
> **Références** : [`docs/architecture/IAM.md`](../architecture/IAM.md) (architecture),
> [`docs/security/RBAC.md`](../security/RBAC.md) (règles de droits),
> [`docs/audit/permissions.md`](../audit/permissions.md) (audit et écarts),
> [`docs/curp/U3-note-conception.md`](../curp/U3-note-conception.md) et
> [`docs/curp/U5-note-conception.md`](../curp/U5-note-conception.md) (consoles).
>
> **Deux consoles cohabitent** : l'écran historique « Utilisateurs »
> (`/users`, 12 rôles legacy) et la **console CURP** (`/administration/comptes`,
> 81 rôles). Rien n'a été supprimé ni renommé.

---

## 1. Avant de commencer

### 1.1 Drapeaux (kill-switch, sans redéploiement)

| Drapeau | Défaut | Effet |
|---|---|---|
| `flag.curp_ui_admin` | **éteint** | Ouvre la console CURP (`/administration/comptes`). Éteint = 403 pour tous, y compris un super-utilisateur. |
| `flag.curp_verrouillage_connexion` | éteint | Verrouillage après 5 échecs (15 min), révocation des sessions. |
| `flag.curp_mfa_active` | éteint | Étape TOTP pour les comptes `mfa_actif`. |
| `flag.curp_mfa_obligatoire_sensibles` | éteint | MFA obligatoire pour les 22 rôles sensibles + désactivation refusée (409). |
| `flag.curp_provisionnement_auto` | éteint | Scan automatique de la file de provisionnement. |
| `flag.curp_import_masse` | éteint | Ouverture des imports en masse. |
| `flag.curp_suspension_inactivite` | éteint | Suspension automatique des comptes inactifs (politique `duree_inactivite_jours`). |
| `flag.curp_expiration_auto` | éteint | Expiration automatique des attributions arrivées à terme. |
| `flag.curp_declencheur_*` (7) | éteints | Déclencheurs planifiés U5. |

Gestion des drapeaux : écran `Paramètres` (`flag.*`), table `parametres.Parametre`
ou API. **Un drapeau fermé = comportement strictement d'avant** (no-op vérifié
par tests).

Variables d'environnement du moteur (`backend/.env`) :

```
HABILITATIONS_OBSERVATION=true     # défaut livré : mesure sans refuser
HABILITATIONS_APPLICATION=false    # défaut livré : aucun refus appliqué
```

### 1.2 Chargement initial (une seule fois par environnement)

```bash
cd backend
python manage.py migrate
python manage.py charger_referentiel_injs          # idempotent, 81 rôles / 1 155 permissions
python manage.py inventaire_habilitation --comptes # état de référence
python manage.py verifier_chaine_habilitations     # piste d'audit intègre
```

`charger_referentiel_injs` est **réversible** par
`desactiver_referentiel()` : aucun `DELETE`, les objets sont désactivés.

---

## 2. Créer un compte

### 2.1 Par l'assistant (voie nominale)

1. **Identité** — personne existante (recherche par matricule/nom/courriel) ou
   nouvelle personne ; le matricule `PERS-AAAA-NNNNN` est généré automatiquement
   (`generer_matricule_personne`).
2. **Compte** — identifiant (unicité vérifiée → erreur `IDENTIFIANT_EXISTANT`,
   HTTP 409), courriel, canal (WEB / MOBILE / LES_DEUX), mot de passe initial,
   « doit changer le mot de passe à la première connexion » (recommandé).
3. **Rôles** — choix parmi les 81 rôles (recherche, filtre par domaine) ; le
   niveau effectif proposé est celui du catalogue, ajustable **à la baisse**
   (jamais au-dessus du niveau du rôle sans motif) ; date de début/fin ;
   périmètre.
4. **Organisation** — direction(s), département(s), service(s)/secrétariat(s)
   de rattachement (LOT 1/LOT 3).
5. **Validation** — récapitulatif, **motif obligatoire**, puis création.

Règles appliquées automatiquement :

- **seconde signature** (`valide_par`) exigée pour les 22 rôles sensibles ;
- **incompatibilités** signalées (5 couples, ex. `GESTIONNAIRE_NOTES` ↔
  `RESPONSABLE_JURY`) — avertissement, la création reste possible si justifiée ;
- **garde des deux administrateurs** : impossible de faire descendre le parc
  sous le seuil d'administrateurs système (`SEUIL_ADMINISTRATEURS`) ;
- **transaction atomique** : une erreur en cours de création (rôle inconnu,
  périmètre invalide…) annule **tout** — aucun compte fantôme n'est laissé ;
- le compte est créé en statut **INVITE** (activation ensuite) ou **ACTIF**
  selon le choix, avec un **motif** journalisé.

### 2.2 Par API

```bash
# Créer
curl -X POST /api/habilitations/comptes/ \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"personne": {...}, "compte": {...}, "roles": [...], "organisation": {...}, "motif": "…"}'

# Simuler avant de modifier (obligatoire)
curl -X POST /api/habilitations/comptes/42/simuler-modification/ -d '{"roles": [...]}'
# → {gagnées: [...], perdues: [...], conservées: [...], avertissements: [...]}
```

### 2.3 Rattachement d'un compte existant

Un `User` legacy peut être **rattaché** (et non recréé) à une personne + un
profil CURP. La correspondance des 12 rôles legacy vers les rôles CURP est
documentée dans `CORRESPONDANCE_LEGACY`
([RBAC §4.2](../security/RBAC.md#42-correspondance-avec-les-12-rôles-legacy-annexe-a6))
et ne s'applique **qu'à la bascule U8**, sur feu vert.

---

## 3. Modifier les droits d'un compte

1. Ouvrir la fiche (`/administration/comptes/:id`) → **Modifier**.
2. Ajuster rôles, niveaux, dates, périmètres, organisation.
3. **Lancer la simulation** : le panneau de différentiel affiche
   `gagnées` / `perdues` / `conservées` / `avertissements`.
4. **Saisir un motif** (obligatoire dès qu'un droit change) → enregistrer.

Refus attendus (contrats d'API) :

| Situation | Réponse |
|---|---|
| Rôles modifiés sans différentiel accepté | `409 DIFFERENTIEL_REQUIS` |
| Rôles modifiés sans motif | `400 MOTIF_REQUIS` |
| Identifiant déjà pris | `409 IDENTIFIANT_EXISTANT` |
| Rôle inconnu / désactivé | `ErreurConsole('ROLE_INCONNU')` → `400`, **rollback complet** |
| Compte non gouverné / inexistant | `404` |

Chaque modification écrit au journal : `ROLE_ATTRIBUE`, `ROLE_REVOQUE`,
`PERMISSION_OCTROYEE`, `PERMISSION_RETIREE`, `COMPTE_MODIFIE` — avec
différentiel, motif, auteur, IP et agent utilisateur.

---

## 4. Cycle de vie du compte (machine à états A5)

```
                 activer                suspendre / desactiver / verrouiller
   INVITE ─────────────────► ACTIF ─────────────────────────────────────────► SUSPENDU
     │                         ▲  │                                            DESACTIVE
     │ expirer                 │  │ expirer                                    VERROUILLE
     ▼                         │  ▼
   EXPIRE        deverrouiller ┘  EXPIRE
                 (depuis VERROUILLE)
```

| Transition | Depuis | Vers | `is_active` après | Événement journal |
|---|---|---|---|---|
| `activer` | INVITE, SUSPENDU, VERROUILLE, DESACTIVE | ACTIF | oui | `COMPTE_ACTIVE` |
| `suspendre` | ACTIF | SUSPENDU | non | `COMPTE_SUSPENDU` |
| `desactiver` | ACTIF | DESACTIVE | non | `COMPTE_DESACTIVE` |
| `verrouiller` | ACTIF | VERROUILLE | non | `COMPTE_VERROUILLE` |
| `deverrouiller` | VERROUILLE | ACTIF | oui | `COMPTE_DEVERROUILLE` |
| `expirer` | INVITE, ACTIF | EXPIRE | non | `COMPTE_EXPIRE` |

Toute autre transition est **illégale** (`TransitionIllegale` → `400`) : par
exemple `suspendre` un compte déjà suspendu, ou `deverrouiller` un compte
désactivé.

Effets immédiats d'une suspension/désactivation (vérifiés par les tests LOT 4) :

- `is_active=False`, **sessions révoquées**, jetons inutilisables ;
- le moteur refuse avec `COMPTE_SUSPENDU` / `COMPTE_DESACTIVE` ;
- la connexion renvoie `403 COMPTE_VERROUILLE`-style (statut dédié) ;
- le verrouillage automatique (LOT 2) remet `echecs_consecutifs` à zéro et
  alimente `date_verrouillage` (nécessaire au calcul du délai).

`POST /api/habilitations/comptes/{id}/statut/` avec `{"transition": "suspendre",
"motif": "…"}`.

---

## 5. MFA (TOTP)

| Étape | Endpoint | Note |
|---|---|---|
| Armer | `POST /api/auth/mfa/setup/` | renvoie secret + URI `otpauth://` |
| Confirmer | `POST /api/auth/mfa/confirm/` | active après un code valide |
| Vérifier à la connexion | `POST /api/auth/mfa/verify/` | avec le `mfa_token` (5 min) reçu au login |
| Désactiver | `POST /api/auth/mfa/disable/` | code exigé pour soi-même ; **409** si MFA obligatoire (rôle sensible) |

Implémentation locale RFC 6238 (`habilitations/services/totp.py`) : aucun appel
réseau, aucune dépendance externe.

---

## 6. Organisation institutionnelle (LOT 1 / LOT 3)

Écran `/administration/comptes/organisation` :

- **Directions** : création (`code` + `libellé` uniques), modification,
  suppression (refusée si des départements sont rattachés — FK PROTECT) ;
- **Départements** : rattachés à une direction (nullable), `code` + `libellé`
  uniques ;
- **Services** : hiérarchisés sous un département (FK nullable) ;
- **Rattachements de comptes** : `…/organisation/<type>/<pk>/comptes/` liste les
  comptes rattachés à une entité et permet d'ajouter/retirer des affiliations
  (`CompteUtilisateur.departements` / `.services`).

Ces affiliations sont **administratives** ; les droits effectifs passent par les
**périmètres** des attributions (voir RBAC §6). Aujourd'hui la console ne pose
que des périmètres de type `SECRETARIAT` (écart **L4-02**) : un périmètre
`DIRECTION`/`SERVICE`/`GROUPE` se pose via l'admin Django
(`/admin/habilitations/attributionrole/`) en attendant le LOT 5.

---

## 7. Dérogations et délégations

### 7.1 Dérogations (octroi ou retrait ciblé)

`POST /api/habilitations/derogations/` :

- sens **OCTROI** ou **RETRAIT**, une seule permission, bornée par dates,
  périmètre dans la `portee_maximale` de la permission ;
- **motif obligatoire** ;
- durée maximale = `PolitiqueSecurite.duree_max_derogation_jours` (90 j) →
  `DEROGATION_DUREE_EXCESSIVE` ;
- **seconde signature obligatoire** pour les 15 permissions critiques →
  `DEROGATION_SANS_SECONDE_SIGNATURE` ;
- révocable à tout moment (`…/derogations/{id}/revoquer/`).

Un RETRAIT ne peut être levé que par un OCTROI postérieur **et** doublement
signé (règle S4).

### 7.2 Délégations

`POST /api/habilitations/delegations/` : rôles et/ou permissions délégués,
périmètres, dates, motif. Contraintes :

- **profondeur 1** : un délégataire ne peut pas re-déléguer ;
- le délégant doit rester **directement titulaire** pendant toute la durée
  (`DELEGATION_SANS_TITULAIRE_VALIDE`) ;
- seconde signature si une permission critique est déléguée ;
- terminaison anticipée (`…/delegations/{id}/terminer/`), activation, action.

---

## 8. Imports en masse (U5, drapeau `flag.curp_import_masse`)

1. **Simulation** : `POST /api/habilitations/comptes/import-simuler/` (ou
   `…/comptes/imports/` avec `dry_run`) → lignes acceptées, rejetées, motifs.
2. **Exécution** : création d'une référence d'import ; chaque ligne est
   journalisée.
3. **Annulation** : `POST /api/habilitations/comptes/imports/{ref}/annuler/` →
   retour arrière **complet** (jamais de suppression physique : statuts et
   attributions révoqués).

Aucun import ne contourne les contrôles : identifiants en double, rôles
inconnus, incompatibilités et seuil d'administrateurs sont refusés ligne à
ligne.

---

## 9. File de provisionnement (U5)

`GET /api/habilitations/propositions/` liste les comptes à traiter
(nouveaux arrivants détectés, dossiers sans compte, échéances). Actions :
`approuver` / `rejeter` (motif obligatoire), et scan automatique par
`provisionnement_scanner` (drapeau `flag.curp_provisionnement_auto`).

---

## 10. Surveillance et audit quotidien

### 10.1 Piste d'audit

| Besoin | Moyen |
|---|---|
| Qui a fait quoi ? | Écran `/administration/comptes/journal` (filtres : compte, type d'événement, période, auteur) ou `GET /api/habilitations/journal/` |
| Intégrité de la piste | `GET /api/habilitations/journal/integrite/` ou `python manage.py verifier_chaine_habilitations` → `[]` si intègre |
| Refus appliqués | Événement `ACCES_REFUSE` (motif, code, cible, IP) — uniquement en mode APPLICATION |
| Fiche d'un compte | `GET /api/habilitations/comptes/{id}/` inclut son historique |
| Droits effectifs | Écran « Permissions effectives » de la fiche, ou `GET /api/habilitations/comptes/{id}/effective-permissions/` (rôles + octrois − retraits, avec origine) |

37 types d'événements couvrent : comptes, rôles, permissions, dérogations,
délégations, politique, statuts, MFA, connexions refusées, organisation,
imports, provisionnement, accès refusés.

### 10.2 Mode observation (avant toute application)

```bash
python manage.py observations_habilitations            # synthèse des écarts
GET /api/habilitations/observations/synthese/          # idem par API
POST /api/habilitations/observations/remettre-a-zero/  # remise à zéro des compteurs
```

### 10.3 Diagnostic d'un compte

```bash
python manage.py habilitations_diag                    # état complet
GET /api/habilitations/mes-acces/                      # côté utilisateur connecté
POST /api/habilitations/evaluer/  {"code_permission": "…", "cible": {"type": "…", "object_id": 1}}
```

`evaluer/` renvoie la **décision motivée** : `autorise`, `gouverne`, `mode`,
`motifs` (codes + libellés), `octrois` (origine rôle / dérogation / délégation).
Évaluer **autrui** est réservé aux administrateurs et journalisé.

### 10.4 Tâches planifiées

| Commande | Rôle |
|---|---|
| `expirer_habilitations` | attributions arrivées à `date_fin` → EXPIREE |
| `detecter_inactivite` | préavis + propositions de suspension au-delà de `inactivite_suspension_jours` (jamais de suspension silencieuse) |
| `provisionnement_scanner` | alimente la file de propositions |
| `verifier_chaine_habilitations` | contrôle d'intégrité |
| `sync_role_groups` | resynchronise les groupes `ROLE_*` legacy |

Exécutées par le service `cron` / `worker` (voir `scripts/start_dev.sh`).

---

## 11. Politique de sécurité (singleton `PolitiqueSecurite`)

| Paramètre (`PolitiqueSecurite`, singleton) | Défaut | Effet |
|---|---|---|
| `longueur_min_mot_de_passe` | 12 | + `exige_majuscule` / `exige_minuscule` / `exige_chiffre` / `exige_caractere_special` (tous vrais) |
| `duree_validite_mot_de_passe_jours` | 0 | 0 = pas d'expiration forcée |
| `historique_mots_de_passe` | 5 | réutilisation refusée sur les N derniers |
| `nombre_echecs_avant_verrouillage` | 5 | seuil de verrouillage (LOT 2) |
| `duree_verrouillage_minutes` | 15 | déverrouillage automatique à échéance |
| `inactivite_session_minutes` | 30 | inactivité de session |
| `inactivite_suspension_jours` | 180 | au-delà : **préavis** puis **proposition de suspension en file humaine** — jamais de suspension silencieuse (`detecter_inactivite`) |
| `duree_max_derogation_jours` | 90 | borne la durée d'une dérogation |
| `periodicite_revue_jours` | 180 | campagne de revue des habilitations |
| `preavis_suspension_jours` / `delai_grace_fin_relation_jours` | 15 / 7 | préavis et délai de grâce |
| `plafond_quotidien_propositions` | 50 | borne la file de provisionnement |
| `echeance_notification_jours` | 7 | notifications d'échéance |
| `roles_mfa_obligatoire` | `[]` | complète la liste des 22 rôles sensibles du catalogue |
| `canaux_par_role` | `{}` | surcharge ponctuelle du canal imposé par rôle |

Constante de code (non paramétrable) : `SEUIL_ADMINISTRATEURS = 2` dans
`habilitations/services/comptes_admin.py` — la **garde des deux
administrateurs** refuse (ou avertit en simulation) toute opération qui ferait
descendre le parc d'administrateurs système actifs sous ce seuil.

Toute modification de politique est journalisée (`POLITIQUE_MODIFIEE`) avec
motif, auteur et valeurs avant/après.

---

## 12. Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| 403 sur toute la console | `flag.curp_ui_admin` éteint | Activer le drapeau |
| 403 `COMPTE_SUSPENDU` après suspension | Comportement attendu | `activer` (transition A5) + motif |
| 403 `MFA_REQUIRED` sans possibilité de désactiver | Rôle sensible + `flag.curp_mfa_obligatoire_sensibles` | Réinitialiser le MFA par un administrateur |
| 403 `COMPTE_VERROUILLE` | 5 échecs consécutifs | Attendre 15 min ou `deverrouiller` |
| Refus `CIBLE_HORS_PERIMETRE` sur un objet métier | L4-01 corrigé au LOT 5 : vérifier que l'objet est bien rattaché au périmètre posé (le résolveur suit Direction ⊃ Département ⊃ Service et Formation ⊃ Parcours ⊃ Groupe/ECUE) | Voir [audit §11](../audit/permissions.md) ; en observation, aucun impact utilisateur |
| Compte legacy sans droits CURP | Profil non gouverné | `python manage.py rattacher_comptes_legacy` (simulation), puis `--appliquer` — rattachement additif et idempotent (LOT 5) |
| `IDENTIFIANT_EXISTANT` | Unicité des identifiants | Choisir un autre identifiant (aucun compte fantôme créé) |

---

## 13. LOT 5 (U8) — bascule CURP : livré et reste

Exécuté le 2026-09-15 sur feu vert ; tout est additif et réversible, le défaut
livré reste OBSERVATION (aucun impact production). Détail des preuves :
[audit §11](../audit/permissions.md).

**Livré par le LOT 5** :

- **couverture des cibles « objet métier »** (L4-01) : `moteur._decrire_perimetre`
  expose `content_type_id` et `id` ; la voie DRF `has_object_permission` décide
  désormais au contrôle 9, refus à l'identique journalisé ;
- **résolveurs hiérarchiques** (`habilitations/services/resolveurs.py`) :
  Direction ⊃ Département ⊃ Service RH ; Formation ⊃ Parcours ⊃ Groupe
  (coupes Niveau/Site) ; maquette ⊃ UE ⊃ ECUE ; un périmètre `ETUDIANT` couvre
  les inscriptions du dossier. Nouveau type de périmètre `DEPARTEMENT`
  (migration `habilitations/0013`) ;
- **périmètres non secrétariat depuis la console** (L4-02) : chaque ligne
  d'attribution accepte `perimetres: [{type, object_id}]` (objets vérifiés,
  400 `PERIMETRE_INCONNU` sinon, aucun compte fantôme) ; `perimetres_secretariats`
  reste accepté. L'assistant de création et l'écran de modification portent les
  sélecteurs « Directions couvertes / Départements couverts » ; les types
  pédagogiques se posent par l'API (l'admin Django reste le repli universel) ;
- **événement `CONNEXION`** (L4-03) : chaque connexion réussie d'un compte
  gouverné est tracée au journal d'habilitation (best effort, jamais bloquante ;
  la double piste avec `presences.AuditLog` est assumée) ;
- **cible dict journalisée** (L4-04) ;
- **rattachement des comptes legacy** : `manage.py rattacher_comptes_legacy`
  (simulation par défaut, `--appliquer` pour écrire, `--role` pour filtrer) —
  table A6, attributions non sensibles posées actives, rôles sensibles en
  proposition (double signature en console, jamais d'auto-élévation),
  idempotent ;
- **vues pilotes** branchées en OBSERVATION : liste des inscriptions
  (`GET /api/scolarite/inscriptions/`, code `scolarite.inscription_administrative.consulter`)
  et confirmation de paiement (`POST /api/finances-etudiantes/paiements/<id>/confirmer/`,
  code `finances_etud.paiement.valider`). Leurs réponses ne changent pas ;
  les compteurs se lisent via `manage.py observations_habilitations`
  (ou `--remettre-a-zero` avant une campagne).

**Ce qui reste ouvert** :

- arbitrage des cases **J2** de la matrice (RBAC §9 — atelier commanditaire,
  aucun changement unilatéral engagé) ;
- branchement des vues restantes, vue par vue, puis mode **APPLICATION**
  progressif par drapeau (`HABILITATIONS_APPLICATION`, kill-switch console
  verrouillé au LOT 6) ;
- retrait du legacy (écarts E1/E2/E7) après stabilisation — hors périmètre ;
- alignement éventuel de la projection `permissions_effectives()` sur la règle
  S4 (écart L4-07 : la projection reste volontairement plus fermée, fail-closed).
