# IAM — Identité, comptes et contrôle d'accès (INJS-LMD)

> **Document de consolidation (LOT 4 du module Utilisateurs)** · Date : 2026-09-14
> **Sources de vérité** : le code (`backend/authentication/`, `backend/habilitations/`),
> l'audit de phase 0 ([`docs/audits/2026-09-14-audit-module-utilisateurs.md`](../audits/2026-09-14-audit-module-utilisateurs.md)),
> le chantier CURP ([`docs/curp/`](../curp/)) et la note d'architecture
> [`docs/curp/05-architecture-completion-module-utilisateurs.md`](../curp/05-architecture-completion-module-utilisateurs.md).
> **Documents frères** : [`docs/security/RBAC.md`](../security/RBAC.md) (rôles, niveaux,
> matrice), [`docs/administration/utilisateurs.md`](../administration/utilisateurs.md)
> (exploitation), [`docs/audit/permissions.md`](../audit/permissions.md) (audit et écarts).
>
> Ce document **consolide** l'existant : il ne crée pas de troisième dispositif.
> Les chiffres cités sont mesurés sur le dépôt (voir §12).

---

## 1. Vue d'ensemble

L'INJS-LMD dispose de **deux couches d'identité superposées**, volontairement
cohabitantes jusqu'à la bascule U8 :

| Couche | Portée | État |
|---|---|---|
| **Legacy** — `authentication.User` (12 rôles), groupes Django `ROLE_*`, `ROLE_POLICY`, 10 permissions Django custom, classes DRF (`IsDFRC`, `IsEncadrant`, `IsSecretariat`…) | Authentification **et** autorisation réellement appliquées sur les vues métier | **En production** |
| **CURP** — app `habilitations` : `Personne`, `CompteUtilisateur`, `RoleMetier` (81), `PermissionMetier` (1 155), `Perimetre` (12 types), `AttributionRole`, `PermissionAttribuee`, `DelegationHabilitation`, journal immuable chaîné, moteur `est_autorise()` | Autorisation cible, complète en données, écrans et API | **Construite, alimentée, écranée — moteur en observation ; aucun refus appliqué sur une vue métier** |

```
              ┌──────────────────────────── IDENTITÉ ────────────────────────────┐
              │  authentication.User (AbstractUser)                              │
              │   role legacy (12) · groupes ROLE_* · permissions Django (10)    │
              │   matricule · secretariat FK · must_change_password · last_login │
              │            │ 1:1                                                 │
              │  habilitations.CompteUtilisateur ── FK ── habilitations.Personne │
              │   statut (6) · canal (WEB/MOBILE/LES_DEUX) · MFA · verrouillage  │
              │   departements M2M · services M2M  (organisation, LOT 1)         │
              └──────────────────────────────────────────────────────────────────┘
                        │                                      │
        ┌───────────────▼──────────────┐        ┌──────────────▼─────────────────┐
        │  AUTORISATION EN VIGUEUR     │        │  AUTORISATION CIBLE (CURP)     │
        │  ROLE_POLICY + classes DRF   │        │  AttributionRole × RoleMetier  │
        │  capabilities (projection)   │        │  × PermissionMetier (matrice)  │
        │  ProtectedRoute / peut()     │        │  Perimetre · dérogations ·     │
        │  (frontend = masque)         │        │  délégations · moteur à 10     │
        └──────────────────────────────┘        │  contrôles · ExigePermission   │
                                                └────────────────────────────────┘
                        │                                      │
                        └──────────────► JOURNAL ◄─────────────┘
                       presences.AuditLog (générique) + habilitations.JournalHabilitation
                       (append-only, chaîné SHA-256, 37 types d'événements)
```

**Règle structurante (S3)** : le backend est la **seule** autorité. Le frontend
projette des capacités pour l'affichage (`GET /api/auth/capabilities/`) et masque
des entrées de menu, mais n'accorde jamais rien ; chaque vue conserve ses
`permission_classes`.

---

## 2. Chaîne d'identité (modèles)

