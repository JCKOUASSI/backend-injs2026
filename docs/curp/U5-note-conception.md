# U5 — Note de conception : cycle de vie, provisionnement, imports et délégation (prompt C3)

> Unité I5, dépend d'U4 (livrée), bloque U8. Statut de cette note :
> **hypothèses de réalisation pour la tranche démo < 24 h**, à contresigner
> par le RS et l'EF (deux approbations prévues par le plan pour U5).
> Aucune règle métier non écrite dans les prompts n'est introduite ; tout
> automatisme est **additif, inactif par défaut et extinguible sans
> redéploiement** (principe de repli de la fiche).

## 1. Principe directeur : l'humain reste aux points de décision

C3 : « Automatiser ce qui peut l'être… en gardant l'humain aux points de
décision. » Traduction pour U5 :

- les **sondes événementielles** ne créent jamais de compte : elles déposent
  une **proposition dans une file de validation humaine** ;
- aucune suspension, désactivation ou création n'est appliquée sans
  approbation explicite tracée d'un responsable (à l'exception de
  l'**expiration à terme convenu**, voir §5, qui n'est pas une décision
  nouvelle mais l'application d'une date déjà approuvée à la création) ;
- chaque déclencheur a son **propre drapeau**, tous **OFF par défaut** ; un
  drapeau maître `flag.curp_provisionnement_auto` doit aussi être ouvert
  (double sécurité, extinction immédiate globale).

## 2. Machine à états stricte (A5) — L1

La table plate de transitions U4 devient un **graphe dirigé valide selon
l'annexe A5** :

```
(création) → INVITE ──(1re connexion + changement MDP)→ ACTIF
INVITE ──(invitation expirée)→ EXPIRE
ACTIF ──→ SUSPENDU (décision admin, durée bornée)
ACTIF ──→ VERROUILLE (échecs répétés / auto)
ACTIF ──→ DESACTIVE (départ, fin de relation, décision)
ACTIF ──→ EXPIRE (date d'expiration atteinte)
SUSPENDU ──(réactivation motivée)→ ACTIF
VERROUILLE ──(déverrouillage auto ou admin)→ ACTIF
DESACTIVE ──(réactivation exceptionnelle motivée)→ ACTIF
```

- Une transition depuis un état source non prévu est **refusée (409
  `TRANSITION_ILLEGALE`)** et **journalisée comme tentative** (cohérence S6
  : les tentatives interdites sont tracées).
- Chaque transition garde : permission, motif obligatoire, écriture au
  journal, miroir `User.is_active`, et la garde des deux administrateurs (S7).
- Le verrouillage automatique et l'expiration ont leur transition propre
  (`verrouiller`, `expirer`) ; aucun retour n'est prévu depuis `EXPIRE`
  (stricte lecture d'A5 : une nouvelle invitation est alors nécessaire).
- Les notifications à l'intéressé (A5 : « notification de l'intéressé »)
  sont matérialisées par une `NotificationHabilitation` en base (le SMTP
  n'existe pas dans le sandbox ; en production ces mêmes notifications sont
  celles que le canal d'envoi existant reprendra — aucun envoi n'est
  simulé).

## 3. Provisionnement événementiel et file de validation — L2

Nouveau modèle `PropositionProvisionnement` (file) :

- champs : `declencheur`, `action_proposee`
  (CREER_COMPTE / ACTIVER_COMPTE / ATTRIBUER_ROLE / SUSPENDRE_COMPTE /
  DESACTIVER_COMPTE), référence de l'objet métier source sous forme
  **découplée** (`source_app`, `source_modele`, `source_objet_id`,
  `source_libelle` — pas de FK vers les apps métier, pour éviter tout
  couplage fort), charge utile JSON `proposition` (identifiant suggéré,
  personne, rôles, périmètres, canal), `statut`
  (EN_ATTENTE / APPROUVEE / APPLIQUEE / REJETEE / ANNULEE), clé de
  déduplication unique, acteur d'approbation/rejet, motifs, dates.
- **Idempotence** : une clé `(declencheur, source_app, source_modele,
  source_objet_id, action)` unique empêche qu'un même fait génère deux
  propositions.
- **Plafond quotidien** (réglage `plafond_quotidien_propositions`, défaut
  50) : au-delà, les propositions excédentaires ne sont pas mises en file
  et une notification d'alerte `ALERTE_PLAFOND` est émise (risque
  « création en masse par erreur lors d'une reprise »).

Les six sondes lisent les modèles métier réels, de façon **défensive**
(imports tolérants ; une app absente ne fait que rendre la sonde vide) :

