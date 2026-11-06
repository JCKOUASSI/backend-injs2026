# 08 — Réconciliation des catalogues de rôles (81 / 35, 22 / 11 sensibles)

**Date** : 6 novembre 2026 · **Branche** : `arena/4524a57c-backend-injs2026`
**Objet** : expliquer, preuves à l'appui, l'écart entre les chiffres annoncés
(35 rôles / 11 sensibles dans `catalogue_roles.py`) et l'état de référence
(81 rôles / 22 sensibles / 1 157 permissions).
**Méthode** : lecture et comparaison **sans aucune écriture**. Aucun import,
aucune désactivation, aucune permission modifiée.

---

## 1. Conclusion

| | |
|---|---|
| **Divergence entre le fichier et la base** | **AUCUNE** |
| Rôles dans `catalogue_roles.py` | **81** |
| Rôles en base | **81** |
| Codes absents de la base | `[]` |
| Codes absents du fichier | `[]` |
| Rôles sensibles fichier / base | **22 / 22** |
| Attributs divergents (`sensible`, `niveau_defaut`, `perimetre_defaut`, `module_requis`) | **0** |
| Permissions | **1 157** (intouchées) |

Les chiffres **35** et **11** ne désignent pas le catalogue complet : ils
désignent **la première section du fichier**. Le fichier contient deux sections
qui se cumulent :

```
35 rôles « annexe A1 »      +  46 rôles « cibles module utilisateurs (J2) »  =  81 rôles
11 sensibles A1             +  11 sensibles J2                               =  22 sensibles
```

Le module `catalogue_roles.py` ne déclare qu'**une seule** liste `ROLES` ; les
deux sections y sont concaténées. La mention « 35 rôles » ne figure que dans la
**docstring d'en-tête**, qui décrit la section A1 historique : c'est l'unique
source de la confusion. **Aucune divergence produit, seulement une lecture
tronquée du fichier.**

---

## 2. Preuve de comptage (AST, sans import)

Le fichier déclare ses rôles en **tuples positionnels** : un comptage par
`grep 'code='` ou `grep 'sensible=True'` renvoie 0, ce qui a pu laisser croire à
un fichier plus petit qu'il n'est. Le comptage fiable se fait par analyse
syntaxique (`ast`) :

```
ROLES = [ … ]           → 81 éléments
séparateur              → commentaire « CIBLES PROMPT MODULE UTILISATEURS »
avant séparateur (A1)   → 35 éléments, dont 11 sensibles
après séparateur (J2)   → 46 éléments, dont 11 sensibles
```

Le champ sensible est l'élément d'indice 6 de chaque tuple.

## 3. Comparaison fichier ↔ base (sonde Django, lecture seule)

```
base    : 81 rôles, 22 sensibles, 1 157 permissions
fichier : 81 rôles (35 A1 + 46 J2), 22 sensibles (11 A1 + 11 J2)
codes_absents_de_la_base    : []
codes_absents_du_fichier    : []
attributs_divergents        : []      # sensible, niveau_defaut, perimetre_defaut, module_requis
```

Cette comparaison est désormais **automatisée** : la fonction
`comparer_catalogue_fichier()` du service et le test
`RapportPreviewTests.test_catalogue_concordant_avec_le_fichier` rejouent le
contrôle à chaque exécution de la suite.

## 4. Contenu des deux sections

### 4.1 Section « annexe A1 » — 35 rôles (11 sensibles, marqués `*`)

`ADMIN_SYSTEME *`, `DIRECTION_GENERALE *`, `DIRECTION_ETUDES *`, `SCOLARITE`,
`RESPONSABLE_PEDAGOGIQUE`, `AGENT_CANDIDATURE`, `AGENT_CONTROLE_DOSSIERS`,
`RESPONSABLE_CONCOURS *`, `AGENT_ADMISSIONS`, `AGENT_INSCRIPTIONS`,
`GESTIONNAIRE_ETUDIANTS`, `RESPONSABLE_FORMATION`, `GESTIONNAIRE_GROUPES`,
`GESTIONNAIRE_COURS`, `GESTIONNAIRE_MAQUETTES`, `ENSEIGNANT`,
`RESPONSABLE_UE_ECUE`, `GESTIONNAIRE_CHARGES`, `GESTIONNAIRE_NOTES`,
`MEMBRE_JURY`, `RESPONSABLE_JURY *`, `RESPONSABLE_GRADUATION *`,
`RESPONSABLE_DIPLOMATION *`, `GESTIONNAIRE_FINANCES_ETUD *`,
`VALIDATEUR_FINANCIER *`, `GESTIONNAIRE_VACATIONS *`, `GESTIONNAIRE_STAGES`,
`GESTIONNAIRE_RH *`, `GESTIONNAIRE_PATRIMOINE`, `GESTIONNAIRE_ESPACES`,
`GESTIONNAIRE_COURRIERS`, `ARCHIVISTE`, `ETUDIANT`, `CANDIDAT`, `CONSULTATION`

