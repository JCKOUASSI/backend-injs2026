# U1 — Modèle de données de l'habilitation (livrable CURP_MODELE_DONNEES)

> Socle additif de l'application `backend/habilitations/`, unité U1.
> Aucun modèle des applications existantes n'est modifié (vérifié par
> `git diff` : seuls `config/settings.py` et la CI le sont). Aucune décision
> d'accès n'est encore prise par cette application : elle contient des
> données et des contrôles **purs non bloquants**. Date : 2026-09-13.

## 1. La chaîne de responsabilité

```
PERSONNE ──< COMPTE UTILISATEUR >──< ATTRIBUTION RÔLE >── RÔLE MÉTIER
 (identité)      (profil OneToOne          │                   │
                  de auth.User)            ├──< PÉRIMÈTRE       │ (niveau défaut,
                                           │                   │  module requis,
                          COMPTE >──< DÉROGATION >── PERMISSION  │  sensible)
                          (OCTROI / RETRAIT borné à 90 j)
                                           │
                          COMPTE ──> DÉLÉGATION (bornée dans le temps)
                                           │
                    TOUTE OPÉRATION ──> JOURNAL HABILITATION (append-only chaîné)

Réglages transverses : POLITIQUE DE SÉCURITÉ (singleton, paramétrable sans redéploiement)
```

On ne confond pas l'identité (Personne), le compte de connexion
(`authentication.User`, inchangé), son profil CURP (CompteUtilisateur), les
rôles, les permissions atomiques et les périmètres.

## 2. Les dix modèles

| # | Modèle | Rôle essentiel |
|---|---|---|
| 1 | `Personne` | Identité métier unique ; matricule lisible `PERS-AAAA-NNNNN` ; 5 liens **OneToOne nullable et non exclusifs** vers `ressources_humaines.Agent`, `formations.Formateur`, `formations.Participant`, `scolarite.DossierEtudiant`, `admissions.Candidat`. |
| 2 | `CompteUtilisateur` | **OneToOne** de `authentication.User` (`related_name='profil_habilitation'`, CASCADE sur le profil) ; 6 statuts, 3 canaux, dates de cycle de vie, échecs, indicateur MFA. `personne` nullable (comptes techniques). |
| 3 | `RoleMetier` | Référentiel en base (aucune liste figée au code) : code stable, domaine, niveau par défaut, périmètre par défaut, `module_requis`, disponibilité calculée, caractère sensible, cumul, canal imposé ; M2M réflexive `incompatible_avec`. |
| 4 | `PermissionMetier` | Permission atomique `module.ressource.action` (13 actions du modèle fonctionnel), portée maximale, criticité NORMALE/SENSIBLE/CRITIQUE, motif et double validation exigés, journalisation. |
| 5 | `Perimetre` | 12 types (INJS_ENTIER… PROPRE_COMPTE) + cible **polymorphe** (ContentType) + `reference_lisible` (code métier, jamais l'identifiant technique). |
| 6 | `AttributionRole` | Compte × rôle × niveau effectif × périmètres (M2M) × dates × motif obligatoire × attribué/validé par × statut ; unicité d'une attribution ACTIVE par couple compte/rôle. |
| 7 | `PermissionAttribuee` | Dérogation OCTROI/RETRAIT, motif obligatoire, OCTROI toujours borné (90 j max par défaut, lus dans la politique). |
| 8 | `DelegationHabilitation` | Délégant/délégataire, rôles/permissions/périmètres délégués, dates **obligatoirement bornées**, contrainte SQL « pas de délégation à soi-même ». |
| 9 | `PolitiqueSecurite` | Singleton (`pk=1`) : politique de mot de passe, verrouillage, sessions, inactivité, durée max des dérogations, MFA et canaux par rôle. Non supprimable. |
| 10 | `JournalHabilitation` | Registre append-only **chaîné SHA-256** (voir §4). |

Les tables implicites des relations plusieurs-à-plusieurs ne sont pas des
modèles métier : le total reste bien **dix**.

### Statuts et canaux

- Compte : `INVITE, ACTIF, SUSPENDU, DESACTIVE, VERROUILLE, EXPIRE`.
- Canal : `WEB, MOBILE, LES_DEUX`. Le profil permet d'imposer `MOBILE` aux
  futurs rôles enseignant/étudiant ; le comportement actuel des 12 rôles
  (FORMATEUR/AUDITEUR mobiles) reste régi par le dispositif existant jusqu'à
  la migration U8.
- Attributions/dérogations/délégations : statuts de cycle de vie PROPOSÉE →
  ACTIVE → SUSPENDUE/EXPIREE/REVOQUEE/TERMINEE.

## 3. Référence polymorphe des périmètres (décision d'architecture 3)

`Perimetre` utilise `(content_type, object_id, cible=GenericForeignKey)`
plutôt qu'une dizaine de clés étrangères dures : un périmètre peut viser un
secrétariat, une formation, un groupe, un module/ECUE, un site ou un
étudiant sans coupler cette application transverse aux vingt applications.
Le `reference_lisible` porte le code métier (ex. `SECR-DEMO-A`) et reste
exploitable même si l'objet source disparaît. Les types globaux
(`INJS_ENTIER`, `PROPRE_COMPTE`) n'ont pas d'objet rattaché.

## 4. Journal append-only et chaîné

- Écriture exclusive par `habilitations.services.journalisation.journaliser(...)`,
  qui calcule sous transaction : `numero` suivant et
  `empreinte = SHA-256(empreinte_précédente | contenu canonique JSON)`.
- Immuabilité défendue à deux niveaux :
  - **ORM/modèle** (valable sur SQLite comme PostgreSQL) : `save()` refuse la
    mise à jour, `delete()` interdit, le `QuerySet` refuse `update()`/
    `delete()` en masse, l'admin Django est consultative (pas d'ajout ni de
    modification ni de suppression).
  - **Base PostgreSQL** (production et CI) : déclencheurs
    `BEFORE UPDATE/DELETE` (migration `0002`) qui lèvent une exception.
    SQLite ne les reçoit pas (le vidage des tests y passe par `DELETE FROM`)
    ; il n'est qu'une bascule de développement, jamais un moteur de
    production.
