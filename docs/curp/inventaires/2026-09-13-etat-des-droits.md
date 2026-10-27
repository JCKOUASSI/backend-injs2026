# ÉTAT DES DROITS EXISTANTS — extrait automatiquement du code serveur
# Généré par : manage.py inventaire_habilitation
# Source : authentication/role_groups.py (les groupes Django sont la
# source de vérité des rôles ; le champ User.role est synchronisé).

## Les 12 rôles et leurs groupes

| Code rôle | Libellé | Groupe Django |
|---|---|---|
| ADMIN | Administrateur | ROLE_ADMIN |
| DIRECTION | Direction | ROLE_DIRECTION |
| CHEF_CPFAE_ADMIN | Chef INJS Admin | ROLE_CHEF_CPFAE_ADMIN |
| CPFAE_ADMIN | INJS Admin | ROLE_CPFAE_ADMIN |
| CHEF_SECRETARIAT | Chef Secrétariat | ROLE_CHEF_SECRETARIAT |
| SECRETARIAT | Secrétariat | ROLE_SECRETARIAT |
| FINANCE | Finance | ROLE_FINANCE |
| ARCHIVE | Archiviste | ROLE_ARCHIVE |
| ENCADRANT | Encadrant | ROLE_ENCADRANT |
| SUPERVISEUR | Superviseur | ROLE_SUPERVISEUR |
| FORMATEUR | Formateur | ROLE_FORMATEUR |
| AUDITEUR | Étudiant | ROLE_AUDITEUR |

## Ensembles de rôles effectifs (constantes serveur)

- **Rôles web autorisés (ALLOWED_WEB_ROLES)** : ADMIN, ARCHIVE, CHEF_CPFAE_ADMIN, CHEF_SECRETARIAT, CPFAE_ADMIN, DIRECTION, ENCADRANT, FINANCE, SECRETARIAT, SUPERVISEUR
- **Rôles réservés mobile/PWA (MOBILE_ONLY_ROLES)** : AUDITEUR, FORMATEUR
- **Rôles d'encadrement mobile** : ENCADRANT, SUPERVISEUR
- **Accès global (GLOBAL_ACCESS_ROLES)** : ADMIN, ARCHIVE, CHEF_CPFAE_ADMIN, CPFAE_ADMIN, DIRECTION
- **Rôles de secrétariat cloisonnés** : CHEF_SECRETARIAT, SECRETARIAT
- **Rôles du module Finance** : ARCHIVE, DIRECTION, FINANCE
- **Rôles pouvant muter les comptes** : ADMIN, CHEF_CPFAE_ADMIN, CHEF_SECRETARIAT, CPFAE_ADMIN, SECRETARIAT

## Politique de permissions par rôle (ROLE_POLICY)

### ADMIN
- applications : authentication, formations, presences, exports
- actions modèles : view, add, change, delete
- permissions métier : access_web, operational_web, mutate_users, global_scope, list_participants, manage_questionnaires, manage_notes, validate_decisions, consult_evaluation
- permissions exclues : —

### CHEF_CPFAE_ADMIN
- applications : authentication, formations, presences, exports
- actions modèles : view, add, change, delete
- permissions métier : access_web, operational_web, mutate_users, global_scope, list_participants, manage_questionnaires, manage_notes, validate_decisions, consult_evaluation
- permissions exclues : —

### CPFAE_ADMIN
- applications : authentication, formations, presences, exports
- actions modèles : view, add, change, delete
- permissions métier : access_web, operational_web, mutate_users, global_scope, list_participants, manage_questionnaires, manage_notes, validate_decisions, consult_evaluation
- permissions exclues : —

### DIRECTION
- applications : authentication, formations, presences, exports
- actions modèles : view
- permissions métier : access_web, operational_web, global_scope, list_participants, manage_notes, validate_decisions, consult_evaluation
- permissions exclues : —

### CHEF_SECRETARIAT
- applications : formations, presences, suiviEvaluation
- actions modèles : view, add, change, delete
- permissions métier : access_web, operational_web, mutate_users, list_participants, manage_questionnaires, manage_notes, validate_decisions, consult_evaluation
- permissions exclues : add_participant

### SECRETARIAT
- applications : formations, presences, suiviEvaluation
- actions modèles : view, add, change, delete
- permissions métier : access_web, operational_web, mutate_users, list_participants, manage_questionnaires, manage_notes, validate_decisions, consult_evaluation
- permissions exclues : add_participant

### FINANCE
- applications : formations, presences, exports
- actions modèles : view
- permissions métier : access_web, finance_module, consult_evaluation
- permissions exclues : —

### ARCHIVE
- applications : authentication, formations, presences, exports, suiviEvaluation
- actions modèles : view
- permissions métier : access_web, operational_web, global_scope, list_participants, finance_module, consult_evaluation
- permissions exclues : —

### ENCADRANT
- applications : formations, presences, suiviEvaluation
- actions modèles : view, add, change, delete
- permissions métier : access_web, operational_web, list_participants, manage_questionnaires, manage_notes, validate_decisions, consult_evaluation
- permissions exclues : —

### SUPERVISEUR
- applications : suiviEvaluation
- actions modèles : view, add, change, delete
- permissions métier : access_web, operational_web, manage_questionnaires, manage_notes, validate_decisions, consult_evaluation
- permissions exclues : —

### FORMATEUR
- applications : formations, presences
- actions modèles : view
- permissions métier : —
- permissions exclues : —

### AUDITEUR
- applications : formations, presences
- actions modèles : view
- permissions métier : —
- permissions exclues : —

## Permissions métier personnalisées du modèle utilisateur
- `authentication.access_web` — Accès à la plateforme web
- `authentication.operational_web` — Personnel opérationnel web (hors module Finance)
- `authentication.mutate_users` — Créer ou modifier des comptes utilisateurs
- `authentication.global_scope` — Périmètre global (tous secrétariats)
- `authentication.list_participants` — Consulter la liste des participants
- `authentication.finance_module` — Accès au module Finance
- `authentication.manage_questionnaires` — Gérer les questionnaires d'évaluation
- `authentication.manage_notes` — Gérer les notes et épreuves
- `authentication.validate_decisions` — Valider les décisions pédagogiques
- `authentication.consult_evaluation` — Consulter les évaluations

## Règles de transport
- FORMATEUR et AUDITEUR : connexion web REFUSÉE (HTTP 403,
  message « réservé à l'application mobile ») ; device_id requis et
  vérification d'appairage presences.DeviceBinding côté mobile.
- Le cloisonnement par secrétariat est appliqué dans formations.access
  (modules/participants filtrés sur user.secretariat) et les permissions
  DRF IsSecretariat* ; il doit être préservé par le chantier CURP.
