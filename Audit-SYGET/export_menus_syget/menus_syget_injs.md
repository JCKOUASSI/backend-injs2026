# Arborescence complète des Menus — SYGET-INJS (INJS Abidjan)

## 1. Menu de navigation principal (Barre latérale)

| # | Libellé du menu | URL | Route Django | Permission requise | Rôles autorisés |
|---|---|---|---|---|---|
| 1 | **Accueil (Tableau de bord)** | `/accueil/` | `home` | `Authentifié (LoginRequired)` | Superuser, ADMIN_EDT, GESTIONNAIRE_EDT, DIRECTION_EDT, RUP_EDT |
| 2 | **Formations** | `/formations/` | `formations:list` | `formations.view_formation` | Superuser, ADMIN_EDT, GESTIONNAIRE_EDT, DIRECTION_EDT, RUP_EDT |
| 3 | **Auditeurs** | `/auditeurs/` | `auditeurs:list` | `auditeurs.view_auditeur` | Superuser, ADMIN_EDT, GESTIONNAIRE_EDT, DIRECTION_EDT |
| 4 | **Formateurs** | `/formations/formateurs/` | `formations:formateurs_list` | `formations.view_formateur` | Superuser, ADMIN_EDT, GESTIONNAIRE_EDT, DIRECTION_EDT, RUP_EDT |
| 5 | **Paramétrage** | `/parametrage/` | `parametrage:index` | `parametrage.view_parametregeneral` | Superuser, ADMIN_EDT, GESTIONNAIRE_EDT (lecture), DIRECTION_EDT (lecture) |
| 6 | **Simulation** | `/simulation/` | `simulation:index` | `formations.view_formation` | Superuser, ADMIN_EDT, GESTIONNAIRE_EDT, DIRECTION_EDT, RUP_EDT |
| 7 | **Administration** | `/admin/` | `admin:index` | `user.is_staff` | Superuser / Staff |
| 8 | **Déconnexion** | `/logout/` | `logout` | `Authentifié (POST)` | Tous |

## 2. Sous-menus, accès rapides et actions par module

| Module | Élément / Sous-menu | URL | Route Django | Type d'action | Permission |
|---|---|---|---|---|---|
| Accueil (Accès rapides) | **Nouvelle formation** | `/formations/create/` | `formations:create` | Navigation / Formulaire | `formations.add_formation` |
| Accueil (Accès rapides) | **Importer auditeurs** | `/auditeurs/import/` | `auditeurs:import` | Import Excel | `auditeurs.add_auditeur` |
| Accueil (Accès rapides) | **Liste auditeurs** | `/auditeurs/` | `auditeurs:list` | Liste | `auditeurs.view_auditeur` |
| Accueil (Accès rapides) | **Importer formateurs** | `/formations/formateurs/import/` | `formations:formateurs_import_page` | Import Excel | `formations.add_formateur` |
| Accueil (Accès rapides) | **Paramétrage** | `/parametrage/` | `parametrage:index` | Configuration | `parametrage.view_parametregeneral` |
| Accueil (Accès rapides) | **Chevauchements salles** | `/seances/chevauchements/` | `seances:chevauchements` | Contrôle conflits | `seances.view_seance` |
| Formations | **Détail & Programme pédagogique** | `/formations/<id>/` | `formations:detail` | Vue détail (Périodes, Modules, Inscriptions) | `formations.view_formation` |
| Formations | **Unité Pédagogique (Affectation Formateurs RUP)** | `/formations/<id>/up/` | `formations:rup_unite` | Affectation formateurs par groupe/module | `formations.view_formation` |
| Formations | **Export Auditeurs de la formation (Excel)** | `/formations/<id>/export/auditeurs/` | `formations:export_auditeurs` | Export XLSX | `formations.view_formation` |
| Groupes & Répartition | **Gestion des groupes d'une formation** | `/groupes/formation/<formation_id>/` | `groupes:list` | Liste, Config horaires/jours, Génération auto | `groupes.view_groupe` |
| Groupes & Répartition | **Générer automatiquement les groupes par grade** | `/groupes/formation/<formation_id>/auto/` | `groupes:auto_generate` | Action POST moteur groupes+séances | `groupes.add_groupe + delete_groupe` |
| Groupes & Répartition | **Régénérer le planning de la formation** | `/groupes/formation/<formation_id>/planning/` | `groupes:regenerer_planning` | Action POST moteur planning | `seances.add_seance` |
| Groupes & Répartition | **Gérer les membres d'un groupe** | `/groupes/<groupe_id>/membres/` | `groupes:membre_add` | Affectation / retrait auditeurs | `groupes.change_groupe` |
| Groupes & Répartition | **Menu Exporter (Formation) — Cours / Séances / Formateurs / PDF / ZIP / Synthèse UP DOCX** | `/seances/formation/<formation_id>/export/...` | `seances:formation_export*` | Menu déroulant multi-exports | `seances.view_seance` |
| Séances & Emploi du temps | **Aperçu & Édition du planning d'un groupe** | `/seances/groupe/<groupe_id>/` | `seances:preview` | Grille calendrier, filtres, conflits, ajout/édition séance | `seances.view_seance` |
| Séances & Emploi du temps | **Export Excel — Séances uniquement** | `/seances/groupe/<groupe_id>/export/?format=seances` | `seances:export` | Export XLSX onglet Séances | `seances.view_seance` |
| Séances & Emploi du temps | **Export Excel — Cours (Formations)** | `/seances/groupe/<groupe_id>/export/?format=cours` | `seances:export` | Export XLSX onglet Formations | `seances.view_seance` |
| Séances & Emploi du temps | **Export Excel — Formateurs (module)** | `/seances/groupe/<groupe_id>/export/?format=formateurs` | `seances:export` | Export XLSX onglet Formateurs | `seances.view_seance` |
| Séances & Emploi du temps | **Export PDF Emploi du temps** | `/seances/groupe/<groupe_id>/export-pdf/` | `seances:export_pdf` | Export PDF A4 Paysage | `seances.view_seance` |
| Séances & Emploi du temps | **Journal d'audit du planning** | `/seances/audit/` | `seances:audit_list` | Historique traçabilité | `seances.view_planningauditlog` |
| Séances & Emploi du temps | **Détection des chevauchements de salles** | `/seances/chevauchements/` | `seances:chevauchements` | Contrôle qualité salles | `seances.view_seance` |
| Paramétrage & Référentiels | **Onglet Paramètres généraux & par formation** | `/parametrage/#pane-parametres` | `parametrage:index` | Horaires, capacité, scoring salles | `parametrage.change_parametregeneral` |
| Paramétrage & Référentiels | **Onglet Lieux (Sites, Bâtiments, Salles, Disponibilités)** | `/parametrage/#pane-lieux` | `parametrage:index` | CRUD hiérarchique des locaux | `parametrage.view_site` |
| Paramétrage & Référentiels | **Onglet Types de formation, Grades, Vagues, Jours fériés** | `/parametrage/#pane-referentiels` | `parametrage:index` | CRUD nomenclatures | `parametrage.view_grade` |
| Paramétrage & Référentiels | **Onglet Modules & Volumes horaires par défaut** | `/parametrage/#pane-modules` | `parametrage:index` | Catalogue modules + associations Type/Grade | `referentiels.view_module` |
| Référentiels dédiés | **Catalogue des Modules** | `/referentiels/modules/` | `referentiels:module_list` | CRUD Modules & Spécialités | `referentiels.view_module` |
| Référentiels dédiés | **Catalogue des Types de formation** | `/referentiels/types/` | `referentiels:type_list` | Liste Types de formation | `referentiels.view_typeformation` |