| Déclencheur (drapeau) | Source réelle | Proposition |
|---|---|---|
| `…_admission` | `admissions.Admission` décision ADMIS/ADMIS_SOUS_RESERVE | CREER_COMPTE étudiant : rôle `ETUDIANT`, rôle legacy `AUDITEUR`, canal MOBILE |
| `…_inscription` | `scolarite.InscriptionAdministrative` VALIDEE | ACTIVER_COMPTE + périmètres (formation/niveau/groupe) |
| `…_recrutement` | `ressources_humaines.Agent` ACTIF sans compte | CREER_COMPTE agent (rôle à compléter par le valideur si non déductible) |
| `…_affectation_enseignant` | `scolarite.AffectationPedagogique` (formateur affecté à un ECUE) | ATTRIBUER_ROLE `ENSEIGNANT` (+ périmètres ECUE), legacy `FORMATEUR`, MOBILE |
| `…_fin_relation` | `Agent.date_sortie` / `InscriptionAdministrative` TERMINEE / fin de vacation, après délai de grâce | SUSPENDRE_COMPTE (la désactivation reste un geste admin ultérieur) |
| `…_jury` | `jurys.MembreJury` (membre désigné, `user` existant) | ATTRIBUER_ROLE `MEMBRE_JURY` (+ périmètre FORMATION de la session) ; sans compte CURP, la création passe par l'écran U4 |

La sonde jury observe `jurys.MembreJury`, qui référence déjà un `User`
existant (FK PROTECT) : la sonde ne propose donc **que** l'attribution du
rôle `MEMBRE_JURY` aux utilisateurs qui ont déjà un compte CURP, bornée
sur la formation de la session de jury. Un membre désigné sans compte CURP
ne génère aucun fait : sa création reste une décision humaine depuis la
fiche de compte (écran U4) — aucun rôle d'accès n'est deviné
automatiquement. Le rôle d'approbation cible `MEMBRE_JURY` (catalogue,
borné sur FORMATION) ; la fonction (président/secrétaire/membre) est
consignée dans le motif pour aide à la décision.

