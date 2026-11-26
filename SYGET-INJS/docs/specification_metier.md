# Spécification métier — Logiciel d'emploi du temps CPFAE

Document métier exhaustif décrivant le besoin client et la couverture fonctionnelle de l'application **epdtcpfae**. Il sert de référence pour valider que la plateforme satisfait l'ensemble des demandes métier du Centre de Perfectionnement et de Formation aux Affaires Économiques (CPFAE).

---

## 1. Contexte et finalité métier

### 1.1 Problème adressé
Le CPFAE organise plusieurs **vagues** de formation (FAC, FAB, etc.) regroupant des centaines d'auditeurs (agents de catégories A/B/C/D, grades A3, A4, B3, B4, C3, C4, D3, D4…). Chaque vague mobilise plusieurs **modules pédagogiques**, plusieurs **formateurs**, plusieurs **sites/bâtiments/salles** et impose un planning compatible avec :

- les contraintes de capacité (effectif vs taille de salle) ;
- la disponibilité des salles, formateurs, jours ouvrés, jours fériés ;
- les volumes horaires réglementaires par couple (type de formation × module × grade) ;
- une cadence mensuelle (1, 2, 3 ou 4 semaines/mois) configurable par formation et par groupe ;
- la non-collision : pas deux groupes au même endroit, pas deux modules le même jour pour un même groupe, plafond quotidien de séances, etc.

La construction manuelle de cet emploi du temps est lente, source d'erreurs et difficilement auditable.

### 1.2 Objectifs métier (« demande client »)
1. **Centraliser** les référentiels (sites, bâtiments, salles, grades, vagues, types de formation, modules, spécialités, jours fériés).
2. **Automatiser** la création des groupes pédagogiques à partir des inscrits, du grade et de la catégorie, avec ou sans mixage des grades.
3. **Générer automatiquement** un planning de séances respectant l'ensemble des règles métier ci-dessus, avec un score de qualité de l'allocation des salles.
4. **Détecter et expliquer les conflits** (chevauchements, dépassements, jours fériés, hors-plage horaire).
5. **Exporter** les emplois du temps (Excel, PDF, synthèse Word par module/groupe/formation).
6. **Anticiper** la faisabilité d'une formation via une **simulation** (capacité d'accueil, durée minimum requise, date de fin recommandée).
7. **Tracer** toutes les actions de planification (audit RGPD/qualité).
8. **Sécuriser** l'accès via un **RBAC à 3 rôles** (Admin, Gestionnaire, Direction).

### 1.3 Utilisateurs cibles
| Profil | Rôle Django | Périmètre |
|---|---|---|
| Administrateur EDT | `ADMIN_EDT` | Lecture + écriture sur tout (planning, formations, auditeurs, groupes, référentiels, paramétrage). Audit complet. |
| Gestionnaire EDT | `GESTIONNAIRE_EDT` | Lecture + écriture planning et données métier ; **lecture seule** sur le paramétrage. |
| Direction | `DIRECTION_EDT` | **Lecture seule** sur l'ensemble (preview, audit, exports). |
| Superutilisateur Django | — | Tous droits, accès admin Django. |

---

## 2. Périmètre fonctionnel global

L'application est découpée en 7 modules métier (apps Django) :

| App | Rôle métier |
|---|---|
| `parametrage` | Référentiels paramétrables : grades, vagues, sites, bâtiments, salles, jours fériés, paramètres généraux, association module ↔ type de formation. |
| `referentiels` | Référentiels structurels partagés : types de formation, modules, spécialités. |
| `auditeurs` | Gestion des auditeurs (création manuelle + import Excel). |
| `formations` | Formations, programme pédagogique (modules de formation), formateurs, inscriptions. |
| `groupes` | Groupes pédagogiques d'une formation, configuration horaire et jours actifs. |
| `seances` | Génération, édition, audit, exports et détection de conflits sur les séances. |
| `simulation` | Outil d'aide à la décision pour dimensionner une formation (durée, salles, créneaux). |