- `verifier_chaine()` recalcule tout et signale trou de séquence, rupture de
  chaînage ou empreinte altérée. La commande
  `verifier_chaine_habilitations` sort en code 1 en cas d'anomalie
  (première brique du contrôle périodique d'U7).

## 5. Services et commandes

- `services/journalisation.py` : écriture chaînée, empreintes, vérification.
- `services/identite.py` : génération des matricules, détection
  **non bloquante** de doublons (nom + date de naissance, téléphone,
  courriel), chaque critère étant activable/désactivable.
- `services/validations.py` : contrôles **purs** (durée d'une dérogation,
  incompatibilités réciproques, disponibilité selon les modules installés).
- `services/politique.py` : modification du singleton tracée au journal.
- Commandes :
  - `init_habilitations_injs [--dry-run]` : politique singleton par défaut
    (idempotente) ; elle ne peuple aucun rôle (les 33 rôles sont l'unité U3) ;
  - `verifier_chaine_habilitations` : intégrité du journal ;
  - `habilitations_diag` : rapport **indicatif** (comptes sans profil,
    doublons, attributions enfreignant une règle, dérogations/délégations
    échues), code de sortie toujours 0 en U1 (observation).

## 6. Additivité et non-régression

- L'application n'enregistre **aucun signal**, n'installe **aucune
  permission DRF** et n'expose **aucune route** en U1 ; son `ready()` est
  vide. La créer ou la retirer ne change aucune décision d'accès.
- Les 12 rôles, `role_groups.py`, le JWT, les canaux mobiles et le
  cloisonnement par secrétariat ne sont pas touchés.
- Preuve testée : `habilitations/tests/test_additivite.py` vérifie qu'un
  `User` sans profil se connecte exactement comme avant (web admin 200,
  auditeur web 403 / mobile 200) et que ses permissions sont inchangées.

## 7. Migrations et réversibilité

- `0001_initial` crée les dix tables (les seules clés étrangères sortantes
  ajoutées sont celles des nouvelles tables ; le OneToOne du profil est
  porté par la table `habilitations_compteutilisateur`, pas par `auth`/
  `authentication`).
- `0002_triggers_immuabilite` pose les déclencheurs PostgreSQL, sans effet
  sur SQLite.
- Aller/retour testés sur base vide (tests) et sur la base de
  démonstration peuplée : `migrate habilitations` puis
  `migrate habilitations zero` supprime l'intégralité des tables sans
  toucher aux autres applications.

## 8. Tests

77 tests dans `habilitations/tests/` (objectif U1 : 35) : identité et
doublons, profil et canaux, référentiel et permissions, périmètres et
attributions/dérogations, délégations, politique, journal (immuabilité ORM,
chaînage, détection d'altération), additivité, et déclencheurs PostgreSQL
(2 tests, automatiquement ignorés sur SQLite).

## 9. Périmètre explicitement reporté

Moteur `est_autorise()` et mode observation (U2), 33 rôles et matrice
(U3), écrans React (U4), cycle de vie actif/provisionnement/délégation
effective (U5), MFA/sessions/appareils (U6), campagnes de revue et
tableau de bord (U7), migration des comptes et bascule (U8).
