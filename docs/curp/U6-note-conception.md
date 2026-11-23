# U6 — Sécurité effective de la connexion (LOT 2 du module Utilisateurs)

> **Date** : 2026-09-14 · **Portée** : ce que le LOT 2 livre de l'unité U6
> (MFA / verrouillage / sessions) et ce qui reste en retrait.
> **Principe** : tout est **additif**, **drapeauté** (livré ÉTEINT) et
> **journalisé** ; drapeau fermé = comportement strictement d'avant (no-op).

## 1. Livré

### 1.1 Verrouillage de compte à la connexion
- **Drapeau** : `flag.curp_verrouillage_connexion` (ordonné 230, éteint).
- Mécanique : à chaque échec d'authentification,
  `CompteUtilisateur.echecs_consecutifs` est incrémenté (uniquement pour les
  comptes gouvernés, c'est-à-dire dotés d'un profil CURP, et seulement en
  statut ACTIF). Au seuil `PolitiqueSecurite.nombre_echecs_avant_verrouillage`
  (défaut 5), la machine à états A5 applique `verrouiller`
  (`changer_statut` → statut VERROUILLE, `is_active=False`, sessions
  révoquées, journal `COMPTE_VERROUILLE`).
- La vérification précède l'authentification : un compte verrouillé ne
  laisse pas filtrer le bon mot de passe (réponse 403 `COMPTE_VERROUILLE`,
  journal `CONNEXION_REFUSEE_VERROUILLEE`).
- Déverrouillage : automatique à l'échéance de
  `duree_verrouillage_minutes` (défaut 15 min, transition `deverrouiller`
  journalisée `COMPTE_DEVERROUILLE`) ou par un administrateur via la console
  CURP existante (`POST /api/habilitations/comptes/{id}/statut/`).
- La levée d'un verrouillage (auto ou admin) **remet le compteur d'échecs à
  zéro** : de nouveaux échecs complets sont requis pour re-verrouiller.
- **Correction U5 annexée** : la transition `verrouiller` alimente désormais
  `CompteUtilisateur.date_verrouillage` (champ existant, jamais écrit avant),
  indispensable au calcul du délai.

### 1.2 MFA TOTP
- **Implémentation** : `habilitations.services.totp` — RFC 6238, HMAC-SHA1,
  période 30 s, 6 chiffres, fenêtre ±1 pas, secret base32 (20 octets).
  **Aucune dépendance externe ni appel réseau.**
- **Drapeaux** : `flag.curp_mfa_active` (231) active l'étape pour les comptes
  `mfa_actif=True` ; `flag.curp_mfa_obligatoire_sensibles` (232) rend le MFA
  obligatoire pour les comptes portant un rôle sensible actif (définition :
  colonne « Sens. » du catalogue des rôles — 22 rôles au LOT 1) et interdit la
  désactivation de leur MFA (409).
- **Flux de connexion** : identifiants valides + MFA requis → 403
  `MFA_REQUIRED` avec un **jeton d'étape court (5 min, claim `mfa_etape`)** ;
  `POST /api/auth/mfa/verify/` (throttlé comme le login) vérifie le code
  TOTP puis finalise la connexion (mêmes tokens/cookies que le login direct).
  Code erroné → 400 `MFA_CODE_INVALIDE` (aucun effet de bord sur le compte) ;
  jeton expiré ou hors étape → 400 `MFA_JETON_INVALIDE`.
- **Gestion** (authentications requises, tiers via `mutate_users`) :
  - `POST /api/auth/mfa/setup/` → arme un secret (retour secret + URI
    `otpauth://` pour l'application d'authentification) ;
  - `POST /api/auth/mfa/confirm/` → active après vérification d'un code valide ;
  - `POST /api/auth/mfa/disable/` → désactive (code exigé **pour soi-même** ;
    refusa 409 sous obligation de MFA pour rôles sensibles).
- **Traçabilité** : nouveaux évènements du journal append-only chaîné
  `MFA_ETAPSE_DEMANDEE`, `MFA_ACTIVE`, `MFA_DESACTIVE`
  (migration `habilitations/0011` de choices, sans effet sur les données).
- **Champ** : `CompteUtilisateur.mfa_secret` (additif, vide par défaut —
  migration `habilitations/0010`).

### 1.3 Horodatage des connexions (correction de l'écart E11 d'U0)
- Sans drapeau (comportement toujours vrai) : à chaque connexion réussie
  (web ou mobile, directe ou après MFA), `User.last_login` et
  `CompteUtilisateur.derniere_connexion` sont alimentés et le compteur
  d'échecs remis à zéro. Les comptes dormants sont à nouveau détectables.
- Le test de caractérisation U0 qui figeait l'ancien défaut est mis à jour
  pour figer le comportement corrigé.

### 1.4 API ajoutée
```
POST /api/auth/mfa/verify/    AllowAny + throttle login (jeton d'étape + code)
POST /api/auth/mfa/setup/     IsAuthenticated (soi, ou tiers via mutate_users)
POST /api/auth/mfa/confirm/   IsAuthenticated
POST /api/auth/mfa/disable/   IsAuthenticated
```
Plus la sémantique étendue de `POST /api/auth/login/` : codes
`COMPTE_VERROUILLE` (403), `MFA_REQUIRED` (403 + `mfa_token`),
`MFA_OBLIGATOIRE` (403).

## 2. Hors périmètre du LOT 2 (reste de U6, à instruire)

- **Sessions** : expiration par inactivité (`inactivite_session_minutes` de
  la politique) — le réglage existe ; son application stricte aux sessions web
  (re-jeton périodique) reste à brancher.
- **Appareils** : révocation d'appareils à distance, multi-appareils — le
  verrouillage d'appareil mobile (AUDITEUR/FORMATEUR) existe déjà ; la
  révocation curative n'est pas livrée ici.
- **Interface** : l'étape MFA côté écran (saisie du code, écran de
  verrouillage avec délai restant, gestion du MFA dans la fiche compte)
  relève du **LOT 3** (frontend).
- **Bascule** : le LOT 5 (U8) branchera `ExigePermission` sur les vues
  métier et passera le moteur en OBSERVATION → APPLICATION ; la sécurité de
  connexion livrée ici fonctionne **indépendamment** de ce basculement.

## 3. Sécurité des choix

- Le MFA n'est **jamais** contournable par le drapeau `curp_mfa_active`
  fermé + obligation ouverte : l'obligation (232) exige le passage MFA même
  si l'étape (231) est fermée pour les autres (les deux drapeaux sont
  indépendants mais l'obligation prime pour les comptes sensibles).
- Le secret TOTP n'est jamais renvoyé par l'API après armement (retour unique
  lors de `setup/`) ; `disable` par soi-même exige la preuve de possession
  (code valide).
- Les refus (verrouillage, étape demandée, codes invalides) ne révèlent pas
  d'information exploitable au-delà du statut du compte.