---

## 3. Référentiels et paramétrage (app `parametrage` + `referentiels`)

### 3.1 Besoins métier
- Le client doit pouvoir **gérer ses propres référentiels** sans intervention technique.
- Les valeurs paramétrées doivent **pré-remplir** les formulaires de création (formation, groupe, module).
- Les contraintes d'intégrité doivent empêcher de désactiver/supprimer une donnée référencée.

### 3.2 Couverture fonctionnelle

| Entité | Champs clés | Règles métier |
|---|---|---|
| **Type de formation** (`TypeFormation`) | code, libellé | Code unique. Référence obligatoire d'une formation. |
| **Module** (`Module`) | titre, actif, spécialité | Titre unique. Spécialité obligatoire (sert au matching formateur). |
| **Spécialité** (`Specialite`) | code, libellé | Code unique. Plusieurs spécialités peuvent matcher un module via le titre. |
| **Grade** (`Grade`) | libellé, ordre, actif | Tri des groupes par ordre puis libellé. Détection automatique à l'import Excel. |
| **Vague** (`Vague`) | libellé, actif | Liste déroulante à la création d'une formation. |
| **Site** (`Site`) | nom, actif | Désactivation interdite si bâtiments actifs rattachés. |
| **Bâtiment** (`Batiment`) | site, nom, actif | Désactivation interdite si salles actives rattachées. Unicité (site, nom). |
| **Salle** (`Salle`) | bâtiment, nom, capacité_max, actif | Capacité maximale = critère central du scoring. |
| **Jour férié** (`JourFerie`) | date, libellé, actif | Exclu automatiquement de la planification si actif. |
| **ModuleTypeFormation** | module, type_formation, grade_cible, volume_horaire_defaut | Volume pré-rempli quand un module est ajouté à une formation. |
| **Paramètres généraux** (singleton) | voir §3.3 | Une seule ligne en base. |

### 3.3 Paramètres généraux (singleton `ParametreGeneral`)

Pré-remplissent les formulaires et pilotent le moteur de génération.

