# Architecture — Complétion du module Utilisateurs / Comptes / Rôles / Permissions / Périmètres

> **Date** : 2026-09-14 · **Base** : audit Phase 0 (`docs/audits/2026-09-14-audit-module-utilisateurs.md`)
> **Décisions validées** (atelier du 2026-09-14) :
> 1. Création des modèles **Direction + Département** (additifs, les périmètres CURP
>    `DIRECTION`/`SERVICE` seront portés par ces entités) ;
> 2. Ajout de **tous les rôles cibles manquants** au catalogue, en **données provisoires J2**
>    (migration idempotente/réversible, cases matrice marquées « à valider en atelier ») ;
> 3. **Périmètre sécurité complet** : verrouillage appliqué à la connexion + **MFA TOTP**
>    (drapeauté, éteint par défaut) + alimentation de `last_login`/`derniere_connexion`.
>
> **Principe directeur** : le socle CURP (U0–U5) n'est pas reconstruit. Chaque lot est
> **additif**, **drapeauté** (éteint par défaut), **réversible** (migrations), et ne produit
> aucun effet sans validation humaine ou feu vert explicite.

---

## 1. Modèle de données (LOT 1)

### 1.1 Organisation — nouveaux modèles (app `administrations`)

```
Direction (code unique, libellé, ordre, actif, dates)
   └── Departement (code unique, libellé, direction FK PROTECT null, ordre, actif, dates)
          └── ressources_humaines.Service (existant) + champ departement FK PROTECT null
```

