# Audit comparatif des bases INJS — historique `injs-db` → cible `injs_lmd_prod_20261026`

**Date** : 2026-11-05
**Périmètre** : PostgreSQL 15 (VPS AlmaLinux) — `injs-db` (historique) et `injs_lmd_prod_20261026` (cible)
**Référentiel applicatif** : `backend-injs2026`, `main` @ `767dabf0faf317c333d280248ebf93fe4ad66ea6` (PR #4 fusionnée, CI verte)
**Nature** : audit, strictement en lecture seule. Aucune migration exécutée, aucun service touché.

---

## Correspondance avec votre cahier des charges

| Livrable demandé | Section |
|---|---|
| A. Synthèse exécutive | §1 |
| B. Inventaire des données | §2 |
| C. Anomalies historiques (quantifiées) | §3 — méthode livrée, chiffres **non mesurés** (voir §0) |
| D. Matrice de correspondance | §4 |
| E. Données potentiellement récupérables | §7 |
| F. Plan de migration recommandé | §8 |
| G. Décision finale par domaine | §10 |
| H. Vérifications encore nécessaires | §9 |
| Audits A à F du cahier des charges | §2 à §6 |

---

## 0. Statut d'exécution — à lire avant tout le reste

L'audit demandé comporte deux volets. Un seul a pu être exécuté, et ce document ne prétend pas le contraire.

| Volet | Exécuté ? | Preuve / raison |
|---|---|---|
| **Inventaire de la cible** (structure, modèle par modèle, contraintes, migrations) | ✅ **Oui**, intégralement | introspection Django hors ligne sur le code de `main@767dabf` ; résultats reproductibles (§2) |
| **Règles métier INJS dans le code** (filières, semestres, ECTS, inscriptions) | ✅ **Oui** | lecture du code et des commandes de référentiel (§5) |
| **Inventaire de la base historique** (colonnes, contraintes, volumes exacts) | ❌ **Non** | aucune connexion possible aux bases du VPS (§0.1) |
| **Quantification des anomalies historiques** | ❌ **Non** | dépend de l'accès ci-dessus |
| **Volumes cible réels** (compter les lignes dans `injs_lmd_prod_20261026`) | ❌ **Non** | idem |

### 0.1 Pourquoi les bases n'ont pas pu être interrogées

Une sonde a été exécutée une seule fois, sans mot de passe, sans écriture :

```
$ ssh -o BatchMode=yes -o ConnectTimeout=15 almalinux@152.228.233.123 true
kex_exchange_identification: read: Connection reset by peer
Connection reset by 152.228.233.123 port 22

$ timeout 10 bash -c 'exec 3<>/dev/tcp/152.228.233.123/22; head -c 60 <&3'
(aucune bannière — flux réinitialisé)
```

Le proxy de sortie de l'environnement d'audit accepte le TCP puis réinitialise le protocole : **aucune session SSH, donc aucun `psql`, aucun `docker exec`** vers le VPS. Le client `psql` n'était pas installé dans cet environnement ; un binaire a ensuite été installé **localement** uniquement pour valider les scripts sur des bases témoins jetables (§0.2) — il n'a aucun accès aux données réelles. Il n'existe aucun contournement depuis cet environnement ; les seules voies sont une exécution sur le Mac (§9) ou sur le VPS.

**Conséquence** : les chiffres de la base historique cités dans ce rapport sont **ceux que vous avez établis** (73 tables, 327 migrations, 111 comptes, 89 étudiants, 305 inscriptions, 96 dossiers, 136 cours, 88 UE, 14 promotions, 5 années, 4 programmes, 10 semestres, 1 599 présences, 368 séances, 50 emplois du temps, 44 affectations, 3 enseignants, 185 salles). Ils sont repris **tels quels, sans re-mesure**, et signalés comme tels dans chaque tableau.

### 0.2 Ce qui a été livré à la place

Un **pack de collecte exécutable en lecture seule** (§9, `docs/audits/sql/`) qui produit exactement les mesures manquantes. Ses trois scripts ont été **réellement exécutés et validés** contre deux schémas témoins PostgreSQL créés pour l'occasion (type historique et type cible) : 0 erreur, et toutes les anomalies volontairement introduites ont été détectées.

---

## 1. Synthèse exécutive — livrable A

### 1.1 État réel des deux bases

| | `injs-db` (historique) | `injs_lmd_prod_20261026` (cible) |
|---|---|---|
| Rôle | base de l'application héritée | base de `backend-injs2026` |
| Tables | 73 (votre mesure, non re-mesurée) | **222 attendues** d'après le code ; 203 annoncées → écart à trancher (§2.3) |
| Applications | domaines `academics`, `students`, `admissions`, `exams`, `faculty`, `accounts`, `finance`, `library` | **21 applications métier** + 4 applications Django (25 installées) |
| Migrations | 327 enregistrées (héritage) | 257 fichiers de migration dans le code ; état réel en base à relever |
| Modèle utilisateur | `accounts_user` (111 comptes) | `authentication.User` + couche `habilitations` (1 compte) |
| Données métier | volumineuses (305 inscriptions, 1 599 présences, notes, jurys, finances) | quasi vides (votre constat) |

### 1.2 Constat structurant découvert pendant l'audit

La base cible **n'est pas une base LMD « pure »** : elle superpose deux générations de modèle.

1. Un **socle hérité (`formations`)** : `Formation`, `Module`, `SessionModule`, `Participant`, `Formateur`, `RefFormation`, `RefVague`, `RefSalle`, `NoteModule`…
2. Une **couche LMD (`scolarite`, `evaluations`, `jurys`, `edts`, `presences`)** : `AnneeAcademique`, `RefFiliere`, `Maquette`, `UE`, `ECUE`, `InscriptionAdministrative`, `InscriptionPedagogique`, `SessionEvaluation`, `SessionJury`…

Ces deux mondes sont reliés par un **pivot unique**, et c'est le fait le plus important de tout l'audit :

```
formations.Participant  ←— (PROTECT, unique) — scolarite.DossierEtudiant
                                                     ↑ PROTECT
                                     scolarite.InscriptionAdministrative
                                                     ↓ CASCADE
                                     scolarite.InscriptionPedagogique → ECUE
```

**Conséquence directe** : aucun étudiant ne peut exister dans la cible uniquement comme « dossier » ; il doit **aussi** exister comme `formations.Participant` (`matricule` UNIQUE). Toute reprise d'étudiants est donc une reprise à **deux tables obligatoirement liées**, pas une simple copie de `students_student`.

### 1.3 Volume potentiellement réutilisable et niveau de compatibilité

| Niveau | Domaines | Volume historique concerné (vos chiffres) |
|---|---|---|
| **Directe / transformable** | années académiques, salles, étudiants+dossiers, comptes | 5 années, 185 salles, 89 étudiants / 96 dossiers, 111 comptes |
| **Sous conditions** | inscriptions, présences, notes, enseignants | 305 inscriptions, 1 599 présences, 3 enseignants |
| **Partielle** | cours → ECUE, emplois du temps, affectations | 136 cours, 88 UE, 50 EDT, 44 affectations |
| **Audit métier complémentaire** | programmes → filières, examens → sessions d'évaluation, jurys, finances | 4 programmes, examens/notes, jurys, finances |
| **Abandon** | bibliothèque (aucune application cible), Celery | — |

### 1.4 Principaux risques

1. **Le pivot étudiant** (Participant + DossierEtudiant) : oublier l'un des deux rend l'étudiant inutilisable dans la cible.
2. **Unicité du matricule à trois endroits** (`Participant.matricule`, `User.username`, `User.matricule`) : tout doublon historique bloque l'import, et le nettoyage est une décision métier.
3. **Référentiel daté** : `referentiels.RefFiliere` porte une clé étrangère vers `AnneeAcademique` ; une filière existe *pour une année*. On ne peut pas importer des filières « hors année ».
4. **F05 à F08 n'ont aucun cycle LMD** dans le référentiel source (cf. §5.1) : les données historiques rattachées à ces filières ne peuvent pas être accrochées à un cursus LMD sans décision explicite.
5. **Inscription pédagogique = une ligne par ECUE** : 305 inscriptions historiques se traduisent potentiellement en plusieurs milliers de lignes ; la volumétrie doit être estimée avant tout import.
6. **Notes calculées** : la cible recalcule (`SemesterResult`, `UEResult`, `ECUEResult`) à partir de `RegleCalculVersion`. Importer des résultats calculés produirait des données fausses dès la première session.

---

## 2. Inventaire des données — livrable B

### 2.1 Base historique — non mesurée dans cet audit

Domaines et volumes **tels que vous les avez établis** :

| Domaine | Tables annoncées | Volumes annoncés |
|---|---|---|
| `academics` | (non détaillé) | 5 années, 4 programmes, 14 promotions, 10 semestres |
| `students` | (non détaillé) | 89 étudiants, 305 inscriptions, 96 dossiers |
| `faculty` | (non détaillé) | 3 enseignants, 136 cours, 88 UE, 44 affectations, 50 EDT, 368 séances, 1 599 présences, 185 salles |
| `exams` | (non détaillé) | examens + notes présents |
| `accounts` | (non détaillé) | 111 comptes |
| `finance`, `library`, `admissions` | (non détaillé) | présents, non chiffrés |

**Aucune colonne, clé ou contrainte de la base historique n'a pu être vérifiée** : c'est précisément ce que la collecte §9 fournira (script `00_profil_schema.sql`).

### 2.2 Base cible — inventaire vérifié (introspection du code)

Totaux réels : **202 modèles**, **19 tables de liaison M2M**, **202 + 19 + `django_migrations` = 222 tables physiques attendues**, **21 applications métier** (+ `admin`, `auth`, `contenttypes`, `sessions` = 25 applications installées, ce qui correspond à votre chiffre de « 25 applications migrées »).

| Application | Modèles | Clé primaire | Rôle métier |
|---|---|---|---|
| `formations` | 27 | `BigAuto` | socle hérité : formations, modules, séances, participants, formateurs, salles, vagues |
| `scolarite` | 22 | `BigAuto` | LMD : année, niveau, semestre, parcours, maquette, UE, ECUE, groupe, inscriptions, dossiers |
| `evaluations` | 17 | `BigAuto` | sessions d'évaluation, épreuves, notes, résultats calculés, règles de calcul |
| `referentiels` | 17 | `BigAuto` | écoles, mentions, filières, cursus, grades, types (évaluation, décision, frais…) |
| `habilitations` | 15 | `BigAuto` | comptes, rôles métier, permissions, périmètres, délégations, journal |
| `admissions` | 15 | `BigAuto` | campagne, candidat, candidature, concours, pièces, admission |
| `edts` | 14 | `BigAuto` | emplois du temps, créneaux, affectations, registre de séance, géolocalisation |
| `finances_etudiantes` | 9 | `BigAuto` | tarification, facture, échéancier, paiement, quittance, relance, remboursement |
| `suiviEvaluation` | 8 | `BigAuto` | questionnaires, questions, réponses, décisions pédagogiques |
| `administrations` | 7 | `BigAuto` | départements, directions, courriers, réunions, documents |
| `patrimoine` | 7 | `BigAuto` | équipements, inventaire, maintenance, véhicules, réservations |
| `presences` | 6 | `BigAuto` | pointages, encadrants, notifications d'absence, rattrapages, appareils |
| `jurys` | 6 | `BigAuto` | session de jury, membres, propositions, décisions, PV, notifications |
| `ressources_humaines` | 6 | `BigAuto` | agents, services, fonctions, affectations, disponibilités |
| `statistiques` | 5 | `BigAuto` | rapports, observations, signatures, alertes de seuil |
| `graduation` | 4 | `BigAuto` | diplômes, registre, modèles de document, rééditions |
| `stages` | 4 | `BigAuto` | conventions, organismes, tuteurs, évaluations de stage |
| `equivalences` | 3 | `BigAuto` | demandes, pièces, historique |
| `core` / `parametres` / `authentication` / `sessions` | 2 / 2 / 1 / 1 | `BigAuto` | audit, paramètres, compte utilisateur, sessions |
| **Total** | **202** | **100 % entiers** | aucun UUID en clé primaire |

**Points de structure vérifiés** (utiles à la migration) :

- Aucune clé primaire UUID : toutes les PK sont des entiers auto-incrémentés. Les UUID n'existent qu'en champs secondaires uniques (`DossierEtudiant.uuid`, `SeanceRegistre.uuid`, `Candidat.uuid`).
- Contraintes d'unicité les plus contraignantes pour une reprise : `Participant.matricule`, `User.username`, `User.matricule`, `RefFormation.intitule`, `AnneeAcademique.libelle`, `SeanceRegistre.cle_metier`, `Formateur.numerobadge`.
- Unicités **fonctionnelles ou partielles** (pièges classiques d'import) :
  - `UE` : `(maquette, Lower(code))` — unicité **insensible à la casse** ;
  - `ECUE` : `(ue, Lower(code))` ; `Groupe` : `(annee, formation, niveau, Lower(nom))` ; `Parcours` : `(formation, Lower(code))` ;
  - `AnneeAcademique` : `libelle` UNIQUE + **une seule** année `courante = true` (index partiel) + `CHECK (date_fin > date_debut)` + `CHECK NOT (cloturee AND courante)` ;
  - `InscriptionAdministrative` : `(etudiant, annee, formation, parcours, niveau)` unique **seulement si `statut = VALIDEE`** — les inscriptions non validées peuvent donc se dupliquer ;
  - `InscriptionPedagogique` : `(inscription, ecue)` unique ;
  - `Maquette` : `(annee, formation, parcours, niveau, version)` unique ;
  - `SessionEvaluation` : `(annee, formation, niveau, coalesce(semestre,0), coalesce(parcours,0), type_session)` ;
  - `EmploiDuTemps` : `(annee, population_type, population_id, version)` — `population_id` est une **référence générique** (décision de conception à connaître avant import) ;
  - `Evaluation` : `CHECK poids ∈ ]0,100]`, `CHECK bareme > 0` ; `RegleValidationLMD` : une règle par `(formation, niveau)` **plus** une règle par défaut par formation (`niveau IS NULL`).
- 257 fichiers de migration dans le code, dont 101 pour `formations` seul (socle le plus remanié).

### 2.3 Écart 203 vs 222 tables — réconcilié, puis à confirmer en base

Votre relevé annonce **203 tables** ; le code de `main@767dabf` implique **222** tables physiques.

Hypothèse la plus probable, cohérente au table près : **203 = 202 tables de modèles + `django_migrations`**, c'est-à-dire un comptage **au niveau des modèles**, qui omet les **19 tables de liaison M2M** (`authentication_user_groups`, `habilitations_rolemetier_permissions`, `formations_refmodule_formations`, …). Dans ce cas, aucune table ne manque en production.

Cette hypothèse **n'est pas une conclusion** : elle se vérifie en une requête (script `00_profil_schema.sql`, sections 2 et 3) puis en comparant la liste obtenue au fichier `docs/audits/tables_cibles_attendues.txt` (222 lignes). C'est le point n°2 des vérifications restantes (§8).

---

## 3. Anomalies historiques — livrable C

**Aucune anomalie n'a été mesurée.** Toute quantification serait inventée ; ce serait exactement l'erreur à éviter. Voici la matrice de mesure qui sera remplie par la collecte, avec la gravité associée au type d'anomalie.

| Catégorie d'anomalie | Méthode de mesure (script §9) | Gravité si non nulle | Conséquence sur la reprise |
|---|---|---|---|
| FK non validées (`convalidated = false`) | `10_anomalies.sql` §A | Élevée | orphelins possibles partout en aval |
| Références orphelines | §B (toutes les FK, comptage) | Élevée | lignes non reprenables telles quelles |
| Colonnes texte obligatoires vides | §C | Moyenne | `matricule`/`nom` vides ⇒ rejet à l'import |
| Dates incohérentes (modif < création) | §D | Faible | traçabilité seulement |
| Doublons sur clés naturelles | §E (`matricule`, `code`, `numero`) | **Critique** | blocage direct par les contraintes uniques de la cible |
| Statuts non reconnus | §I (distribution des codes) | Moyenne | décisions métier (jury, finance) mal interprétées |
| Algorithme de hachage des mots de passe | §H (comptage par préfixe) | Moyenne | réinitialisation en masse ou non |
| Orphelins métier cibles (étudiant sans inscription, UE sans semestre, pointage sans support, etc.) | §F | Moyenne | contrôle d'acceptation après import |

Les catégories nommées dans la mission (inscription sans étudiant, cours sans programme, promotion sans formation, séance sans EDT, présence sans séance, affectation sans enseignant, évaluation sans cours, note sans évaluation…) seront mesurées par les orphelins §B **si** des FK existent, et par jointures explicites à écrire après la collecte (le nom exact des colonnes historiques est inconnu à ce stade).

**Aucune anomalie ne sera qualifiée de « défaut » sans examen de la contrainte correspondante** : ainsi, l'absence d'unicité sur `(formation, Lower(code))` dans l'historique n'est pas une anomalie en soi ; ce serait un doublon *fonctionnel* seulement si le métier garantit l'unicité — ce que la cible, elle, impose.

---

## 4. Matrice de correspondance historique → cible — livrable D

Classes : **DIRECTE** (structure et sens prouvés) · **TRANSFORMABLE** (conversion documentée) · **PARTIELLE** (une partie seulement est récupérable) · **À VÉRIFIER** (sens/provenance non établis) · **NON REPRENABLE**.

Les noms de tables sources sont ceux de votre inventaire ; **ils ne sont pas vérifiés par cet audit** (à confirmer par la collecte). Les cibles sont, elles, vérifiées dans le code.

| Domaine | Source (historique) | Cible (vérifiée) | Correspondance | Transformation requise | Risque | Décision |
|---|---|---|---|---|---|---|
| Années académiques | `academics_*` (5) | `scolarite_anneeacademique` | **TRANSFORMABLE** | normaliser `libelle`, recalculer `date_debut/date_fin`, une seule `courante` | libellé déjà présent ; `CHECK` sur les dates | Reprise sous conditions |
| Programmes / formations | `academics_program` (4) | `referentiels_reffiliere` (code, `code_dossier` F01–F08, `annee_academique`, école, mention, cursus) + `formations_refformation` (`intitule` UNIQUE, `filiere_code`, `type_diplome`) | **PARTIELLE** | réconciliation 4 programmes → 8 filières + cycles LMD **par le code dossier**, jamais par le libellé | filière datée par année ; F05–F08 sans cycle LMD ; `intitule` UNIQUE | Audit métier complémentaire |
| Départements | (historique) | `administrations_departement` | **À VÉRIFIER** | rattachement aux secrétariats/directions | structure administrative distincte du pédagogique | À vérifier |
| Promotions | `academics_promotion` (14) | `formations_refvague` (+ `scolarite_groupe`) | **TRANSFORMABLE** | `vague` = cohorte (formation, catégorie, grade, site) ; `groupe` = découpage pédagogique (année, formation, parcours, niveau) | `RefVague.libelle` UNIQUE ; une promotion historique peut couvrir plusieurs niveaux | Reprise sous conditions |
| Semestres | `academics_semester` (10) | `scolarite_semestre` (`niveau` + `numero`) | **TRANSFORMABLE** | rattacher chaque semestre au `Niveau` L1–M2 ; numérotation S1→S10 portée par le libellé | 10 semestres = S1–S10, cohérent ; un semestre historique sans niveau bloque | Reprise sous conditions |
| Spécialités | (historique) | `scolarite_parcours` (formation + type de formation, `Lower(code)` unique) | **À VÉRIFIER** | définition du parcours à valider avec le métier | un « parcours » cible n'est pas une « spécialité » historique | À vérifier |
| Cours | `faculty_course` (136) | `formations_refmodule` puis `scolarite_ecue.ref_module` | **PARTIELLE** | un cours ne devient un ECUE que s'il est rattaché à une UE d'une maquette, avec crédits | ECUE exige UE + crédits + semestre : un cours historique n'en porte pas | Audit métier complémentaire |
| Unités d'enseignement | (88) | `scolarite_ue` (`maquette`, `semestre`, `credits` obligatoires) | **TRANSFORMABLE** | rattacher à une maquette validée, fournir les crédits ECTS | 88 UE vs 80 UE théoriques (8 filières × 10 semestres) : cohérence à instruire | Reprise sous conditions |
| Étudiants | `students_student` (89) | `formations_participant` (`matricule` UNIQUE) **puis** `scolarite_dossieretudiant` (participant unique, statut PROTECT) | **TRANSFORMABLE** | création appariée en deux temps, identité `matricule` comme clé | pivot obligatoire ; matricule manquant = rejet ; doublons interdits | Reprise sous conditions |
| Dossiers académiques | (96) | `scolarite_dossieretudiant` + `scolarite_evenementscolarite` | **PARTIELLE** | 96 dossiers pour 89 étudiants : fusionner avant import (1 dossier par participant) | perte d'historique si fusion non documentée | Reprise sous conditions |
| Inscriptions administratives | `students_enrollment` (305) | `scolarite_inscriptionadministrative` (unique **si VALIDEE**) ; `niveau` obligatoire ; `parcours`, `regime`, `statut_etudiant` facultatifs ; `admission` SET_NULL | **TRANSFORMABLE** | mapper « inscription » → administratif, fournir au minimum le niveau | 305 pour 89 étudiants = redoublements : unicité conditionnelle à respecter | Reprise sous conditions |
| Inscriptions pédagogiques | (non distinguées dans l'historique) | `scolarite_inscriptionpedagogique` (une ligne **par ECUE**) | **NON REPRENABLE en l'état** | à générer après affectation aux ECUE ; **jamais d'activation automatique** après validation administrative | volumétrie = inscriptions × ECUE ; l'historique ne contient pas cette granularité | Audit métier complémentaire |
| Enseignants | `faculty_teacher` (3) | `formations_formateur` (`numerobadge` UNIQUE, `user` O2O, `grade_ref`) + `habilitations_personne` | **TRANSFORMABLE** | numéro de badge obligatoire ; lier au compte utilisateur | 3 enseignants seulement : couverture réelle douteuse | Reprise sous conditions |
| Affectations pédagogiques | (44) | `scolarite_affectationpedagogique` — obligatoires : année, formation, **niveau**, **semestre**, enseignant ; facultatifs : parcours, UE, ECUE (tous PROTECT) | **PARTIELLE** | l'historique lie un enseignant à un cours ; la cible exige au minimum un niveau **et un semestre** | le semestre est obligatoire alors que le cours historique n'en porte pas toujours ; UE/ECUE facultatifs, donc une affectation « large » reste possible | Audit métier complémentaire |
| Salles | (185) | `formations_refsalle` (`site` obligatoire, `code`, `nom`, `type_lieu`, `capacité`) + `refbatiment` | **TRANSFORMABLE** | créer/rattacher les sites et bâtiments | `RefSite.nom` UNIQUE ; 185 salles pour un site unique à confirmer | Reprise sous conditions |
| Emplois du temps | `faculty_schedule` (50) | `edts_emploidutemps` (population générique, `version`) + `edts_affectationcreneau` (créneau, salle, groupe, formateur, **affectation pédagogique PROTECT**) | **PARTIELLE** | reconstruire créneaux et affectations | dépend d'`AffectationPedagogique`, elle-même non reprise ⇒ **blocage en cascade** | Audit métier complémentaire |
| Séances | `faculty_attendancesession` (368) | **deux candidats** : `formations_sessionmodule` (hérité) ou `edts_seanceregistre` (LMD, `cle_metier` unique) | **À VÉRIFIER** | choix de modèle de séance à trancher | deux modèles coexistent : choisir est une **décision métier**, pas technique | Audit métier complémentaire |
| Présences | `faculty_attendance` (1 599) | `presences_pointage` — **toutes les clés sont nullables** (participant, formateur, encadrant, session, séance EDT) et **aucune contrainte** n'impose un support | **PARTIELLE** | rattacher au modèle de séance retenu ; renseigner participant + formateur + encadrant | un pointage sans participant ni séance est accepté par la base : le contrôle doit être fait par l'import, puis par requête (§9 §F) ; `session`/`seance_edt` en CASCADE | Reprise sous conditions |
| Examens | `exams_exam` | `evaluations_sessionevaluation` (maquette + règle **PROTECT**, périmètre unique) → `evaluation` → `epreuve` | **TRANSFORMABLE** | créer la session puis les évaluations typées (`TypeEvaluation`) | exige une maquette et une `RegleCalculVersion` : absents de l'historique | Reprise sous conditions |
| Notes | `exams_grade` | `evaluations_evaluationparticipant` + `evaluationgrade` (+ `evaluationgradehistory`, `evaluationcomponent`) | **TRANSFORMABLE** | notes brutes uniquement ; composantes et barèmes à définir | note historique sans composante ni barème explicite | Reprise sous conditions |
| Résultats calculés | (implicite : moyennes, délibérations) | `semesterresult`, `ueresult`, `ecueresult` (dépendent de `RegleCalculVersion`) | **NON REPRENABLE** | **recalcul obligatoire** par le moteur cible | importer un résultat figé produirait des incohérences dès la 1re session | Abandon de reprise |
| Jurys / délibérations | (historique) | `jurys_sessionjury` + `decisionjury` (unique session+inscription) + `referentiels_reftypedecision` | **PARTIELLE** | mapper chaque type de décision historique sur un code de référence | exclusion/ajournement : décision officielle obligatoire, jamais déduite | Audit métier complémentaire |
| Comptes utilisateurs | `accounts_user` (111) | `authentication_user` (`username` UNIQUE, `matricule` UNIQUE) + `habilitations_compteutilisateur` + `RoleMetier` | **TRANSFORMABLE** | remapper les rôles, recréer les habilitations, vérifier l'algorithme de hachage | rôles historiques ≠ rôles métier ; `is_staff`/`is_superuser` à revalider | Reprise sous conditions |
| Finances | (historique) | `finances_etudiantes` (9 tables : tarification, facture, échéancier, paiement, quittance) | **À VÉRIFIER** | aucune correspondance de libellés établie | référentiel tarifaire par année | Audit métier complémentaire |
| Bibliothèque | `library_*` | **aucune application cible** | **NON REPRENABLE** | — | fonctionnalité non couverte par la cible | Abandon de reprise |
| Celery | `celery_*` | hors périmètre | **NON REPRENABLE** | ne pas migrer (une seule tâche utile : `backend_cleanup`) | résultats de tâches non pertinents | Abandon de reprise |

---

## 5. Conformité aux règles métier INJS — audit E du cahier des charges

Éléments **vérifiés dans le code** de `main@767dabf`.

### 5.1 Huit filières et cycles LMD

- Codes de filières manipulés par l'import : **EM, APA, ES, MS, AND, LOI, ECJP, GER**, réconciliés avec le référentiel « A-4.5 » par le **code dossier F01…F08** (`referentiels/management/commands/importer_referentiels_injs.py`, `RefFiliere.code_dossier`).
- Règle explicite du code : **« seules F01 à F04 ouvrent un cursus LMD ; F05 à F08 n'ont, dans la source, aucun cycle LMD — rien n'est créé pour elles »** (`CYCLES_LMD = ('F01','F02','F03','F04')`).
- **Conséquence pour l'historique** : si des étudiants inscrits en F05–F08 doivent être repris, il n'existe aujourd'hui **aucun cycle LMD** auquel les rattacher. C'est une décision métier (ouvrir un cursus, ou traiter ces filières hors LMD), pas une transformation technique.

### 5.2 Architecture LMD : S1 → S10, 30/60 ECTS

- Répartition officielle codée : S1–S2 → L1, S3–S4 → L2, S5–S6 → L3, S7–S8 → M1, S9–S10 → M2 (`configurer_referentiel_injs.py`).
- `Niveau.credits_requis` = **60 ECTS par niveau** ; `RegleValidationLMD.credits_semestre` = **30 ECTS par semestre** (valeur par défaut et valeur posée par l'import).
- Commande de contrôle dédiée : `controler_referentiel_injs` vérifie « 30 ECTS par semestre » et « 60 ECTS par niveau » — donc le critère d'acceptation est déjà outillé.
- **Conséquence** : les 10 semestres historiques s'alignent sur S1–S10 (cohérent), mais les **crédits ECTS ne sont pas dans l'historique** : ils viendront de la maquette, jamais d'une déduction sur les volumes horaires.

### 5.3 Séparation admission / inscription administrative / parcours / inscription pédagogique

Quatre objets distincts et non interchangeables dans la cible :

1. `admissions_candidature` → `admissions_admission` (décision d'admission, voie d'accès, campagne) ;
2. `scolarite_inscriptionadministrative` (validée par un utilisateur, statut, régime, niveau, parcours) ;
3. `scolarite_parcours` (+ `Niveau`, `Semestre`) = parcours académique ;
4. `scolarite_inscriptionpedagogique` = **une ligne par ECUE**, distincte et postérieure.

**Aucun mécanisme automatique** ne crée l'inscription pédagogique à la validation administrative : la structure l'impose (deux tables, deux clés étrangères distinctes). Cette règle est donc structurellement préservée — et doit le rester dans tout script de reprise.

### 5.4 Exclusion et décisions

`RegleValidationLMD` isole les seuils (`seuil_admission`, `seuil_elim`, `compensation`, `capitalisation`) et `jurys_decisionjury` porte la décision par inscription, typée par `referentiels_reftypedecision`. Une exclusion ne peut donc être qu'une **décision enregistrée**, jamais une déduction de moyenne : la reprise doit mapper les types de décision historiques, ou renoncer à les importer.

### 5.5 Données historiques non rattachables avec certitude

Sans document de référence, **ne peuvent pas** être rattachées : les 4 « programmes » historiques face aux 8 filières ; les 136 cours face aux UE/ECUE ; les 44 affectations face aux ECUE ; les 50 emplois du temps face aux `population_id` génériques ; les examens face aux sessions d'évaluation. Aucune correspondance ne sera inventée : ces lignes restent « À VÉRIFIER ».

---

## 6. Risques techniques de migration — audit F

| # | Risque | Détail vérifié | Parade |
|---|---|---|---|
| 1 | **Clés primaires** | 100 % `BigAuto` (entiers) des deux côtés — pas de conflit de type | ne pas réimporter les PK historiques : laisser la séquence cible attribuer, conserver l'identifiant historique dans une table de correspondance hors production |
| 2 | **Conflits d'identifiants** | `Participant.matricule`, `User.username`, `User.matricule` sont UNIQUE | dédoublonnage **avant** import, arbitrage métier documenté |
| 3 | **Modèle utilisateur** | 111 comptes → `authentication.User` + `habilitations` (rôles métier, périmètres) | remapper les rôles ; vérifier l'algorithme de hachage (§C) ; ne jamais réinitialiser en masse sans décision |
| 4 | **Pivot étudiant** | `DossierEtudiant.participant` PROTECT + unique | import en deux temps, transaction unique, contrôle de cardinalité 1:1 |
| 5 | **Ordre de reprise** | chaîne de PROTECT : référentiels → année → filière → formation → niveau/semestre → parcours → maquette → UE → ECUE → site/salle → formateur → participant → dossier → inscription → affectation → groupe → EDT → créneau → séance → pointage → session d'évaluation → évaluation → note → jury | respecter strictement l'ordre ; un import dans le désordre échouera sur des PROTECT, pas sur des CASCADE (donc sans perte, mais bloquant) |
| 6 | **ManyToMany** | 19 tables de liaison | ne pas peupler avant les deux extrémités ; `formations_refmodule_formations`, `authentification_user_groups`, `habilitations_*` |
| 7 | **Unicités insensibles à la casse** | `Lower(code)` sur UE, ECUE, Groupe, Parcours ; `Lower(intitule)` sur `RefModule` ; `Lower(libelle)` sur plusieurs référentiels | normaliser la casse avant import, sinon collisions silencieuses au premier trimestre |
| 8 | **Champs obligatoires absents de l'historique** | non nullables et probablement absents : `RefSalle.site`, `RefSalle.nom`, `UE.credits`, `ECUE.credits`, `ECUE.coefficient`, `Formateur.numerobadge`, `Participant.matricule/nom/prenom`, `InscriptionAdministrative.niveau`, `AffectationPedagogique.semestre` | fournir des valeurs par défaut **validées par le métier**, jamais inventées |
| 9 | **Valeurs par défaut** | `credits_semestre=30`, `seuil_admission=10`, `capitalisation_activee=True` | vérifier que ces défauts correspondent aux règles INJS avant de s'y appuyer |
| 10 | **Historique des migrations** | 257 fichiers côté code ; 327 enregistrées côté historique (sans lien) | ne pas recopier `django_migrations` ; relever le nombre réel en cible (§9) |
| 11 | **Dépendance aux applications historiques** | aucune application historique n'existe dans le code cible (`academics`, `students`, `faculty`, `exams`, `library` absents) | aucune FK inter-apps ne peut être conservée : la reprise est un **remodelage**, pas une copie |
| 12 | **Celery** | cible : une seule tâche périodique (`backend_cleanup`), 85 exécutions | ne rien migrer ; ne pas réutiliser la base de broker historique |
| 13 | **FK génériques** | `edts_emploidutemps.population_id`, `habilitations_perimetre.content_type` | cohérence `type`/`id` à garantir, sinon données invisibles ou erronées |

---

## 7. Données potentiellement récupérables, par priorité — livrable E

| Priorité | Domaine | Volume historique | Récupérabilité | Condition bloquante |
|---|---|---|---|---|
| 1 | **Référentiels académiques** (années, niveaux, semestres, filières) | 5 années, 10 semestres, 4 programmes | moyenne | les filières doivent venir du référentiel A-4.5 (daté par année), pas des libellés historiques |
| 2 | **Étudiants et dossiers** | 89 étudiants, 96 dossiers | **élevée** | pivot Participant + DossierEtudiant ; fusion des 7 dossiers excédentaires |
| 3 | **Inscriptions administratives** | 305 | élevée | mapping niveau/parcours/régime/statut ; unicité conditionnelle |
| 4 | **Enseignants et affectations** | 3 enseignants, 44 affectations | faible (enseignants) / nulle (affectations) | affectation cible au niveau ECUE, historique au niveau cours |
| 5 | **Emplois du temps et salles** | 50 EDT, 185 salles | moyenne (salles) / faible (EDT) | salles : créer les sites ; EDT : dépend des affectations |
| 6 | **Présences** | 368 séances, 1 599 présences | moyenne | décision préalable : `SessionModule` ou `SeanceRegistre` |
| 7 | **Examens et évaluations** | examens + notes | moyenne | maquette + règle de calcul obligatoires ; résultats calculés exclus |
| 8 | **Autres** (comptes, finances, jurys, bibliothèque) | 111 comptes, finances, jurys | comptes : moyenne ; jurys/finances : à instruire ; bibliothèque : nulle | mapping des rôles et des types de décision |

---

## 8. Plan de migration recommandé — livrable F, **théorique, non exécuté**

### 8.1 Principe

1. **Le référentiel ne se reprend pas depuis l'historique.** Il s'importe depuis les documents officiels (commandes `importer_referentiels_injs`, `import_referentiel_injs_lmd`, `configurer_referentiel_injs`, puis contrôle `controler_referentiel_injs`).
2. **L'historique ne fournit que des faits** : personnes, inscriptions, notes brutes, pointages — jamais des référentiels, jamais des résultats calculés.
3. **Toute ligne non rattachable reste dehors** et est journalisée dans un rapport d'écarts, avec son identifiant technique.

### 8.2 Ordre de reprise (dépendances vérifiées)

| Phase | Objet | Dépend de | Contrôle d'acceptation |
|---|---|---|---|
| 0 | Sauvegarde des deux bases + test de restauration | — | restauration vérifiée sur environnement isolé |
| 1 | Référentiels officiels (école, mention, cursus, filières, grades, types) | — | `controler_referentiel_injs` : 0 écart ; 8 filières, codes F01–F08 |
| 2 | Années académiques + niveaux + semestres | 1 | S1–S10 complets, une seule `courante`, `CHECK` respectés |
| 3 | Formations, parcours, maquettes, UE, ECUE | 1–2 | 30 ECTS/semestre, 60 ECTS/niveau, codes uniques (casse ignorée) |
| 4 | Sites, bâtiments, salles | 1 | 100 % des salles rattachées à un site |
| 5 | Enseignants (`Formateur`) + comptes (`User`) + rôles métier | 1 | 0 doublon de badge / username / matricule |
| 6 | Participants + dossiers étudiants | 1–3 | cardinalité 1:1 Participant ↔ Dossier |
| 7 | Inscriptions administratives | 6 | 0 inscription sans étudiant/année/formation/parcours/niveau ; unicité des VALIDEE |
| 8 | Groupes + affectations pédagogiques | 3, 5, 6 | 0 affectation sans ECUE |
| 9 | Emplois du temps + créneaux | 4, 8 | 0 créneau sans affectation pédagogique |
| 10 | Séances (modèle retenu) + pointages | 9 | 0 pointage sans support ; présences = total historique (ou écart expliqué) |
| 11 | Sessions d'évaluation + évaluations + notes brutes | 3, 7 | 0 note sans participant évalué ; **0 résultat calculé importé** |
| 12 | Jurys + décisions | 7, 11 | chaque décision porte un `RefTypeDecision` existant |
| 13 | Finances (si décision) | 7 | rapprochement montants vs historique |
| 14 | Contrôles finaux | toutes | comptages par domaine comparés aux chiffres historiques, écarts justifiés un par un |

### 8.3 Règles de sécurité du plan

- import **idempotent** (clé métier + `update_or_create`), jamais « truncate + reload » ;
- une transaction par phase, avec point de reprise ;
- **aucune bascule de production** sans sauvegarde vérifiée + plan de retour arrière distinct (applicatif ≠ base) ;
- les mots de passe ne sont jamais affichés, jamais réinitialisés sans décision ;
- les données nominatives ne sortent pas de la base (rapports d'écarts = identifiants techniques).

### 8.4 Critères d'acceptation globaux

1. `controler_referentiel_injs` = 0 écart.
2. Comptages cible = comptages historiques **ou** écart documenté ligne à ligne.
3. 0 violation d'unicité, 0 orphelin (§9, scripts 10).
4. Aucun résultat calculé importé ; recalcul du moteur cible cohérent sur un échantillon validé par le métier.
5. Aucune inscription pédagogique créée automatiquement par la validation administrative.

---

## 9. Vérifications encore nécessaires — livrable H (les vraies inconnues)

1. **Schéma réel de `injs-db`** — noms, colonnes, PK/FK, contraintes des 73 tables. → `00_profil_schema.sql` sur `injs-db`.
2. **Écart 203 vs 222 tables** en cible — lever l'hypothèse du §2.3. → `00_profil_schema.sql` sections 2–3, puis comparaison avec `tables_cibles_attendues.txt`.
3. **Intégrité référentielle historique** (FK non validées, orphelins). → `10_anomalies.sql` §A et §B.
4. **Doublons sur clés naturelles** (matricules, codes, numéros). → §E.
5. **Algorithmes de hachage des 111 comptes** (comptage par préfixe, aucun hash affiché). → §H.
6. **Distribution des statuts historiques** (reconnaître les valeurs non reconnues). → §I.
7. **Correspondance 4 programmes ↔ 8 filières** : dépend d'un document de référence (A-4.5) et d'une décision métier — **aucune requête SQL ne la donnera**.
8. **Nature des 88 UE et 136 cours historiques** (crédits ? rattachement ?). → colonnes via `00_profil_schema.sql` §5, puis arbitrage.
9. **Volumétrie prévisible des inscriptions pédagogiques** : nombre d'ECUE par inscription, à estimer avant import.
10. **Modèle de séance à retenir** (`SessionModule` hérité vs `SeanceRegistre` LMD) : décision métier, pas technique.
11. **Périmètre retenu des filières F05–F08** : ouverture d'un cursus LMD ou traitement hors LMD.
12. **Fichiers Celery** : confirmer qu'il n'y a rien à reprendre (une seule tâche `backend_cleanup`).

### Comment obtenir 1 à 6 en une seule opération

Sur le VPS (ou le Mac) :

```sh
cd docs/audits/sql
MODE=docker PG_CONTAINER=<conteneur_postgres> sh run_audit.sh
```

Les trois scripts sont en `READ ONLY` + `ROLLBACK`, ne contiennent aucun secret, n'affichent aucune donnée nominative, et ont été validés sur deux schémas témoins. Les sorties vont dans `docs/audits/collecte/` et suffisent à chiffrer les audits A, B et D sans nouvelle intervention.

---

## 10. Décisions finales par domaine — livrable G

| Domaine | Décision |
|---|---|
| Années académiques | **REPRISE ENVISAGEABLE** (sous contrôle des dates et de l'année courante) |
| Référentiels (écoles, mentions, filières, grades, types) | **REPRISE SOUS CONDITIONS** — réimport documentaire, pas reprise historique |
| Programmes / formations (4) | **AUDIT MÉTIER COMPLÉMENTAIRE** |
| Promotions / vagues | **REPRISE SOUS CONDITIONS** |
| Niveaux et semestres | **REPRISE ENVISAGEABLE** (alignement S1–S10 vérifié) |
| Cours / UE / ECUE | **AUDIT MÉTIER COMPLÉMENTAIRE** |
| Étudiants + dossiers | **REPRISE SOUS CONDITIONS** (pivot obligatoire, fusion 96→89) |
| Inscriptions administratives | **REPRISE SOUS CONDITIONS** |
| Inscriptions pédagogiques | **AUDIT MÉTIER COMPLÉMENTAIRE** (granularité ECUE absente de l'historique) |
| Enseignants | **REPRISE SOUS CONDITIONS** |
| Affectations pédagogiques | **AUDIT MÉTIER COMPLÉMENTAIRE** (semestre obligatoire, UE/ECUE facultatifs) |
| Salles | **REPRISE SOUS CONDITIONS** |
| Emplois du temps | **AUDIT MÉTIER COMPLÉMENTAIRE** |
| Séances | **AUDIT MÉTIER COMPLÉMENTAIRE** (choix de modèle) |
| Présences | **REPRISE SOUS CONDITIONS** (après le choix de modèle de séance) |
| Examens / évaluations | **REPRISE SOUS CONDITIONS** |
| Notes brutes | **REPRISE SOUS CONDITIONS** |
| Résultats calculés (moyennes, délibérations chiffrées) | **ABANDON DE REPRISE** — recalcul obligatoire |
| Jurys / décisions | **AUDIT MÉTIER COMPLÉMENTAIRE** |
| Comptes utilisateurs | **REPRISE SOUS CONDITIONS** |
| Finances étudiantes | **AUDIT MÉTIER COMPLÉMENTAIRE** |
| Bibliothèque | **ABANDON DE REPRISE** (aucune application cible) |
| Celery | **ABANDON DE REPRISE** (hors périmètre) |

---

## 11. Conclusion — statut honnête de la mission

Les critères de fin que vous avez fixés ne sont **pas tous atteints** :

| Critère | État |
|---|---|
| 1. Les deux schémas comparés | ⚠️ **partiel** — cible inventoriée intégralement ; historique non interrogé |
| 2. Relations métier examinées | ✅ **fait** côté cible (pivot, chaînes PROTECT, unicités) |
| 3. Anomalies quantifiées | ❌ **non** — méthode livrée, chiffres impossibles sans accès |
| 4. Matrice de correspondance produite | ✅ **fait** (26 domaines, 5 classes, décision par ligne) |
| 5. Données récupérables identifiées | ✅ **fait** (8 priorités) |
| 6. Risques et dépendances documentés | ✅ **fait** (13 risques, ordre de reprise en 15 phases) |
| 7. Plan de migration contrôlé proposé | ✅ **fait** (théorique, non exécuté) |

Je n'écris donc **pas** la formule de clôture « audit terminé » : elle serait fausse. Ce qui est vrai et vérifiable :

**AUCUNE MODIFICATION EFFECTUÉE — AUCUNE DONNÉE COPIÉE — AUCUN SERVICE MODIFIÉ — AUCUNE MIGRATION LANCÉE.**

Aucune écriture n'a été tentée sur le VPS, sur Docker, sur Nginx, sur Celery ni sur PostgreSQL. Le seul environnement modifié est celui de l'audit (installation d'un interpréteur et création de deux bases témoins **locales et jetables**, dans le sandbox, pour valider les scripts SQL — aucune de ces bases ne contient de donnée réelle).

**Prochaine action, et elle vous revient** : exécuter `docs/audits/sql/run_audit.sh` sur le VPS (ou le Mac) et me transmettre la sortie. Avec ces fichiers, je complète les audits A, B et D avec des chiffres réels et je fournis alors le rapport final avec la formule de clôture.

### Livrables de cette session

| Fichier | Contenu |
|---|---|
| `docs/audits/2026-11-05-audit-comparatif-bases-injs.md` | le présent rapport |
| `docs/audits/sql/00_profil_schema.sql` | profil complet (tables, colonnes, clés, contraintes, index, migrations, séquences) |
| `docs/audits/sql/10_anomalies.sql` | intégrité, orphelins, doublons, dates, statuts, hachages, orphelins métier cibles |
| `docs/audits/sql/run_audit.sh` | exécution en lecture seule sur les deux bases |
| `docs/audits/sql/README.md` | mode d'emploi et garanties de sécurité |
| `docs/audits/tables_cibles_attendues.txt` | les 222 tables attendues en cible, pour comparaison directe |