## 3. Menus de l'Administration Backend (Django Unfold `/admin/`)

| Application | Entrée de menu (Modèle) | Classe | URL Admin |
|---|---|---|---|
| Auditeurs (`auditeurs`) | **Auditeurs** | `Auditeur` | `/admin/auditeurs/auditeur/` |
| Authentification et autorisation (`auth`) | **Groupes** | `Group` | `/admin/auth/group/` |
| Authentification et autorisation (`auth`) | **Utilisateurs** | `User` | `/admin/auth/user/` |
| Formations (`formations`) | **Affectations formateurs/groupes** | `AffectationFormateurGroupe` | `/admin/formations/affectationformateurgroupe/` |
| Formations (`formations`) | **Formateurs** | `Formateur` | `/admin/formations/formateur/` |
| Formations (`formations`) | **Formations** | `Formation` | `/admin/formations/formation/` |
| Formations (`formations`) | **Inscriptions** | `Inscription` | `/admin/formations/inscription/` |
| Formations (`formations`) | **Modules de formation** | `FormationModule` | `/admin/formations/formationmodule/` |
| Formations (`formations`) | **Périodes de formation** | `FormationPeriode` | `/admin/formations/formationperiode/` |
| Formations (`formations`) | **Responsables d'unités pédagogiques** | `ResponsableUnitePedagogique` | `/admin/formations/responsableunitepedagogique/` |
| Groupes (`groupes`) | **Groupes** | `Groupe` | `/admin/groupes/groupe/` |
| Groupes (`groupes`) | **Membres du groupe** | `GroupeAuditeur` | `/admin/groupes/groupeauditeur/` |
| Paramétrage (`parametrage`) | **Associations modules / types** | `ModuleTypeFormation` | `/admin/parametrage/moduletypeformation/` |
| Paramétrage (`parametrage`) | **Bâtiments** | `Batiment` | `/admin/parametrage/batiment/` |
| Paramétrage (`parametrage`) | **Grades** | `Grade` | `/admin/parametrage/grade/` |
| Paramétrage (`parametrage`) | **Jours fériés** | `JourFerie` | `/admin/parametrage/jourferie/` |
| Paramétrage (`parametrage`) | **Paramètres de formation** | `ParametreFormation` | `/admin/parametrage/parametreformation/` |
| Paramétrage (`parametrage`) | **Paramètres généraux** | `ParametreGeneral` | `/admin/parametrage/parametregeneral/` |
| Paramétrage (`parametrage`) | **Périodes de disponibilité des sites** | `PeriodeDisponibiliteSite` | `/admin/parametrage/periodedisponibilitesite/` |
| Paramétrage (`parametrage`) | **Salles** | `Salle` | `/admin/parametrage/salle/` |
| Paramétrage (`parametrage`) | **Sites** | `Site` | `/admin/parametrage/site/` |
| Paramétrage (`parametrage`) | **Vagues** | `Vague` | `/admin/parametrage/vague/` |
| Référentiels (`referentiels`) | **Modules** | `Module` | `/admin/referentiels/module/` |
| Référentiels (`referentiels`) | **Spécialités** | `Specialite` | `/admin/referentiels/specialite/` |
| Référentiels (`referentiels`) | **Types de formation** | `TypeFormation` | `/admin/referentiels/typeformation/` |
| Séances (`seances`) | **Audit planning** | `PlanningAuditLog` | `/admin/seances/planningauditlog/` |
| Séances (`seances`) | **Rapports de planning** | `PlanningRun` | `/admin/seances/planningrun/` |
| Séances (`seances`) | **Séances** | `Seance` | `/admin/seances/seance/` |