L'approbation réutilise les services U4 (`creer_compte`, `changer_statut`,
`_appliquer_roles`) dans une transaction, avec le motif de l'approbateur.
Le rejet exige un motif et clôt la proposition (l'objet métier n'est pas
touché ; une nouvelle sonde pourra représenter la proposition ultérieurement
si la source change, via une nouvelle clé d'idempotence datée).

## 4. Imports en masse transactionnels et réversibles — L3

- Nouveau modèle `ExecutionImport` (référence `IMP-AAAAMMJJ-NNNN`, statut
  EN_COURS / TERMINE / ECHEC / ANNULE, totaux, rapport ligne à ligne JSON,
  acteur, dates, motif d'annulation). `CompteUtilisateur.import_execution`
  lie chaque compte créé.
- **Exécution en une transaction** : toutes les lignes sont revalidées
  immédiatement avant écriture (l'aperçu date parfois) ; une seule ligne
  invalide ou un doublon apparu entre-temps fait **tout échouer**
  (409 `IMPORT_NON_VALIDE`), rien n'est écrit, et l'import corrigé peut être
  rejoué (nouvelle exécution).
- **Réversibilité par identifiant d'exécution** : « un import raté
  s'annule d'un seul geste ». Conformément à **S5 (aucune suppression
  physique)**, l'annulation **désactive** les comptes créés par
  l'exécution (statut DESACTIVE, miroir `is_active=False`, motif
  `Annulation de l'import IMP-…`, journal ligne par ligne) ; les comptes
  déjà exploités après l'import sont aussi désactivés, jamais supprimés,
  et leur historique demeure. L'annulation exige un motif (double commande).
- Drapeau dédié `flag.curp_import_masse` (OFF = l'aperçu U4 reste seul
  disponible, l'écriture répond 403/409).

## 5. Expiration et inactivité

- Commande `expirer_habilitations` (drapeau `flag.curp_expiration_auto`)
  : passage ACTIVE→EXPIREE / TERMINEE à `date_fin` atteinte pour les
  attributions temporaires, dérogations et délégations ; **notification
  J-7** (une seule, horodatée sur l'objet) à l'intéressé. C'est
  l'application du terme convenu, pas une décision nouvelle : automatique.
- Commande `detecter_inactivite` (drapeau `flag.curp_suspension_inactivite`
  ; durée `inactivite_suspension_jours` défaut **180**, préavis
  `preavis_suspension_jours` défaut **15**, généreux au départ comme exigé)
  : à J-15 elle notifie l'agent et son responsable ; à échéance elle
  **dépose une proposition SUSPENDRE_COMPTE dans la file**, elle ne suspend
  pas elle-même : « jamais de suspension silencieuse » et règle générale
  d'approbation humaine de C3. `CompteUtilisateur.exempt_inactivite` porte
  les exemptions déclarables (congé longue durée).
- Commande `provisionnement_scanner` : lance les sondes actives (cinq
  événementielles métier + la sonde jury).

Ces trois commandes sont idempotentes et conçues pour être appelées par la
planification de production (quotidienne) ; en sandbox elles se lancent à
la main et via un bouton de l'écran de file pour la démonstration.

## 6. Délégation renforcée — L4

Le modèle U1 porte les données ; U5 applique les contrôles côté service et
API (backend seule source de vérité, S3) :

- **on ne délègue que ce que l'on détient** : chaque rôle (et permission
  explicite) doit figurer dans les attributions ACTIVES directes du
  délégant, et la `date_fin` de la délégation ne peut excéder le terme de
  ses attributions ; les périmètres délégués doivent être inclus dans les
  siens.
- **pas de re-délégation** : un droit qui n'arrive au délégant que par une
  délégation reçue ne peut être re-délégué (on compare aux seules
  attributions directes).
- durée **obligatoirement bornée** (déjà en U4), pas de délégation à
  soi-même (déjà), **fin anticipée** motivée (déjà), **extinction
  automatique** par la commande d'expiration.
- la délégation est créée PROPOSEE et **activée** par un administrateur
  (`POST delegations/<id>/activer/`) ; seule une délégation ACTIVE produit
  ses effets (le moteur U2 vérifiait déjà les délégations actives).
- **traçabilité des actions par délégation** : le journal reçoit un lien
  `delegation_source` ; un service `journaliser_action_deleguee()` et un
  endpoint `POST delegations/<id>/action/` permettent à toute application
  métier (branchement plus large à U8) d'enregistrer l'action avec mention
  du délégant. Refus si le demandeur n'est pas le délégataire ou si la
  délégation n'est pas active.

## 7. Notifications

`NotificationHabilitation` (destinataire User, compte lié, catégorie,
titre, message, lu/date de lecture, métadonnées) : préavis d'inactivité,
échéances J-7, alerte de plafond, propositions à instruire. Endpoints de
liste et marquage comme lu. Aucun envoi SMTP n'est supposé (absent du
sandbox) : la notification en base est le support traçable et le point
d'accroche du canal d'envoi de production.

## 8. Périmètre livré et replis

**Livré en U5 (tranche démo)** : L1 machine à états stricte, L2 file +
six sondes drapeautées (dont la sonde jury, ajoutée à la demande) +
plafond, L3 import transactionnel et annulable,
L4 délégation complète (contrôles, activation, extinction, action tracée),
commandes planifiables, écran de file, finalisation de l'écran d'import et
de l'écran délégations, ≥ 30 tests backend et tests Vitest des nouveaux
parcours.

**Hors périmètre (unités suivantes)** : campagnes de revue signées (U7),
MFA/sessions/appareils (U6), migration des comptes et bascule (U8),
vrais emails/SMS et calendrier système (les commandes sont prêtes à être
planifiées), application effective du moteur d'autorisation (reste en
observation jusqu'à U8).

**Repli** : chaque interrupteur (7 drapeaux : maître, 5 déclencheurs,
expiration, inactivité, import en écriture) est indépendant et OFF ; les
nouveaux endpoints restent de plus gardés par `ExigeDrapeauAdmin` (le
drapeau U4 continue de commander l'accès à la console). L'écran
Utilisateurs legacy et l'admin Django ne sont pas touchés.

## 9. Bilan de réalisation (livraison)

### Commandes planifiables (quotidiennes, idempotentes)
- `manage.py provisionnement_scanner [--declencheur …]` : alimente la file
  depuis les sondes activées (maître + drapeau dédié) ; no-op total si OFF.
- `manage.py detecter_inactivite` : préavis J-15 à l'agent et au responsable,
  puis proposition de suspension en file (jamais de suspension directe) ;
  tient compte de `exempt_inactivite`.
- `manage.py expirer_habilitations` : attributions/dérogations à EXPIREE,
  délégations à TERMINEE, invitations anciennes à EXPIRE, comptes à date
  échue ; préavis J-7 émis une seule fois (`notification_echeance_le`).

### Routes ajoutées (11, portant le total console à 34)
`propositions/` (liste + compteurs), `propositions/<id>/approuver|rejeter/`,
`provisions/scanner/`, `comptes/imports/`, `comptes/imports/<ref>/`,
`comptes/imports/<ref>/annuler/`, `notifications/`,
`notifications/tout-lire/`, `notifications/<id>/lire/`,
`delegations/<id>/activer/`, `delegations/<id>/action/`.

### Vérifications exécutées
- **47 tests backend U5** : machine A5 (toutes les flèches, refus tracés,
  révocation de sessions), sondes/file (OFF=no-op, dédup, plafond/alerte,
  approbation, rejet/redépôt, rôle à compléter), inactivité (préavis,
  exemption, file), expiration (J-7, terme, invitations, délégations),
  import (aperçu, échec total sans écriture, rejeu, exécution, annulation
  démontrée sur 100 lignes, doubles annulations), délégation (détention,
  re-délégation, hors-terme, activation, action tracée avec délégant) et
  les parcours API.
- **9 tests Vitest** des nouveaux écrans ; 1523 tests front au total verts.
- Migrations `habilitations 0006/0007` et `parametres 0006` réversibles
  (aller/retour vérifiés) ; suite backend globale verte à l'exception d'un
  test référentiel déjà en échec sur la tête U4 (SQLite insensible à la
  casse, sans lien avec U5).
- Démo G2 roulée en transaction annulée : 100 comptes créés (MOBILE/AUDITEUR
  déduits, référence `IMP-20260914-0001`), puis 100/100 désactivés par
  annulation, 0 utilisateur supprimé physiquement.
- A5 complétée : toute transition rendant le compte inactif révoque les
  sessions Django actives et journalise `SESSION_REVOQUEE`.
