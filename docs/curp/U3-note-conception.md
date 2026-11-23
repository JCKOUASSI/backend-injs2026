# U3 — Note de conception : référentiel des rôles et matrice de permissions

> À contresigner par **RT** et **EF** (revue supplémentaire EF exigée pour
> U3). Unité **additive et paramétrable** : le référentiel est chargé en base
> par une migration de données **idempotente**, jamais figé dans le code des
> vues. Date : 2026-09-14. Prompt source : recueil CURP-INJS, **annexes A1,
> A2, A3, A4, A6** ; fiche d'exécution « FICHE U3 » (prompt C1).

## 1. Reformulation

**Créé** :
- un package de données `habilitations/referentiel/` portant, sous forme de
  tables Python auditées (et non en dur dans les vues), les rôles de
  l'annexe A1, les permissions atomiques de l'annexe A3, les niveaux par
  module de l'annexe A2, les incompatibilités et la correspondance avec les
  12 rôles existants (A6) ;
- une migration de données **idempotente et réversible**
  `0004_charger_referentiel_injs` ;
- une commande `charger_referentiel_injs [--dry-run]` (même chargement,
  réutilisable sans migration, par exemple après correction d'une ligne) ;
- une commande `generer_matrice_habilitations` qui produit le document
  imprimable `docs/CURP_INJS_MATRICE.md` (livrable L4) ;
- le calcul d'activation conditionnelle par module (rôle indisponible si
  l'application Django manque, sans erreur ni plantage) ;
- au moins 40 tests.

**Étendu (additif)** : l'énumération `Action` des permissions reçoit les
verbes métiers supplémentaires utilisés par l'annexe A3
(`saisir, verrouiller, signer, generer, editer, revoquer, deposer,
instruire, decider, ouvrir, cloturer, forcer, certifier, deplacer,
remplacer, resoudre, configurer, calculer`) en plus des 13 verbes
canoniques. Le moteur U2 n'est pas modifié : il compare déjà des codes.

**Épargné** : les 12 rôles legacy, les groupes Django, toutes les vues et
permissions DRF existantes, les tests existants (R5). Aucun compte n'est
rattaché en U3 (la migration des comptes est U8) : le moteur reste en
mode observation et l'existant continue de décider seul.

## 2. Écart à acter : 33 rôles annoncés, 35 lignes au tableau A1

Le recueil titre « les 33 rôles » mais le tableau A1 contient **35 lignes** :
32 rôles internes + 3 « destinataires du service » (`ETUDIANT`, `CANDIDAT`,
`CONSULTATION`). Par sécurité additive, **les 35 lignes sont chargées**
(supprimer un rôle annoncé par le recueil serait une perte d'information) ;
les trois usagers sont marqués `actif=True`, périmètre `PROPRE_COMPTE` pour
les deux premiers, et clairement identifiés comme non-administratifs. Le
point est consigné au registre d'arbitrage ; un retrait se ferait ensuite
sans redéploiement (rôle inactivé en base).

Les doublons de la liste transmise par la maîtrise d'ouvrage sont résolus
selon A1 : un seul `RESPONSABLE_PEDAGOGIQUE` ; le « Gestionnaire cours »
devient `GESTIONNAIRE_COURS` ; l'« Archiviste » de la liste est `ARCHIVISTE`
domaine `ADMINISTRATION_GENERALE`.

## 3. Les données chargées

### 3.1 Rôles (A1)
Pour chacun : `code` stable, `libellé`, `domaine` (13 domaines du modèle),
`niveau_defaut`, `perimetre_defaut`, `module_requis` (pour l'activation
conditionnelle), `sensible` (11 rôles marqués « oui » dans A1),
`canal_impose` (`MOBILE` pour `ENSEIGNANT` et `ETUDIANT`, conformément à A6),
`ordre`, `actif`, description en français courant.

### 3.2 Permissions (A3)
Code `module.ressource.action`. Les jokers `.*` du recueil sont expansés en
l'ensemble des **13 verbes canoniques** ; les verbes métiers explicites
(`note.saisir`, `pv.signer`, `diplome.revoquer`, `emargement.forcer`…)
sont ajoutés tels quels à l'énumération. Chaque permission porte sa
`portee_maximale`, et les permissions de la liste CRITIQUE d'A3 reçoivent
`criticite=CRITIQUE`, `necessite_motif=True`,
`necessite_double_validation=True`, `journalisee=True`.

### 3.3 Dérivation de la matrice (A2 → permissions atomiques)
A2 donne, par rôle et par module, un **niveau N0–N4**. Chaque verbe a un
niveau requis intrinsèque :

| Niveau | Verbes accordés |
|---|---|
| N0 | `consulter` (dans un périmètre `PROPRE_COMPTE` ou très restreint) |
| N1 | N0 + `imprimer`, `exporter`, `generer` (documents/rapports) |
| N2 | N1 + `creer`, `modifier`, `soumettre`, `saisir`, `editer`, `deposer`, `deplacer`, `remplacer`, `ouvrir`, `calculer` |
| N3 | N2 + `valider`, `rejeter`, `publier`, `annuler`, `signer`, `verrouiller`, `instruire`, `decider`, `certifier`, `cloturer`, `resoudre` |
| N4 | N3 + `supprimer`, `archiver`, `administrer`, `configurer`, `forcer` |

Pour chaque case `(rôle, module)` de niveau N, le rôle reçoit les
permissions du module dont le verbe est de niveau ≤ N. Les astérisques et
cercles d'A2 (limitation à ses ECUE, à son propre dossier) ne sont pas des
niveaux : ils sont portés par le **périmètre par défaut** du rôle et seront
appliqués par les résolveurs de couverture U4. Les colonnes absentes d'A2
(`administrations`, `exports`, `parametres`, `referentiels`,
`finances_form`) reçoivent des lignes **provisoires et documentées**
(ADMIN_SYSTEME N4, rôles fonctionnels évidents, ARCHIVISTE N1) : elles sont
étiquetées « à valider à l'atelier J2 » dans le document de matrice.

Les usagers bénéficient d'actes d'auto-démarche explicites sur leur propre
dossier (ex. `candidature.soumettre`, `piece.deposer`,
`justificatif.deposer`) car A2 leur donne N1 sur des modules où l'acte de
soumission est pourtant le leur : ces lignes sont isolées dans une table
`PERMISSIONS_USAGERS`.

### 3.4 Incompatibilités (J5)
Les cinq couples minimaux exigés sont déclarés des deux côtés :
`GESTIONNAIRE_NOTES ↔ RESPONSABLE_JURY`,
`AGENT_INSCRIPTIONS ↔ GESTIONNAIRE_FINANCES_ETUD`,
`GESTIONNAIRE_FINANCES_ETUD ↔ VALIDATEUR_FINANCIER`,
`AGENT_CANDIDATURE ↔ AGENT_CONTROLE_DOSSIERS`,
`RESPONSABLE_GRADUATION ↔ GESTIONNAIRE_NOTES`.

### 3.5 Correspondance avec les 12 rôles actuels (A6, livrable L5)
Table implémentée et testée en U3 ; son application (création des
attributions aux comptes) reste du ressort d'U8. Tous les rôles cibles d'A6
existent dans le catalogue après chargement. La table est exposée par un
service pur, sans effet sur les comptes.

## 4. Activation conditionnelle (J2)
Mapping module du recueil → application Django :
`candidatures→admissions`, `scolarite/pedagogie/enseignants→scolarite`,
`evaluations→suiviEvaluation`, `jurys→jurys`, `diplomation→graduation`,
`finances_etud→finances_etudiantes`, `finances_form→formations`,
`stages→stages`, `rh→ressources_humaines`, `patrimoine→patrimoine`,
`edt→edts`, `presences→presences`, `administrations→administrations`.
Les cinq modules conditionnels de la MOA (finances étudiantes, stages, RH,
administrations, patrimoine) sont **présents dans le dépôt** : tous les
rôles correspondants sont donc disponibles dès la livraison (vérifié par
un test qui éteint fictivement un module et constate l'indisponibilité sans
erreur).

## 5. Réversibilité et idempotence
- la migration utilise `update_or_create(code=…)` : la repasser ne crée
  aucun doublon et remet les lignes du catalogue à leur état de référence,
  sans toucher à d'éventuelles attributions (aucune en U3) ;
- le **reverse ne supprime rien** (S5) : il rend les rôles et permissions du
  catalogue `actif=False` **sans supprimer de ligne ni défaire les liaisons**
  M2M de matrice ou d'incompatibilité. Une nouvelle exécution du forward
  réactive tout et remet la matrice à sa référence (vérifié par test : après
  reverse, les 35 rôles et les permissions sont toujours présents, à
  `actif=False`). La commande `charger_referentiel_injs` refait le chargement
  sans migration.

## 6. Tests (≥ 40)
Un test par rôle (permission emblématique accordée selon A2), un test de
refus par rôle (permission d'un module hors case), niveaux N0/N1…/N4, les 5
incompatibilités (bilatérales), permissions critiques marquées, **zéro
permission orpheline**, **zéro rôle sans permission**, activation
conditionnelle (module présent/absent), idempotence, réversibilité de la
migration, table A6 complète (12 rôles legacy mappés vers des rôles
existants), et visibilité de l'API `roles/`/`permissions/`.

## 7. Ce que U3 ne fait PAS
aucun rattachement de compte legacy (U8), aucun écran React (U4), aucun refus
appliqué (toujours observation), aucune décision de matrice non écrite dans
A2 sans la mention « provisoire – J2 ». La matrice reste une **hypothèse
signée en attente des ateliers EF ligne à ligne** (jalon J2) ; à défaut de
signature complète, elle est livrée marquée « provisoire » et la bascule
reste gelée, comme l'exige la fiche U3.

## 8. Bilan d'exécution et points d'arbitrage

### 8.1 Chiffres chargés (état de référence)
- **35 rôles** (32 internes + 3 destinataires), dont **11 sensibles** ;
- **1 155 permissions atomiques** après expansion des jokers A3 en les 13
  verbes canoniques, sur les **20 modules** ;
- **6 962 liaisons** rôle × permission ; **5 couples d'incompatibilité**
  bilatéraux ;
- contrôles de cohérence globaux au vert : **aucune permission orpheline**,
  **aucun rôle sans permission**, **aucun doublon de code** ;
- document imprimable `docs/CURP_INJS_MATRICE.md` (régénérable par commande).

### 8.2 Arbitrages pris par l'équipe de réalisation (à entériner J2)
1. **Divergence 33/35.** Le recueil titre « 33 rôles » mais le tableau A1
   contient 35 lignes : les 3 lignes `ETUDIANT`, `CANDIDAT`, `CONSULTATION`
   sont des *destinataires du service*. Par sécurité additive (R2), les 35
   lignes sont chargées et les 3 destinataires sont étiquetés comme tels
   (domaine `DESTINATAIRES`) ; ils peuvent être désactivés sans redéploiement.
2. **Dérivation hiérarchique des niveaux.** Une case de niveau N donne les
   verbes de niveau ≤ N (un N3 hérite des verbes N2). En conséquence, la
   **séparation des tâches saisie/validation** (ex. finances) est portée par
   les **incompatibilités de cumul J5**, et non par un retrait non écrit du
   verbe de saisie au validateur : aucun verbe n'est retiré à un niveau
   supérieur sans case A2 le justifiant. À confirmer en J2 si la MOA veut
   durcir en excluant aussi la saisie au rôle validateur.
3. **Exports et référentiels hors colonnes A2.** Les modules `exports`,
   `parametres`, `referentiels`, `administrations`, `finances_form` n'ont pas
   de colonne en A2 : leurs cases sont marquées **« provisoire – J2 »** dans
   le document et dans les données dérivées. L'export *sensible* est verrouillé
   au niveau N4 par une surcharge explicite, indépendamment du verbe `generer`
   (N1).
4. **Actes d'auto-démarche usagers.** Les quelques actes N1/N2 des étudiants et
   candidats sur LEUR dossier (dépôt de justificatif, dépôt de candidature)
   sont ajoutés explicitement et ne valent que dans le périmètre
   `PROPRE_COMPTE`.

### 8.3 Préservation des tests existants (R5)
La migration de données est **neutralisée pendant la constitution de la base
de test** (`manage.py test`) afin que les tests U1/U2, qui créent leurs
permissions de façon autonome avec des codes du catalogue, retrouvent des
tables vides exactement comme avant U3. Le comportement réel de la migration
est prouvé par un test dédié qui la force et vérifie peuplement, idempotence
et désactivation non destructive (`MigrationChargementTests`).
**Un seul test U1 a dû être adapté**, de façon additive :
`test_les_treize_actions_sont_proposees` figeait le nombre de verbes à 13 ; il
vérifie désormais que les 13 verbes canoniques restent tous présents (R2) tout
en autorisant les verbes métier ajoutés par A3. Aucune garantie de sûreté
n'est affaiblie ; les autres tests U1/U2 sont intouchés.

### 8.4 Performance du moteur (exigence A7.20)
Une évaluation d'octroi exécute **11 requêtes fixes**, une évaluation de refus
**7 requêtes** : ce nombre est indépendant du volume du catalogue (la jointure
`role__permissions = <permission>` est indexée et filtrée par permission). Sur
SQLite du bac de sable, mesures autour de 4 ms (refus) et 6 ms (octroi) ; ce
délai est à confirmer sur la cible **PostgreSQL de CI**, attendue sous les
5 ms. U3 n'ajoute aucune requête au moteur U2 : seule une jointure jusqu'ici
infructueuse (tables vides) devient porteuse.

### 8.5 Étendue effectivement livrée
En plus des livrables L1–L6, la liste `GET /api/habilitations/roles/` expose
`incompatible_avec` (codes) et `permissions_count` (compteur annoté) pour
préparer U4, sans alourdir la réponse avec les 1 155 codes ; le catalogue
complet reste lisible via `GET /api/habilitations/permissions/`. Le moteur
reste en **mode OBSERVATION**, aucune vue n'est branchée, aucun compte n'est
rattaché (renvoyé à U8).