- **`max_auditeurs_groupe_defaut`** : capacité par défaut d'un groupe (ex. 25).
- **`groupes_auto_mixage_grades`** : autorise le mixage multi-grades dans la génération auto des groupes.
- **`matin_heure_debut/fin_defaut`**, **`soir_heure_debut/fin_defaut`** : créneaux par défaut.
- **`jours_defaut`** : jours ouvrés par défaut (ex. lundi→vendredi).
- **`duree_seance_defaut_minutes`** : durée standard d'une séance (240 min par défaut).
- **`max_seances_par_jour_defaut`** : plafond séances/jour/groupe (2 par défaut).
- **`max_salles_simultanees_module`** : nombre max de salles différentes accueillant le même module sur une même journée (entre groupes d'une formation).
- **`tolerance_capacite_salle`** : tolérance de surcharge en auditeurs (0 = veto strict).
- **`marge_simulation_pct`** : marge ajoutée au plancher dans la simulation (5 %–20 %).
- **Poids du scoring salles** :
  - `poids_score_ecart_capacite` (proximité capacité ↔ effectif) ;
  - `poids_score_rotation_module` (rotation des salles d'un même module) ;
  - `poids_score_equilibrage_global` (équilibrage global d'usage des salles).

> **Référence opérationnelle** : `docs/reglage_scoring_salles.md` fournit 3 presets (conservateur, équilibré, rotation forte) et une grille d'ajustement.

---

## 4. Auditeurs (app `auditeurs`)

### 4.1 Besoins métier
- Saisir manuellement un auditeur **ou** importer en masse depuis Excel.
- Conserver l'identité administrative (matricule, état civil), le canal de contact, le concours, la catégorie et le grade.
- Servir d'identité unique pour l'inscription aux formations et la constitution des groupes.

### 4.2 Couverture fonctionnelle

| Fonction | URL/vue |
|---|---|
| Liste des auditeurs | `auditeurs:list` |
| Création manuelle | `auditeurs:create` |
| Détail / mise à jour / suppression | `auditeurs:detail` / `update` / `delete` |
| Import Excel + rapport d'import | `auditeurs:import` / `import_rapport` |

### 4.3 Données d'un auditeur

#### 4.3.1 Champs propres (modèle `Auditeur`)

| Champ | Type | Règles métier |
|---|---|---|
| **N° d'inscription** (`matricule`) | texte, **unique** | Identifiant administratif. Normalisé à l'import (trim, casse). Sert de clé fonctionnelle pour les imports et les inscriptions. |
| **Nom** (`nom`) | texte | Affiché en majuscules dans `nom_complet`. |
| **Prénoms** (`prenom`) | texte | Peut contenir plusieurs prénoms. |
| **Genre** (`genre`) | choix `M` / `F` | Optionnel. |
| **Date de naissance** (`date_naissance`) | date | Optionnel. |
| **Lieu de naissance** (`lieu_naissance`) | texte | Optionnel. |
| **E-mail** (`email`) | e-mail | Optionnel. Canal de contact. |
| **Téléphone 1** (`telephone_1`) | texte | Optionnel. |
| **Téléphone 2** (`telephone_2`) | texte | Optionnel. |
| **Type concours** (`type_concours`) | texte | Filière de recrutement. |
| **Libellé concours** (`libelle_concours`) | texte | Intitulé exact du concours. |
| **Catégorie** (`categorie`) | texte (A/B/C/D…) | Pré-rempli à l'import. Utilisé pour nommer les groupes en mode mixage (« Groupe N {catégorie} »). |
| **Grade** (`grade`) | texte (A3, A4, B3…) | Détecté automatiquement à l'import. Détermine la compatibilité avec un module via `grade_cible_matches` et le nom du groupe en mode non-mixage (« Groupe N {grade} »). |

#### 4.3.2 Champs dérivés (calculés via les inscriptions et la planification)

Ces données ne sont pas stockées sur l'auditeur mais calculées à partir de ses inscriptions (`Inscription` → `FormationModule` → `Formation`, `Groupe`, `Seance`, `Salle`, `Batiment`, `Site`).

| Champ dérivé | Source | Règle de calcul |
|---|---|---|
| **Groupe** | `MembreGroupe` → `Groupe.nom` | Nom du / des groupe(s) auxquels l'auditeur appartient (ex. « Groupe 1 A3 »). |
| **Grade-Groupe** (`grade_groupe`) | propriété calculée | Concaténation `{grade}-{nom_groupe}` pour le premier groupe rattaché ; sinon `grade` seul, sinon « — ». |
| **Vague** | `Formation.vague` | Vague de la / des formation(s) où l'auditeur est inscrit. |
| **Formation(s)** | `Inscription` → `FormationModule.formation` | Liste distincte des formations actives de l'auditeur (intitulé + type). |
| **Site** | `Seance.salle.batiment.site` | Site(s) effectivement utilisé(s) pour les séances de l'auditeur (via son groupe). |
| **Salle** | `Seance.salle` | Salle(s) attribuée(s) aux séances du groupe de l'auditeur. |

> Les champs dérivés sont exposés en lecture dans les exports (`formations:export_auditeurs`) et les écrans de consultation. Ils ne sont jamais saisis manuellement : ils résultent du parcours **inscription → groupe → planning**.

---

## 5. Formations et programme pédagogique (app `formations`)

### 5.1 Besoins métier
- Décrire **chaque vague de formation** (type, intitulé, vague, période, cadence mensuelle).
- Définir le **programme pédagogique** : liste des modules avec volume horaire, créneau autorisé, sites/bâtiments/salles, formateur, période d'enseignement et grade ciblé.
- Inscrire les auditeurs (manuellement, par copie depuis une formation source, par import).
- Affecter les **formateurs** par couple (groupe, module).

### 5.2 Couverture fonctionnelle

#### Formation
- Création / édition / suppression / détail (`formations:create|edit|delete|detail`).
- Choix du type, intitulé, vague (liste paramétrée), date début/fin.
- **`rythme_mensuel`** : 1, 2, 3 semaines ou tout le mois — limite la planification.
- **`planning_union_sites_programme`** : option avancée pour élargir le pool de sites du dispatch.
- Export de la liste des auditeurs inscrits (`formations:export_auditeurs`).

#### Modules de la formation (`FormationModule`)
- Ajout / édition / suppression d'un module (`module_add|edit|delete`).
- Volume horaire fixe **ou** dérivé du paramétrage `(type × module × grade)`.
- **`creneau_mode`** : matin uniquement / soir uniquement / matin et soir.
- Sites / bâtiments / salles : nom(s) explicites (CSV) **ou** auto-fallback sur le pool actif filtré par site/bâtiment.
- **`salle_nombre`** : limite le pool si aucune salle n'est nommée.
- Formateur affecté (nom, prénom, numéro, e-mail, téléphone, organisation).
- Période d'enseignement spécifique au module (sinon hérite de la formation).
- Grade cible : restreint l'éligibilité d'un groupe.

#### Formateurs
- Référentiel global (`Formateur`) avec **numéro unique**, identité, contact, organisation, **spécialités** (M2M obligatoire ≥ 1).
- Import en masse via Excel (`formations:formateurs_import`).
- Affectation **(groupe, module) → formateur** unique (contrainte d'unicité). Matching automatique sur la spécialité du module.

#### Inscriptions
- Ajout manuel (`inscription_add`), suppression (`inscription_delete`).
- **Copie depuis une formation source** (`inscription_copier`) : crée les groupes homologues nécessaires, puis affecte en masse.
- Unicité (formation_module, auditeur).
- Synchronisation automatique de la formation depuis le module choisi.

---

## 6. Groupes pédagogiques (app `groupes`)

### 6.1 Besoins métier
- Constituer des groupes équilibrés à partir des inscrits, par grade ou par catégorie (mixage).
- Permettre une saisie manuelle (création vide, ajout/retrait de membres).
- Configurer pour chaque groupe : créneaux matin/soir, jours actifs, cadence mensuelle (override formation).
- Reporter les groupes d'une formation source vers une formation cible (homologues).

### 6.2 Couverture fonctionnelle

| Fonction | Vue / URL |
|---|---|
| Liste des groupes d'une formation | `groupes:list` |
| Création manuelle d'un groupe | `groupes:create` |
| **Génération automatique** (avec ou sans reset) | `groupes:auto_generate` |
| Configuration horaires + jours d'un groupe | `groupes:config` |
| Suppression d'un groupe | `groupes:groupe_delete` |
| Ajout / suppression d'un membre | `groupes:membre_add` / `membre_delete` |
| **Régénérer le planning** (sans toucher aux membres) | `groupes:regenerer_planning` |
| Assurer l'existence des groupes homologues | `groupes:assurer_homologues` |
| Reporter tous les groupes depuis la source | `groupes:reporter_depuis_source` |

### 6.3 Règles de génération automatique des groupes (synthèse)

Voir `docs/generation_groupes_seances.md`. Grandes lignes :

1. Vérification des modules de la formation.
2. Backfill des inscriptions selon compatibilité de grade.
3. Dédoublonnage.
4. Mode mixage off → un groupe par grade (« Groupe N {grade} »).
5. Mode mixage on → un groupe par catégorie (« Groupe N {cat} ») avec répartition tournante des grades.
6. Création des groupes (capacité = `max_auditeurs_groupe_defaut`) et répartition round-robin des auditeurs.
7. Lancement de la génération des séances pour chaque nouveau groupe.

### 6.4 Configuration horaire (`ConfigGroupe`)
- Activation / horaires matin et soir (par défaut 08:00–12:00 et 13:00–17:00).
- Pré-remplie depuis le paramétrage.

### 6.5 Jours de cours (`JourCours`)
- 0 = lundi … 6 = dimanche, multi-sélection.

### 6.6 Cadence mensuelle d'un groupe
- Vide = hérite de la formation. Sinon override (intersection AND avec la formation).

---

## 7. Génération des séances et planning (app `seances`)

C'est le **cœur métier** du logiciel.

### 7.1 Besoins métier
- Calculer un emploi du temps **complet et sans conflit** pour chaque groupe, conforme au programme pédagogique.
- Proposer une **prévisualisation** (dry-run) avant persistance.
- Détecter et **expliquer** les conflits.
- Permettre la **création/édition/suppression manuelle** d'une séance individuelle.
- Garantir la **traçabilité** (audit log).

### 7.2 Modèle métier
Une séance = (groupe, module, date, heure_début, heure_fin, durée min, salle/bâtiment/site, formateur).

### 7.3 Règles métier appliquées par le moteur

#### Contraintes de salle
- **Site obligatoire** sur un module.
- Pas de **chevauchement** sur une même salle (entre groupes).
- Veto **capacité** : `capacite_max ≥ effectif − tolerance_capacite_salle`.
- Fallback sur salles actives filtrées par site/bâtiment si pas de salle nommée.

#### Contraintes calendaires
- **Jours actifs du groupe** uniquement.
- **Jours fériés** exclus.
- **Cadence mensuelle** (formation ∩ groupe) respectée.
- Fenêtre de dates = `FormationModule.date_debut/fin` sinon dates de la formation.

#### Contraintes de cours
- **Un seul module par jour** pour un groupe.
- **Plafond `max_seances_par_jour_defaut`** par groupe et par jour.
- **Plafond `max_salles_simultanees_module`** : un même module ne peut pas tourner sur plus de N salles le même jour.
- **2 séances/jour max par couple (date, module, salle)**.
- Créneau matin / soir / les deux selon `FormationModule.creneau_mode`.

#### Choix de la salle (scoring 3 critères pondérés)
1. **Écart de capacité** (proximité capacité ↔ effectif) — `poids_score_ecart_capacite`.
2. **Rotation** des salles pour un même module — `poids_score_rotation_module`.
3. **Équilibrage global** d'usage des salles — `poids_score_equilibrage_global`.

#### Choix du formateur
- Une seule affectation `(groupe, module)`.
- Matching sur la spécialité du module (incluant les spécialités dont le code/libellé correspond au titre du module, casse-insensible).

### 7.4 Couverture fonctionnelle (vues)

| Fonction | URL |
|---|---|
| Prévisualisation planning groupe | `seances:preview` |
| Création manuelle d'une séance | `seances:create` |
| Édition / suppression d'une séance | `seances:update` / `delete` |
| Export Excel groupe | `seances:export` |
| Export PDF groupe | `seances:export_pdf` |
| Synthèse Word (DOCX) groupe × module | `seances:groupe_module_synthese_docx` |
| Export Excel formation entière | `seances:formation_export` |
| Export PDF formation entière | `seances:formation_export_pdf` |
| Synthèse Word formation × module | `seances:formation_module_synthese_docx` |
| Vue chevauchements / conflits | `seances:chevauchements` |
| Audit complet des actions | `seances:audit_list` |

### 7.5 Modes de génération
- **Best-effort** (défaut) : place le maximum, signale les modules non placés avec cause précise (salles, fenêtre, jours actifs, plafond, cadence…).
- **Reset/regenerate** : relance sans toucher aux membres des groupes.

### 7.6 Audit & rapports
- **`PlanningAuditLog`** : génération, export, création/modif/suppression — acteur, groupe, séance, détails JSON, horodatage.
- **`PlanningRun`** : rapport persistant par formation (synthèse JSON, statut en cours / terminé / erreur, mode).

---

## 8. Simulation et aide à la décision (app `simulation`)

### 8.1 Besoin métier
Avant de lancer une formation, le gestionnaire doit pouvoir **estimer** :
- la **durée minimum** nécessaire (jours ouvrés) ;
- le **nombre de salles** suffisant ;
- la **date de fin recommandée** à partir d'une date de début ;
- l'impact des paramètres (créneaux/jour, durée créneau, jours ouvrés, jours fériés).

### 8.2 Couverture fonctionnelle (vue `simulation:index`)
- Pré-remplissage automatique depuis le paramétrage (capacités salles actives, créneaux, jours).
- Pré-remplissage depuis une **formation existante** (`?formation_id=`) → reprend nb auditeurs, modules, heures, jours fériés filtrés sur la période.
- 3 modes de calcul :
  1. Période saisie (début + fin) → calcul des jours ouvrés réels et comparaison au minimum recommandé.
  2. Saisie directe d'un nombre de jours ouvrés.
  3. Mode **auto** : minimum requis × `(1 + marge_simulation_pct)`.
- Sortie : faisabilité, jours ouvrés recommandés, date de fin proposée, équivalent en semaines, indicateur « période suffisante » (oui/non).

---

## 9. Sécurité, RBAC et traçabilité

### 9.1 Authentification
- Connexion via Django auth (`/login/`).
- Redirection automatique vers `/accueil/` si authentifié.

### 9.2 Autorisations (3 rôles)
| Rôle | Planning | Métier (formations, auditeurs, groupes, référentiels) | Paramétrage |
|---|---|---|---|
| `ADMIN_EDT` | Lecture + écriture + audit complet | Lecture + écriture | Lecture + écriture |
| `GESTIONNAIRE_EDT` | Lecture + écriture, audit en lecture | Lecture + écriture | **Lecture seule** |
| `DIRECTION_EDT` | Lecture seule | Lecture seule | Lecture seule |

- Toutes les vues héritent de `RoleProtectedMixin` (`shared/permissions.py`) :
  - anonyme → 302 vers `/login/` ;
  - authentifié sans permission → 403.
- Les templates masquent les actions hors permissions (`{% if perms.app.codename %}`).
- Les permissions sont assignées via la commande `seed_roles`.

### 9.3 Traçabilité
- `PlanningAuditLog` consigne toutes les actions sensibles (qui, quand, quoi, détails).
- `PlanningRun` archive chaque génération avec son rapport.
- Page d'audit dédiée (`seances:audit_list`).

---

## 10. Imports / Exports

### 10.1 Imports Excel
- **Auditeurs** (`auditeurs:import`) avec rapport d'import (succès, erreurs, doublons).
- **Formateurs par formation** (`formations:formateurs_import`).
- Détection automatique du grade, normalisation des matricules.

### 10.2 Exports
| Format | Périmètre | Vue |
|---|---|---|
| Excel (XLSX) | Planning d'un groupe | `seances:export` |
| Excel (XLSX) | Planning d'une formation | `seances:formation_export` |
| Excel (XLSX) | Auditeurs d'une formation | `formations:export_auditeurs` |
| PDF | Planning groupe | `seances:export_pdf` |
| PDF | Planning formation | `seances:formation_export_pdf` |
| Word (DOCX) | Synthèse groupe × module | `seances:groupe_module_synthese_docx` |
| Word (DOCX) | Synthèse formation × module | `seances:formation_module_synthese_docx` |

---

## 11. Parcours métier types

### 11.1 Démarrage d'une nouvelle vague
1. **Paramétrage** : créer/valider sites, bâtiments, salles, jours fériés, vagues, grades, paramètres généraux.
2. **Référentiels** : vérifier modules, types de formation, spécialités.
3. **Auditeurs** : importer les auditeurs Excel.
4. **Formation** : créer la formation (type, intitulé, vague, dates, cadence).
5. **Programme** : ajouter les modules de formation (volume, créneau, sites, formateur, période, grade cible).
6. **Inscriptions** : inscrire les auditeurs (manuel, copie d'une formation antérieure, import).
7. **Groupes** : générer automatiquement (mixage on/off) ou créer manuellement, puis configurer horaires/jours.
8. **Séances** : génération automatique → consulter la **prévisualisation** → traiter les conflits éventuels → confirmer.
9. **Exports** : Excel/PDF/Word selon le destinataire (formateurs, direction, auditeurs).

### 11.2 Régénération d'une période existante
- Modifier les dates de la formation et/ou des modules.
- Cliquer **Régénérer le planning** (`groupes:regenerer_planning`) — ne touche pas aux membres.
- *Ne pas* utiliser « Régénérer auto » qui supprime et recrée les groupes.

### 11.3 Cloner une formation
- Créer la formation cible.
- Inscrire les auditeurs via **Copier depuis une formation source** ou **Reporter tous les groupes depuis la source** (les groupes homologues sont créés à l'identique : noms, capacité, horaires, jours, cadence).

### 11.4 Anticiper la faisabilité
- Page **Simulation** → choisir une formation existante ou saisir les chiffres → obtenir durée minimum, date de fin recommandée, écart de période.

---

## 11. Périmètre gestionnaire vs planning global

### 11.1 Double périmètre (organisationnel vs physique)

| Couche | Périmètre `GESTIONNAIRE_EDT` | Périmètre Admin / Direction |
|---|---|---|
| **Listes et CRUD** formations / groupes | Uniquement `formation.responsable = user` | Toutes les formations |
| **Génération planning** | Lit **toutes** les séances en base (salles et formateurs partagés) | Idem |
| **Messages d'échec « salle occupée »** | Intitulé remplacé par « une autre formation » | Intitulé complet affiché |

Le filtrage par responsable est **organisationnel** (ownership des dossiers), pas **physique** : les ressources (salles, formateurs) restent mutualisées entre gestionnaires.

Implémentation : `shared/formations_scope.py`, paramètre `actor` sur `generer_pour_groupe` / `previsualiser_pour_groupe`, enrichissement via `planning.occupations.occupation_details_salles(masquer_noms_formations=…)`.

### 11.2 Dénormalisation des lieux et formateurs sur `Seance`

Chaque séance conserve un **snapshot** textuel pour les exports PDF/Word/Excel.

En parallèle, deux FK nullable fiabilisent les collisions :

- **`salle_id`** → `parametrage.Salle`
- **`formateur_referentiel_id`** → `formations.Formateur`

- À la génération : FK renseignées lorsque l'entité existe dans le référentiel.
- Resync lieux : `python manage.py resync_seances_lieux`

### 11.3 API JSON (lecture + PATCH séance)

Endpoints session + permissions Django (sans DRF) :

| Méthode | URL | Permission |
|---|---|---|
| GET | `/api/formations/` | `formations.view_formation` |
| GET | `/api/formations/<id>/seances/` | `seances.view_seance` |
| GET/PATCH | `/api/seances/<id>/` | `view_seance` / `change_seance` |

### 11.4 Découpage du moteur de planning

Le cœur algorithmique est découpé sous `apps/seances/planning/` :

- `constraints.py`, `locations.py`, `occupations.py`, `room_allocator.py`
- `trainer_allocator.py` — formateurs
- `diagnostics.py` — messages d'échec

`PlanningService` reste la façade orchestratrice.

### 11.5 Prévisualisation HTMX

Bouton **Prévisualiser** sur `seances/preview` → `POST …/preview-htmx/` injecte le rapport sans rechargement complet.

---

## 12. Règles métier critiques (récapitulatif normatif)

| # | Règle | Lieu d'application |
|---|---|---|
| R1 | Site obligatoire sur un module | Génération séances |
| R2 | Pas de chevauchement de salle | Générateur + `chevauchements` |
| R3 | Capacité : `capacite_max ≥ effectif − tolerance` | Veto salle |
| R4 | Jours actifs du groupe uniquement | Générateur |
| R5 | Jours fériés exclus | Générateur |
| R6 | Cadence mensuelle (formation ∩ groupe) | Générateur |
| R7 | Un seul module par jour pour un groupe | Générateur |
| R8 | Plafond séances/jour/groupe | Générateur |
| R9 | Plafond salles simultanées par module/jour | Générateur |
| R10 | Plafond 2 séances/jour par (date, module, salle) | Générateur |
| R11 | Créneau matin / soir / les deux selon `creneau_mode` | Générateur |
| R12 | Volume horaire = formation_module ou paramétrage par grade | Générateur |
| R13 | Au plus 1 formateur par (groupe, module) | Modèle (contrainte unicité) |
| R14 | Matching formateur sur spécialité du module | Affectation |
| R15 | Compatibilité grade auditeur ↔ grade_cible module | Inscription / génération groupes |
| R16 | Désactivation site/bâtiment interdite si enfants actifs | Paramétrage |
| R17 | Toutes actions sensibles tracées | `PlanningAuditLog` |
| R18 | RBAC strict 3 rôles + superuser | `RoleProtectedMixin` |

---

## 13. Critères d'acceptation client

Pour considérer la demande métier **satisfaite**, l'application doit démontrer :

- [ ] **Référentiels** : création/édition/suppression de chaque entité avec validation des dépendances.
- [ ] **Auditeurs** : import Excel avec rapport, CRUD, détection automatique du grade.
- [ ] **Formations** : CRUD complet, gestion du programme pédagogique, copie d'inscriptions, import formateurs.
- [ ] **Groupes** : génération auto avec/sans mixage, CRUD manuel, configuration horaires/jours/cadence, report depuis formation source.
- [ ] **Séances** : génération automatique respectant les 18 règles R1–R18, prévisualisation, CRUD manuel, détection des conflits avec messages explicites.
- [ ] **Exports** : Excel + PDF + Word (groupe et formation, par module).
- [ ] **Simulation** : 3 modes de calcul, intégration au paramétrage, comparaison période réelle vs recommandée.
- [ ] **Sécurité** : 3 rôles fonctionnels, redirection 302/403 conformes, masquage UI selon permissions.
- [ ] **Audit** : journal accessible, rapports `PlanningRun` persistés.
- [ ] **Documentation** : guides opérationnels (`generation_groupes_seances.md`, `reglage_scoring_salles.md`, présent document).

---

## 14. Annexes — Références techniques rapides

- **Architecture apps** : `apps/{parametrage,referentiels,auditeurs,formations,groupes,seances,simulation}` + `shared/`.
- **Modèles clés** : `Formation`, `FormationModule`, `Formateur`, `AffectationFormateurGroupe`, `Inscription`, `Groupe`, `ConfigGroupe`, `JourCours`, `Seance`, `PlanningAuditLog`, `PlanningRun`, `ParametreGeneral`, `Site`, `Batiment`, `Salle`, `Grade`, `Vague`, `JourFerie`, `Module`, `Specialite`, `TypeFormation`, `Auditeur`.
- **Commandes utiles** :
  - `python manage.py migrate` — migrations base.
  - `python manage.py seed_roles` — provisionnement RBAC.
  - `python manage.py auth_db` — initialisation des comptes.
  - `python manage.py resync_seances_lieux` — realigne `salle_id` et noms de lieux depuis le paramétrage.
- **API JSON** : `GET /api/formations/`, `GET /api/formations/<id>/seances/` (session authentifiée).
- **Documents associés** :
  - `docs/generation_groupes_seances.md`
  - `docs/reglage_scoring_salles.md`
  - `README.md` (mise en route + RBAC)