### 4.2 Section « cibles module utilisateurs (J2) » — 46 rôles (11 sensibles, marqués `*`)

`SECRETARIAT_GENERAL`, `QUALITE_MANAGER`, `AUDITEUR`, `AUDIT_READONLY`,
`PLANIFICATION_MANAGER`, `STATISTICIEN`, `CHEF_DEPARTEMENT`,
`RESPONSABLE_PARCOURS`, `RESPONSABLE_CANDIDATURES`, `CORRECTEUR_CONCOURS`,
`SURVEILLANT_CONCOURS`, `RESPONSABLE_ADMISSIONS`, `RESPONSABLE_INSCRIPTIONS`,
`VACATAIRE`, `RESPONSABLE_EVALUATIONS`, `SECRETAIRE_JURY`, `SIGNATAIRE *`,
`VALIDATEUR_DIPLOMES *`, `ENCADREUR_STAGE`, `TUTEUR_ENTREPRISE`,
`RECHERCHE_MANAGER`, `CHERCHEUR`, `VIE_ETUDIANTE`, `BOURSE_MANAGER *`,
`RESPONSABLE_FINANCES *`, `COMPTABLE`, `CAISSIER`, `RECOUVREMENT`,
`CONTROLEUR_FINANCIER *`, `RESPONSABLE_RH`, `AGENT_RH`, `PAIE_MANAGER *`,
`RESPONSABLE_ADMINISTRATION`, `ACHATS_MANAGER`, `LOGISTICIEN`,
`RESPONSABLE_PATRIMOINE`, `MAINTENANCE`, `GED_MANAGER`,
`COMMUNICATION_MANAGER`, `SUPPORT_IT`, `SYSADMIN *`, `NETWORK_ADMIN *`,
`DB_ADMIN *`, `SECURITY_ADMIN *`, `DATA_ANALYST`, `API_MANAGER *`

Périmètres par défaut de cette section : `DIRECTION`, `FORMATION`,
`INJS_ENTIER`, `MODULE_ECUE`, `PARCOURS`, `PROPRE_COMPTE`.
Modules requis : `administrations`, `admissions`, `edts`,
`finances_etudiantes`, `graduation`, `jurys`, `patrimoine`,
`ressources_humaines`, `scolarite`, `stages`, `statistiques`,
`suiviEvaluation` — **tous présents dans `INSTALLED_APPS`** (le chargeur signale
`roles_indisponibles = 0`).

## 5. Quelle source est réellement utilisée ?

| Source | Rôle |
|---|---|
| `backend/habilitations/referentiel/catalogue_roles.py` | **source de vérité déclarative** (la liste `ROLES`, les `INCOMPATIBILITES`, les niveaux cibles) |
| `backend/habilitations/referentiel/chargement.py` | **unique écrivain** du catalogue : `charger_referentiel()`, idempotent |
| migration `habilitations/0005_charger_referentiel_injs.py` | appelle le chargeur au déploiement (sauf en contexte de test) |
| table `RoleMetier` / `Permission` | **image en base** du fichier |
| services `est_autorise` / `peut` (`services/moteur.py`) | lisent **la base**, jamais le fichier |

Le fichier est la source, la base en est la copie conforme : les services
consomment la base, qui est alimentée par le fichier. Il n'existe donc **pas
deux référentiels concurrents**, mais un référentiel et son image.

> **Attention (règle R5)** : sous `manage.py test`, la migration ne charge pas le
> référentiel (`_en_contexte_de_test()`, sauf `CURP_FORCER_REFERENTIEL=1`). Un
> test qui compare la base au fichier doit donc charger le référentiel
> explicitement, sinon il mesure une base vide et non une divergence produit.

## 6. Ce qui n'a **pas** été fait

Conformément à la consigne, cette réconciliation est une **campagne de mesure** :

- aucun import des 35 rôles A1 (ils sont **déjà** en base) ;
- aucune désactivation, aucun écrasement des 81 rôles existants ;
- aucune modification des 1 157 permissions ;
- aucun `DROP`, `RESET`, `FLUSH` ;
- aucun `--apply` sur une base de production.

## 7. Rappel de l'état de référence

**81 rôles et 1 157 permissions constituent l'état de référence.** Il ne sera
pas modifié au motif d'un catalogue Python qui ne contiendrait que 35 rôles —
et ce cas ne se présente pas : le catalogue en contient 81, identiques à la
base.