| Modèle | Application | Rôle dans la chaîne |
|---|---|---|
| `User` | `authentication` | Compte de connexion (AbstractUser). `role` legacy (12 valeurs, figées par DA-05), `matricule`, `telephone`, `organisation`, `grade`, `secretariat` (FK 1:1 historique), `must_change_password`, `last_login`. |
| `Personne` | `habilitations` | Identité physique : `matricule` unique (`PERS-AAAA-NNNNN`), état civil, `photo` (ImageField), liens nullables vers `Participant`/`Formateur`/`Agent`/`DossierEtudiant`. |
| `CompteUtilisateur` | `habilitations` | Profil d'habilitation 1:1 de `User` : `statut` (INVITE/ACTIF/SUSPENDU/DESACTIVE/VERROUILLE/EXPIRE), `canal`, `date_expiration`, `date_verrouillage`, `echecs_consecutifs`, `mfa_actif`, `mfa_secret`, `derniere_connexion`, `departements`/`services` (M2M LOT 1). |
| `AttributionRole` | `habilitations` | Lien compte ↔ rôle ↔ niveau effectif (N0–N4) ↔ périmètres, avec `date_debut`/`date_fin`, `motif`, `attribue_par`, `valide_par` (seconde signature), `statut` (PROPOSEE/ACTIVE/SUSPENDUE/EXPIREE/REVOQUEE). |
| `PermissionAttribuee` | `habilitations` | Dérogation : sens OCTROI ou RETRAIT, bornée, motivée, signée si critique. |
| `DelegationHabilitation` | `habilitations` | Délégation bornée (rôles et/ou permissions, périmètres), profondeur 1. |
| `Perimetre` | `habilitations` | Portée polymorphe (ContentType + object_id) : 12 types, `reference_lisible` lisible. |
| `PolitiqueSecurite` | `habilitations` | Singleton : mots de passe, verrouillage, inactivité, dérogations, `roles_mfa_obligatoire`. |
| `JournalHabilitation` | `habilitations` | Journal append-only chaîné (empreinte SHA-256 de la ligne précédente). |
| `Direction`, `Departement` | `administrations` | Organisation hiérarchique créée au LOT 1 (`Service` existant rattaché par `departement` FK nullable). |
| `AuditLog` | `presences` | Journal générique transverse (connexions, gestes métier, exports). |

**Aucun second modèle utilisateur** n'existe : le compte de connexion reste
`authentication.User` (décision U1). Un compte sans profil CURP est dit
**non gouverné** : le moteur s'abstient et l'ancien dispositif décide seul.

---

## 3. Authentification

### 3.1 Flux de connexion web

```
POST /api/auth/login/  {username, password[, device_id]}
  ├─ throttle LoginRateThrottle (20/min)                       → 429
  ├─ compte verrouillé (LOT 2, drapeau curp_verrouillage_connexion) → 403 COMPTE_VERROUILLE
  ├─ authenticate() échoué → echecs_consecutifs++ (LOT 2)       → 401
  ├─ rôle mobile-only sans device_id (AUDITEUR/FORMATEUR)       → 403
  ├─ device_id + AUDITEUR/FORMATEUR → appairage DeviceBinding   → 403 DEVICE_LOCKED si tiers
  ├─ MFA obligatoire (rôle sensible sans 2FA, drapeau curp_mfa_obligatoire_sensibles) → 403 MFA_OBLIGATOIRE
  ├─ MFA actif → étape 2                                        → 403 MFA_REQUIRED + mfa_token (5 min)
  └─ finaliser_connexion() : last_login + derniere_connexion + AuditLog USER_LOGIN
        → 200 {access, refresh, refresh_in_cookie, must_change_password, user, role_context}
POST /api/auth/mfa/verify/ {mfa_token, code}                    → 200 (mêmes jetons)
POST /api/auth/token/refresh/                                     → nouvel access (rotation)
POST /api/auth/logout/                                            → révocation
```

- **Jeton** : SimpleJWT (access en corps pour le mobile, refresh en **cookie
  HttpOnly** pour le web, rotation activée). `FlexibleJWTAuthentication` accepte
  `Authorization: Bearer`, l'en-tête `X-JWT-Access` et `?access_token=`.