- `Direction` : `code` (unique), `libelle`, `ordre`, `actif`, `created_at/updated_at`.
- `Departement` : `code` (unique), `libelle`, `direction` FK (PROTECT, nullable — un
  département peut exister avant d'être rattaché), `ordre`, `actif`, dates.
- `Service` (RH, existant) : nouveau champ `departement` FK (PROTECT, **nullable**,
  `related_name='services'`) — aucun service existant n'est touché (désrattaché = null).
- `formations.Secretariat` : **non modifié** ; la correspondance secrétariat↔département
  est documentée (le rattachement se fait côté périmètre CURP, type `SECRETARIAT`).
- Périmètre CURP : le type `DIRECTION` existe déjà ; la création future du type
  `DEPARTEMENT` est reportée au lot organisation-complète (les rôles cibles utilisent
  `DIRECTION` comme périmètre par défaut, cf. note J2).

### 1.2 Rattachement compte ↔ organisation (app `habilitations`)

- `CompteUtilisateur.departements` : M2M → `administrations.Departement`
  (`blank`, `related_name='comptes'`).
- `CompteUtilisateur.services` : M2M → `ressources_humaines.Service`
  (`blank`, `related_name='comptes'`).
- `Personne.photo` **existe déjà** (ImageField) — aucun travail (RAS, l'audit le cite
  comme absent sur `User` legacy ; la fiche CURP porte `Personne`).
- `User.secretariat` (legacy 1:1) **conservé** : cohabitation pendant la transition U8.

### 1.3 Rôles cibles (référentiel, données — pas de code)

- `catalogue_roles.py` : **46 rôles ajoutés** (total 81), section « CIBLES (J2) »,
  convention de la ligne existante `(code, libellé, domaine, niveau, périmètre,
  module_requis, sensible, canal, ordre, description)` ; sensibilité `True` sur
  SIGNATAIRE, VALIDATEUR_DIPLOMES, RESPONSABLE_FINANCES, BOURSE_MANAGER,
  CONTROLEUR_FINANCIER, PAIE_MANAGER, SYSADMIN, NETWORK_ADMIN, DB_ADMIN, SECURITY_ADMIN,
  API_MANAGER.
- `catalogue_matrice.py` : nouveau dictionnaire `NIVEAUX_ROLES_CIBLES`
  (origine **J2**, « provisoire, à valider en atelier ») ; fusionné dans
  `niveaux_du_role()` **avant** les règles dérivées (exports/référentiels).
- Mappages documentés (pas de doublons fonctionnels) : `SUPER_ADMIN`/`ADMIN_SI`→
  `ADMIN_SYSTEME`, `DIRECTION`→`DIRECTION_GENERALE`, `PEDAGOGIE_MANAGER`→
  `RESPONSABLE_PEDAGOGIQUE`, `SCOLARITE_MANAGER`→`SCOLARITE`, `ETUDIANT_MANAGER`→
  `GESTIONNAIRE_ETUDIANTS`, `GROUPE_MANAGER`→`GESTIONNAIRE_GROUPES`, `NOTE_MANAGER`→
  `GESTIONNAIRE_NOTES`, `JURY_PRESIDENT`→`RESPONSABLE_JURY`, `JURY_MEMBER`→`MEMBRE_JURY`,
  `STAGE_MANAGER`→`GESTIONNAIRE_STAGES`, `LECTEUR`→`CONSULTATION`.
- Qualité du chargeur conservée : après chargement, **0 rôle sans permission,
  0 permission orpheline** (les rôles SI portent un niveau minimal `parametres` —
  placeholder J2 documenté).
- Rechargement : `python manage.py charger_referentiel_injs` (idempotent, réversible :
  les rôles J2 peuvent être désactivés sans suppression).

### 1.4 Migrations (LOT 1)

| App | Migration | Contenu |
|---|---|---|
| administrations | 0002 | `Direction`, `Departement` |
| ressources_humaines | 0002 | `Service.departement` (nullable, dépend de administrations.0002) |
| habilitations | 0009 | `CompteUtilisateur.departements` + `.services` (M2M) |

Toutes **additives** (create model / add field nullable / M2M) et **réversibles**
(`migrate <app> <n-1>` vérifiée). Aucune donnée existante n'est modifiée.

---

## 2. Sécurité effective (LOT 2 — U6 avancée)

- **Verrouillage de compte** : la connexion (`login_view`) applique
  `PolitiqueSecurite.nombre_echecs_avant_verrouillage` / `duree_verrouillage_minutes`
  sur `CompteUtilisateur.echecs_consecutifs` / `date_verrouillage` (statut `VERROUILLE`
  via la machine A5, journalisé) ; déverrouillage par un admin habilité (endpoint
  `POST /comptes/{id}/statut/` existant) ; les échecs sont comptés par compte, pas par IP
  (le throttlage IP existe déjà en amont).
- **MFA TOTP** : génération de secret + confirmation d'un code à 6 chiffres ; activation
  par le compte (2FA optionnelle par rôle sensible via drapeau
  `flag.curp_mfa_obligatoire_sensibles`, éteint par défaut) ; vérification au login en
  deux temps (`POST /api/auth/mfa/verify/`) avec jeton court (5 min) ; paquets locaux,
  aucune dépendance réseau. `CompteUtilisateur.mfa_actif` (existant) devient actif.
- **Sessions** : alimentation de `User.last_login` + `CompteUtilisateur.derniere_connexion`
  sur **chaque** login JWT (corrige l'écart E11) ; expiration de session par inactivité
  déjà portée par `PolitiqueSecurite.inactivite_session_minutes`.
- **Drapeaux** (livrés ÉTEINTS) : `flag.curp_verrouillage_connexion`,
  `flag.curp_mfa_active`, `flag.curp_mfa_obligatoire_sensibles` — extinction immédiate
  sans redéploiement (règle R3).

## 3. API (LOT 2 + 3)

- `POST /api/auth/mfa/setup/`, `POST /api/auth/mfa/verify/`, `POST /api/auth/mfa/disable/`
  (désactivation par l'admin uniquement pour un compte tiers — auto-désactivation interdite
  si un rôle sensible est porté).
- `GET /api/habilitations/organisation/directions/` (+CRUD),
  `GET /api/habilitations/organisation/departements/` (+CRUD, filtre `direction`),
  `GET /api/habilitations/organisation/services/` (lecture, filtre `departement`).
- `GET /api/habilitations/comptes/{id}/effective-permissions/` : permissions effectives
  (rôles + explicites − restrictions) + modules/écrans dérivés (projections du moteur,
  lecture seule).
- Actions compte : `POST /api/habilitations/comptes/{id}/verrouiller/` / `.../deverrouiller/`
  (raccourcis journalisés, mêmes contrôles que la machine A5).

## 4. Écrans frontend (LOT 3)

- **Organisation** : `Administration → Organisation → Directions / Départements /
  Services` — tableaux CRUD, rattachement service→département, utilisateurs rattachés
  (lecture), garde `habilitations_admin.gerer`.
- **Fiche compte** : blocs « Organisation » (départements/services éditables) et
  « Permissions effectives » (héritées vs explicites, modules/écrans dérivés).
- **Matrice** : recherche + filtres (rôle, module, verbe) sur les 81 rôles.
- **Login** : étape MFA (code 6 chiffres) si le compte est en 2FA ; message de verrouillage
  explicite (délai restant).
- Les contrôles front restent des masques : l'autorité est toujours le backend.

## 5. Tests (LOT 1 → 4)

- **LOT 1** : création/hiérarchisation Direction→Département→Service ; M2M compte↔
  organisation ; chargeur référentiel avec les 81 rôles (0 orphelin, 0 sans permission,
  idempotence du rechargement) ; réversibilité des 3 migrations.
- **LOT 2** : verrouillage (seuil, délai, déverrouillage admin, journal) ; MFA (setup,
  code valide/expire/erroné, obligatoire pour rôle sensible, désactivation contrôlée) ;
  `last_login`/`derniere_connexion` alimentés ; drapeaux éteints = comportement d'avant
  (no-op).
- **LOT 4** : refus d'accès croisés du prompt §34 (enseignant A ≠ B, chef dépt A ≠ B,
  étudiant A ≠ B, agent scolarité ≠ admin rôles, admin SI ≠ permissions métier sensibles)
  **en mode APPLICATION du moteur sur une base de test** ; scénario E2E §35 (création →
  rôles → organisation → périmètre → connexion → menu → accès autorisé/interdit →
  modification de rôle → recalcul → audit) ; consolidation documentation
  (`docs/architecture/IAM.md`, `docs/security/RBAC.md`, `docs/administration/utilisateurs.md`,
  `docs/audit/permissions.md`).

## 6. Bascule (LOT 5 — U8, **feu vert séparé obligatoire**)

Rattachement additif des comptes legacy aux profils CURP, mode OBSERVATION puis
APPLICATION du moteur (`HABILITATIONS_*`), branchement `ExigePermission` sur les vues
critiques, retrait progressif du legacy (E1/E2/E7), documentation de transition.
**Hors des lots 1–4 : aucun impact production avant ce feu vert.**

## 7. Plan de lots (validation par lot, push sur demande)

| Lot | Contenu | Migrations | Tests |
|---|---|---|---|
| **1** | Organisation (modèles + M2M) + 46 rôles cibles J2 + matrice | 3 (additives) | référentiel + modèles |
| **2** | Verrouillage connexion + MFA TOTP + last_login + endpoints | 1 (flags) + champs compte si besoin | sécurité, refus |
| **3** | Écrans Organisation / permissions effectives / matrice + API organisation | — | Vitest |
| **4** | Tests §34/§35 + consolidation docs | — | E2E |
| **5** | Bascule U8 (observation → application) | — | régression complète |