- **`must_change_password`** : renvoyé par le login et porté dans le jeton ;
  l'écran `/forced-password-change` est imposé par `ProtectedRoute`.
- **Horodatages** : depuis le LOT 2, `User.last_login` **et**
  `CompteUtilisateur.derniere_connexion` sont alimentés à chaque connexion
  réussie (l'écart E11 d'U0 est clos).
- **Verrouillage** : `PolitiqueSecurite.nombre_echecs_avant_verrouillage`
  (5 par défaut) et `duree_verrouillage_minutes` (15) sont appliqués à la
  connexion par `authentication/connexion_sure.py`, derrière le drapeau
  `flag.curp_verrouillage_connexion` (livré **éteint**). Le déverrouillage est
  automatique à échéance ou manuel (transition A5 `deverrouiller`).
- **MFA TOTP** : `habilitations/services/totp.py` (paquets locaux, aucune
  dépendance réseau) ; armement → confirmation d'un code → activation ;
  désactivation contrôlée (un compte portant un rôle sensible ne peut pas
  auto-désactiver). Drapeaux `flag.curp_mfa_active` et
  `flag.curp_mfa_obligatoire_sensibles` (livrés **éteints**).

### 3.2 Canaux

| Canal | Population | Contrôle |
|---|---|---|
| WEB | personnels, administration | `ALLOWED_WEB_ROLES` + permission Django `authentication.access_web` |
| MOBILE | étudiants (`AUDITEUR`), formateurs (`FORMATEUR`) | `MOBILE_ONLY_ROLES` : refus web explicite, appairage `DeviceBinding`, heartbeat |
| LES_DEUX | encadrants, superviseurs | `DUAL_ACCESS_ROLES` |

Le profil CURP porte aussi un `canal` (`WEB`/`MOBILE`/`LES_DEUX`) vérifié par le
moteur (contrôle 5), et chaque rôle du catalogue peut imposer un canal
(`RoleMetier.canal_impose`, ex. `ENSEIGNANT` et `ETUDIANT` → MOBILE).

---

## 4. Autorisation

### 4.1 Ce qui est appliqué aujourd'hui (legacy)

- `authentication/role_groups.py` : `ROLE_POLICY` (~530 lignes) mappe les 12
  rôles legacy vers les permissions Django ; les groupes `ROLE_*` sont
  synchronisés par signaux (`authentication/apps.py`).
- Classes DRF posées vue par vue : `IsDFRC`, `IsEncadrant`,
  `IsSecretariatOrDFRC`, `CanListParticipants`, etc.
  (`authentication/permissions.py`, `formations/api_access.py`).
- Filtrage « à la source » par secrétariat : `formations/access.py`.
- Défaut DRF : `IsAuthenticated` (settings `REST_FRAMEWORK`).

### 4.2 Ce que le dispositif CURP apporte

Le moteur `habilitations.services.moteur.est_autorise(utilisateur, code_permission,
*, canal, cible, contexte)` évalue **dix contrôles ordonnés** et retourne une
`DecisionAutorisation` motivée (`autorise`, `gouverne`, `motifs`, `octrois`).
Il est **pur** : aucune écriture, aucune dépendance DRF, fermeture par défaut
(*fail closed*). Détail des contrôles et des motifs :
[`docs/security/RBAC.md`](../security/RBAC.md) §7 et
[`docs/curp/04-moteur-autorisation.md`](../curp/04-moteur-autorisation.md).

Trois modes d'exploitation, pilotés **sans redéploiement** :

| Variable | Défaut livré | Effet |
|---|---|---|
| `HABILITATIONS_OBSERVATION` | `true` | Évalue et compte les écarts, ne modifie aucune réponse. |
| `HABILITATIONS_APPLICATION` | `false` | Le refus devient effectif et tracé `ACCES_REFUSE`. |

`habilitations.permissions.ExigePermission.pour('module.ressource.action')` est
la brique de branchement : *no-op* en mode OFF, observante en mode OBSERVATION,
refusante (403 + journal) en mode APPLICATION. **Elle n'est posée sur aucune
vue métier à ce jour** (0 usage) : le branchement relève du LOT 5 / U8, sur feu
vert séparé.

### 4.3 Projection pour l'interface

`GET /api/auth/capabilities/` renvoie `{version, role, capacites: {module: [actions]},
perimetres, role_context}` **+ la clé additive `habilitations`** :

```json
{"gouverne": true, "mode": "APPLICATION", "statut": "ACTIF",
 "canal": "WEB", "mfa_actif": false, "attributions_actives": 1}
```

Cette clé est **strictement descriptive** (elle n'accorde ni ne retire aucune
action). Côté React, le menu est dynamique (`peut(user, module, action)` dans
`frontend/src/utils/roles.js`) et les routes sont gardées par
`ProtectedRoute capacite={{module, action}}` ; la console CURP exige en plus la
capacité `habilitations_admin.gerer`, dérivée du drapeau `flag.curp_ui_admin`.

---

## 5. Organisation institutionnelle

Cible fonctionnelle : **Établissement → Direction → Département → Service →
Formation → Parcours → Niveau → Groupe → Cours/ECUE**.

| Niveau | Entité porteuse | État |
|---|---|---|
| Établissement | singleton INJS (mono-établissement) | sans objet |
| Direction | `administrations.Direction` | **créée au LOT 1** |
| Département | `administrations.Departement` (FK `direction`, PROTECT, nullable) | **créé au LOT 1** |
| Service | `ressources_humaines.Service` (+ `departement` FK nullable, LOT 1) ; `formations.Secretariat`, `RefTypeSecretariat`, `RefSite` | existant, hiérarchisé |
| Formation / Parcours / Niveau / Groupe | `formations.RefFormation`, `scolarite.Parcours`, `Niveau`, `Groupe` | existant |
| Cours / UE / ECUE | `formations.Module`, `scolarite.UE`/`ECUE` | existant |

Rattachement d'un compte : `CompteUtilisateur.departements` et
`.services` (M2M additifs, vides par défaut). Ce sont des **affiliations
administratives**, distinctes des **périmètres CURP** qui bornent les
permissions : les périmètres de type `DIRECTION`/`SERVICE` portent les mêmes
entités (le type `DEPARTEMENT` n'existe pas encore dans `Perimetre.Type` : les
rôles cibles utilisent `DIRECTION`, note J2).

`User.secretariat` (1:1 legacy) est **conservé** pendant la transition ;
`formations.Secretariat` n'est pas modifié (la correspondance
secrétariat ↔ département se fait côté périmètre CURP, type `SECRETARIAT`).

---

## 6. Journalisation et piste d'audit

| Journal | Portée | Garantie |
|---|---|---|
| `habilitations.JournalHabilitation` | gestes d'habilitation : création de compte, attribution/révocation de rôle, octroi/retrait de permission, délégation, politique, transitions de statut, connexions refusées, MFA, **accès refusés** (`ACCES_REFUSE`), organisation (LOT 3) — 37 types d'événements | append-only, **chaîné** (empreinte SHA-256 incluant l'empreinte précédente), numéro séquentiel ; immuabilité par déclencheurs PostgreSQL (migration 0002) et par l'ORM en SQLite ; `verifier_chaine()` détecte trou, rupture ou altération |
| `presences.AuditLog` | journal générique transverse : connexions, gestes métier, exports, modifications de profil | écrit par `_log_audit()` |
| `scolarite.JournalScolarite` | cycle de vie des objets académiques | écrit par les services métier |

Écriture **exclusivement** par `habilitations.services.journalisation.journaliser()`
(une ligne ne se crée jamais directement). Chaque geste sensible exige un
`motif` non vide ; l'adresse IP et l'agent utilisateur sont capturés.

---

## 7. Surface d'API (module Utilisateurs)

Préfixe `/api/habilitations/` (toutes gardées par `ExigeDrapeauAdmin`
sauf indication) :

| Route | Méthode | Usage |
|---|---|---|
| `mes-acces/` | GET | Profil gouverné du compte connecté (authentifié) |
| `evaluer/` | POST | Décision motivée du moteur ; évaluer autrui = administrateurs, tracé |
| `observations/synthese/`, `observations/remettre-a-zero/` | GET, POST | Pilotage du mode observation (administrateurs) |
| `roles/`, `permissions/`, `roles/<code>/`, `matrice/` | GET | Référentiel en lecture, matrice compacte (authentifié / console) |
| `comptes/` | GET, POST | Liste filtrable paginée, création assistée |
| `comptes/<pk>/` | GET | Fiche complète (rôles actifs/inactifs, dérogations, délégations, journal) |
| `comptes/<pk>/simuler-modification/` | POST | Différentiel de droits (gagnés/perdus/conservés) |
| `comptes/<pk>/modifier/` | PATCH | Modification (différentiel accepté + motif obligatoires) |
| `comptes/<pk>/statut/` | POST | Transition de la machine à états A5 |
| `comptes/<pk>/effective-permissions/` | GET | **Permissions effectives (LOT 3)** : rôles + octrois − retraits |
| `comptes/imports/`, `comptes/imports/<ref>/`, `…/annuler/`, `comptes/import-simuler/` | GET, POST | Imports en masse réversibles (U5) |
| `propositions/`, `propositions/<pk>/approuver/`, `…/rejeter/`, `provisions/scanner/` | GET, POST | File de provisionnement humaine (U5) |
| `derogations/`, `derogations/<pk>/revoquer/` | GET, POST | Dérogations bornées |
| `delegations/`, `delegations/<pk>/terminer/`, `…/activer/`, `…/action/` | GET, POST | Délégations (profondeur 1) |
| `notifications/`, `notifications/<pk>/lire/`, `notifications/tout-lire/` | GET, POST | Notifications d'échéance |
| `journal/`, `journal/integrite/` | GET | Piste d'audit filtrable, contrôle de chaînage |
| `organisation/directions/[<pk>/]`, `organisation/departements/[<pk>/]`, `organisation/services/[<pk>/]`, `…/<pk>/comptes/` | GET, POST, PATCH, DELETE | **Organisation (LOT 3)** : CRUD + rattachements de comptes |

Préfixe `/api/auth/` : `login/`, `mfa/setup/`, `mfa/confirm/`, `mfa/verify/`,
`mfa/disable/`, `token/refresh/`, `logout/`, `me/`, `me/change-password/`,
`roles/`, `capabilities/`, `users/`, `users/<pk>/`.

Schéma vivant : `/api/schema/` (OpenAPI) et `/api/docs/` (Swagger UI).

---

## 8. Écrans (React)

Routes sous `/administration/comptes`, gardées par
`ProtectedRoute capacite={{module: 'habilitations_admin', action: 'gerer'}}` :

| Route | Écran | Fichier |
|---|---|---|
| `/administration/comptes` | Liste des comptes (filtres, pagination) | `frontend/src/pages/habilitations/ListeComptes.jsx` |
| `…/nouveau` | Assistant de création (5 étapes) | `AssistantCreation.jsx` |
| `…/:id` | Fiche compte (+ blocs **Organisation** et **Permissions effectives**, LOT 3) | `FicheCompte.jsx` |
| `…/:id/modifier` | Modification avec panneau de différentiel | `ModifierCompte.jsx`, `DifferentialPanel.jsx` |
| `…/roles` | Gestion des rôles (81) | `GestionRoles.jsx` |
| `…/matrice` | Matrice rôle × module, recherche et filtres (LOT 3) | `MatricePermissions.jsx` |
| `…/organisation` | Directions / Départements / Services + utilisateurs rattachés (LOT 3) | `Organisation.jsx` |
| `…/derogations`, `…/delegations` | Dérogations, délégations | `Derogations.jsx`, `Delegations.jsx` |
| `…/provisionnement`, `…/operations-masse`, `…/revue`, `…/notifications`, `…/journal` | File U5, imports, revue, notifications, piste d'audit | voir dossier |
| `/login`, `/forced-password-change` | Connexion (+ étape MFA et message de verrouillage, LOT 3) | `Login.jsx`, `ForcedPasswordChange.jsx` |
| `/users` | Écran legacy des utilisateurs (12 rôles) — cohabite | `Users.jsx` |

Service d'accès aux données : `frontend/src/services/habilitations.js`
(react-query, clés `HAB_KEYS`/`ORG_KEYS`).

---

## 9. Mobile / PWA (`qr_badge_mobile`, Flutter)

- Connexion par les mêmes endpoints, avec `device_id` → appairage
  `presences.DeviceBinding` (un appareil = un compte étudiant/formateur).
- Les rôles `AUDITEUR` (étudiant) et `FORMATEUR` sont **mobile-only** : le web
  les refuse explicitement (message dédié), et le canal est vérifié côté CURP
  (`RoleMetier.canal_impose`).
- Heartbeats et auto-clôture de pointage traités par les commandes
  `process_mobile_heartbeats`, `auto_close_pointages`, `auto_sessions`
  (service `cron`).
- Le mobile ne parle **qu'à** l'API Django : jamais d'accès direct à la base.

---

## 10. Bascule (LOT 5 / U8) — état d'avancement

Le LOT 5 a été exécuté le 2026-09-15 (feu vert du commanditaire) : les
**étapes 1 à 3** de la séquence sont livrées, de façon additive et
réversible. Le défaut livré reste OBSERVATION : **aucun impact production**
— les refus effectifs exigent le mode APPLICATION, activable vue par vue.
Séquence et état :

1. ✅ rattachement **additif** des comptes legacy à un profil CURP —
   commande `rattacher_comptes_legacy` (simulation par défaut, `--appliquer`
   pour écrire, table A6, jamais d'auto-validation d'un rôle sensible,
   idempotente) ;
2. ✅ mode **OBSERVATION** mesuré sur les vues réelles (compteurs d'écarts,
   `observations_habilitations` ; défaut des réglages
   `HABILITATIONS_OBSERVATION=true`) ;
3. ✅ début de branchement de `ExigePermission` sur les vues critiques,
   vue par vue — deux vues pilotes : liste des inscriptions
   (`scolarite.inscription_administrative.consulter`) et confirmation de
   paiement (`finances_etud.paiement.valider`) ; la suite se pose au cas par
   cas, chaque vue restant débranchable sans redéploiement ;
4. ⏸ mode **APPLICATION** progressif, drapeau par drapeau, avec repli
   immédiat (`HABILITATIONS_APPLICATION=false`, kill-switch verrouillé au
   LOT 6) — à décider vue par vue sur la base des compteurs d'observation ;
5. ⏸ retrait du legacy (écarts E1/E2/E7) après stabilisation — hors périmètre
   du LOT 5.

**Prérequis techniques du LOT 4 — état après exécution** (détail et preuves :
[`docs/audit/permissions.md`](../audit/permissions.md) §5 et §11) :

- ✅ **résolution des cibles « objet métier »** :
  `moteur._decrire_perimetre` expose `content_type_id` et `id` (L4-01) ; la
  voie `has_object_permission` rapproche type+pk exacts au contrôle 9 ;
- ✅ **résolveurs hiérarchiques** : `habilitations/services/resolveurs.py` —
  Direction ⊃ Département ⊃ Service RH, Formation ⊃ Parcours ⊃
  Groupe/Niveau/SITE, maquette ⊃ UE ⊃ ECUE, ETUDIANT ⊃ ses inscriptions ;
  appliqués par défaut sur la voie objet, un résolveur injecté
  (`contexte={'couverture': …}`) reste prioritaire ; type de périmètre
  `DEPARTEMENT` ajouté (migration 0013) ;
- ✅ **pose de périmètres non secrétariat** par la console : champ additif
  `perimetres: [{type, object_id}]` sur les lignes d'attribution +
  sélecteurs Direction/Département dans l'assistant et la modification
  (les types pédagogiques restent posables par l'API, repli admin Django) ;
- ⏸ arbitrage atelier des cases **J2** de la matrice (voir RBAC §9) — hors de
  main du LOT 5, rien de unilatéral.

---

## 11. Garde-fous permanents

| Règle | Traduction dans le code |
|---|---|
| Additif d'abord (R2) | migrations additives et réversibles ; M2M vides par défaut ; aucune donnée existante modifiée |
| Observation avant refus (R3) | `HABILITATIONS_APPLICATION=false` par défaut ; `ExigePermission` posée uniquement sur les vues pilotes du LOT 5, en OBSERVATION (aucune réponse changée) |
| Backend seule autorité (S3) | `capabilities` et `habilitations` sont des projections ; les vues gardent leurs `permission_classes` |
| Élargissement explicite (S4) | un RETRAIT ne se lève que par un OCTROI postérieur **et** doublement signé |
| Jamais de suppression physique (S5) | révocations (statut REVOQUEE), désactivation du référentiel, annulations d'import |
| Traçabilité | motif obligatoire sur tout geste sensible ; journal chaîné vérifiable |
| Réversibilité immédiate | drapeaux `parametres` (kill-switch sans redéploiement) |

---

## 12. Chiffres de référence (mesurés sur le dépôt au 2026-09-14)

| Objet | Valeur |
|---|---|
| Rôles du catalogue | **81** (35 de l'annexe A1 + 46 cibles J2), dont **22 sensibles** |
| Permissions atomiques | **1 155** codes `<module>.<ressource>.<action>` sur **20 modules** |
| Verbes | **13 canoniques** + verbes métier = **31 actions** au modèle |
| Liaisons rôle × permission (matrice dérivée) | **10 440** |
| Permissions critiques (double validation) | **15** |
| Types de périmètre | **12** |
| Statuts de compte | **6** · Canaux : 3 |
| Types d'événements du journal | **37** |
| Couples d'incompatibilité (séparation des tâches) | **5** |
| Applications Django | 20 métier + `habilitations`, `parametres`, `core`, `authentication`, `referentiels`, `exports` |
| Tests backend `habilitations` | **415** (2 ignorés : déclencheurs PostgreSQL), dont **60 ajoutés par le LOT 4** et **26 par le LOT 5** (rejeu 2026-09-15) |

Rejouer les mesures :

```bash
cd backend
python manage.py shell -c "from habilitations.referentiel.chargement import charger_referentiel; print(charger_referentiel(dry_run=True).as_dict())"
python manage.py inventaire_habilitation --comptes
python manage.py test habilitations -v 1
```

---

## 13. Sources de vérité (fichiers)

| Sujet | Fichier |
|---|---|
| Rôles legacy, `ROLE_POLICY`, groupes | `backend/authentication/role_groups.py` |
| Permissions DRF legacy | `backend/authentication/permissions.py`, `backend/formations/api_access.py` |
| Connexion, MFA, verrouillage, horodatages | `backend/authentication/views.py`, `backend/authentication/connexion_sure.py`, `backend/habilitations/services/totp.py` |
| Projection des capacités | `backend/authentication/capabilities.py`, `backend/habilitations/services/projection.py` |
| Modèles CURP | `backend/habilitations/models/` |
| Moteur et codes de motif | `backend/habilitations/services/moteur.py`, `backend/habilitations/services/codes.py` |
| Permission DRF du moteur | `backend/habilitations/permissions.py` |
| Référentiel (rôles, matrice, modules) | `backend/habilitations/referentiel/` |
| Console et services d'administration | `backend/habilitations/api/`, `backend/habilitations/services/comptes_admin.py` |
| Organisation (LOT 1 / LOT 3) | `backend/administrations/models.py`, `backend/habilitations/api/views_admin_organisation.py` |
| Journal | `backend/habilitations/services/journalisation.py`, `backend/habilitations/models/journal.py` |
| Drapeaux | `backend/parametres/` (`flags.py`, migrations de seed) |
| Interface | `frontend/src/pages/habilitations/`, `frontend/src/services/habilitations.js`, `frontend/src/utils/roles.js` |

> **Nomenclature** : les `flag.lot01_…lot12_…` du seed `parametres` désignent les
> **lots de construction du produit** (L1→L12) ; les « LOT 1 → LOT 5 » de ce
> document désignent les **lots du module Utilisateurs** (plan
> [`docs/curp/05-…`](../curp/05-architecture-completion-module-utilisateurs.md) §7).
> Les deux numérotations sont indépendantes.
